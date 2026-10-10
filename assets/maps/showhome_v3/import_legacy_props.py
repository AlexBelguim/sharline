"""Every prop the original Showhome uses, as reusable catalog props for the builder (user, 2026-10-10: "find all
props we use in any map so far and place them in a lib for the builder").

Blender -b --factory-startup -P import_legacy_props.py [-- --only PROP_Arbour,... ]

Source: assets/maps/showhome/kit/props.glb (the old map's local-origin prop library, 58 roots). Five of them were
converted earlier by build_library.py (moving_truck, city_car, hot_tub, sofa, heat_pump) and are skipped here.

Collision, prop-local design metres (the catalog contract, see build_library.save_prop):
- a prop the old map placed on collision brushes ('matched') gets exactly those brushes, moved into its own frame
  from its first placement (props_placements.json + the tagged brushes in layout/showhome_annotated.json): walls with
  their real door openings for the sheds, studios, greenhouses, sales office and parcel hub, solid boxes for the rest;
- a free / detail prop gets the convex hull of its visuals (an axis box if the hull is unusable or too detailed);
- the overhead wire and the zipline cable get none (they are set dressing above head height).

Output: assets/props/<category>/<id>/ (glb, lod1, collision.json, metadata.json) merged into assets/props/catalog.json
with the tags [category, 'showhome_legacy']. deploy_legacy_props.py stages them into game/assets.
"""
import sys, json, math
from pathlib import Path
import bpy, bmesh
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C
import build_library as BL

ROOT = C.ROOT
OLD = ROOT / 'assets/maps/showhome'
PROPS_GLB = OLD / 'kit/props.glb'

# old root name -> (catalog id, category, default phys of its walls / solid parts)
LEGACY = {
    'Arbour': ('arbour', 'garden', 'wood_thick'),
    'Armchair': ('armchair_boxed', 'furniture', 'fabric'),
    'BinStore': ('bin_store', 'utilities', 'wood_thin'),
    'Box_S': ('box_small', 'clutter', 'wood_thin'),
    'Box_M': ('box_medium', 'clutter', 'wood_thin'),
    'Box_L': ('box_large', 'clutter', 'wood_thin'),
    'Box_M_Open': ('box_medium_open', 'clutter', 'wood_thin'),
    'BoxStack_1m': ('box_stack', 'clutter', 'wood_thin'),
    'Crate_Wood_1m': ('wood_crate', 'clutter', 'wood_thin'),
    'CementBag': ('cement_bag', 'worksite', 'sand'),
    'CementBagPallet': ('cement_bag_pallet', 'worksite', 'sand'),
    'ChargerIsland': ('charger_island', 'utilities', 'sheet_metal'),
    'DirtMound': ('dirt_mound', 'worksite', 'soil'),
    'SandMound': ('sand_mound', 'worksite', 'sand'),
    'Dresser': ('chest_of_drawers', 'furniture', 'wood_thick'),
    'Fence_Gate_1m': ('picket_gate_1m', 'fences', 'wood_thin'),
    'Fence_Picket_1m': ('picket_fence_1m', 'fences', 'wood_thin'),
    'Fence_Picket_2m': ('picket_fence_2m', 'fences', 'wood_thin'),
    'Fence_Post': ('picket_post', 'fences', 'wood_thick'),
    'Fence_Run_N': ('picket_run_5m', 'fences', 'wood_thin'),
    'Fence_Run_S': ('picket_run_10m', 'fences', 'wood_thin'),
    'Greenhouse_Clay': ('greenhouse_clay', 'buildings', 'glass'),
    'Greenhouse_Sage': ('greenhouse_sage', 'buildings', 'glass'),
    'Hedge_Block_2m': ('hedge_block_2m', 'garden', 'foliage_dense'),
    'Hedge_Block_4m_Tall': ('hedge_block_4m_tall', 'garden', 'foliage_dense'),
    'Hedge_Boundary': ('hedge_boundary_46m', 'garden', 'foliage_dense'),
    'Hedge_Lawn': ('hedge_lawn_5m', 'garden', 'foliage_dense'),
    'KerbPod': ('kerb_pod', 'vehicles', 'sheet_metal'),
    'KitchenIsland': ('kitchen_island', 'furniture', 'wood_thick'),
    'ModelTable': ('model_table', 'furniture', 'wood_thick'),
    'OutdoorKitchen': ('outdoor_kitchen', 'garden', 'concrete'),
    'Pallet': ('pallet_empty', 'worksite', 'wood_thin'),
    'ParcelHub': ('parcel_hub', 'buildings', 'concrete'),
    'ParcelLockers': ('parcel_lockers', 'utilities', 'sheet_metal'),
    'PebbleCluster': ('pebble_cluster', 'garden', 'gravel'),
    'PlasticBarrier': ('water_barrier', 'worksite', 'plastic'),
    'PrintedBlockStack': ('printed_block_stack', 'worksite', 'concrete'),
    'Pylon': ('utility_pylon', 'utilities', 'concrete'),
    'RainTank': ('rain_tank', 'utilities', 'plastic'),
    'RebarBundle': ('rebar_bundle_6m', 'worksite', 'metal_heavy'),
    'Rock_Low': ('rock_low', 'garden', 'concrete'),
    'Rock_Tall': ('rock_tall', 'garden', 'concrete'),
    'SalesOffice': ('sales_office', 'buildings', 'concrete'),
    'Shed_Clay': ('shed_clay', 'buildings', 'wood_thin'),
    'Shed_Sage': ('shed_sage', 'buildings', 'wood_thin'),
    'Shelving': ('garage_shelving', 'furniture', 'sheet_metal'),
    'ShuttleStop': ('shuttle_stop', 'utilities', 'wood_thin'),
    'Studio_Clay': ('studio_clay', 'buildings', 'concrete'),
    'Studio_Sage': ('studio_sage', 'buildings', 'concrete'),
    'TrafficCone': ('traffic_cone', 'worksite', 'plastic'),
    'Wire_Span_20m': ('wire_span_20m', 'utilities', None),
    'Workbench': ('workbench', 'furniture', 'wood_thick'),
    'Zipline_Cable': ('zipline_cable', 'utilities', None),
}
# A brush look overrides the prop's default phys where it says what it is.
LOOK_PHYS = {'Metal': 'metal_heavy', 'Vehicle': 'sheet_metal', 'Hedge': 'foliage_dense', 'Fence': 'wood_thin',
             'Floor': 'concrete', 'Roof': None, 'Wall': None, 'Prop': None}
MAX_HULL_PLANES = 96


def matched_brushes(old):
    """The old map's collision boxes of this prop, in its own frame (first placement), or None if unplaced."""
    places = [p for p in json.loads((OLD / 'kit/props_placements.json').read_text())['placements']
              if p['prop'] == 'PROP_' + old]
    if not places:
        return None
    place = next((p for p in places if p['yaw_deg'] == 0), places[0])
    brushes = json.loads((OLD / 'layout/showhome_annotated.json').read_text())['brushes']
    loc = Vector(place['design_loc'])
    yaw = math.radians(place['yaw_deg'])
    c, s = math.cos(-yaw), math.sin(-yaw)
    out = []
    for b in brushes:
        tag = b.get('tag') or {}
        if tag.get('id') not in place['brushes'] or b['kind'] == 'PlayerClip' or b['shape'] != 'box':
            continue
        corners = []
        for x in (b['min'][0], b['max'][0]):
            for y in (b['min'][1], b['max'][1]):
                d = Vector((x, y, 0)) - Vector((loc.x, loc.y, 0))
                corners.append((d.x * c - d.y * s, d.x * s + d.y * c))
        lo = (min(p[0] for p in corners), min(p[1] for p in corners), b['min'][2] - loc.z)
        hi = (max(p[0] for p in corners), max(p[1] for p in corners), b['max'][2] - loc.z)
        out.append((tag.get('id') + '_' + tag.get('part', 'solid') + '_' + str(b['i']), lo, hi, b['look']))
    return out


def convex_ok(verts, faces):
    centre = sum(verts, Vector()) / len(verts)
    planes = []
    for f in faces:
        ps = [verts[i] for i in f]
        n = (ps[1] - ps[0]).cross(ps[2] - ps[0])
        if n.length < 1e-9:
            return False
        n.normalize()
        if n.dot(sum(ps, Vector()) / len(ps) - centre) < 0:
            n = -n
        d = n.dot(ps[0])
        if max(n.dot(v) - d for v in verts) > .00015:
            return False
        if not any(max(abs(a - b) for a, b in zip((*n, d), q)) < 1e-6 for q in planes):
            planes.append((*n, d))
    return len(planes) <= MAX_HULL_PLANES


def hull_or_box(root, pid, phys):
    obs = C.visuals()
    pts = [ob.matrix_world @ v.co for ob in obs for v in ob.data.vertices]
    mn = Vector([min(p[k] for p in pts) for k in range(3)])
    mx = Vector([max(p[k] for p in pts) for k in range(3)])
    # Thin in one axis (a pebble cluster, a bag): at least 5 mm, the contract's minimum.
    for k in range(3):
        if mx[k] - mn[k] < .006:
            mx[k] = mn[k] + .006
    bm = bmesh.new()
    for p in pts:
        bm.verts.new(p)
    try:
        res = bmesh.ops.convex_hull(bm, input=list(bm.verts))
        bmesh.ops.delete(bm, geom=list({g for g in res['geom_interior'] + res['geom_unused'] if isinstance(g, bmesh.types.BMVert)}), context='VERTS')
        bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(.05), verts=list(bm.verts), edges=list(bm.edges))
        bm.verts.index_update()
        verts = [v.co.copy() for v in bm.verts]
        faces = [[v.index for v in f.verts] for f in bm.faces]
        good = len(verts) >= 4 and len(faces) >= 4 and convex_ok(verts, faces) and min(mx - mn) >= .006
    except Exception as e:  # degenerate input: fall back to the box
        print('HULL_FAILED', pid, e)
        good = False
    finally:
        bm.free()
    if good:
        C.col_mesh(pid + '_hull', [tuple(v) for v in verts], faces, phys, parent=root)
        return 'hull'
    C.col_box(pid, tuple(mn), tuple(mx), phys, parent=root)
    return 'box'


def build(old, pid, category, phys):
    root = BL.begin(pid, category)
    root['source'] = 'original assets/maps/showhome procedural ' + old
    BL.reuse(root, PROPS_GLB, 'PROP_' + old + '_Root')
    bpy.context.view_layer.update()
    kind = 'none'
    if phys is not None:
        boxes = matched_brushes(old)
        if boxes:
            for name, lo, hi, look in boxes:
                C.col_box(name, lo, hi, LOOK_PHYS.get(look) or phys, parent=root)
            kind = 'brushes %d' % len(boxes)
        else:
            kind = hull_or_box(root, pid, phys)
    print('LEGACY_COLLISION', pid, kind, flush=True)
    BL.save_prop(root, pid, category, 'original assets/maps/showhome procedural ' + old)
    entry = BL.CATALOG[-1]
    entry['tags'] = [category, 'showhome_legacy']
    entry['legacy_root'] = 'PROP_' + old
    C.write(ROOT / 'assets/props' / category / pid / 'metadata.json', entry)


def main():
    only = None
    if '--only' in sys.argv:
        only = set(sys.argv[sys.argv.index('--only') + 1].split(','))
    for old, (pid, category, phys) in LEGACY.items():
        if only and old not in only and pid not in only:
            continue
        build(old, pid, category, phys)
    p = ROOT / 'assets/props/catalog.json'
    existing = json.loads(p.read_text()) if p.exists() else {'schema': 1, 'props': []}
    new_ids = {r['id'] for r in BL.CATALOG}
    existing['props'] = [r for r in existing.get('props', []) if r['id'] not in new_ids] + BL.CATALOG
    C.write(p, existing)
    print('LEGACY_DONE', len(BL.CATALOG), flush=True)


if __name__ == '__main__':
    main()
