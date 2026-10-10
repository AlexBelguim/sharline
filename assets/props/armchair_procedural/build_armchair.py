"""Original authored upholstered chair. No generated/imported geometry.

Blender 5.2: blender --disable-autoexec -b --factory-startup -P build_armchair.py
Pass -- --quick for a two-view iteration; default rebuilds exports and full QA.
All asset vertices are authored directly in metres, Z-up, front -Y.
"""
import bpy
import bmesh
import json
import math
import os
import struct
import sys
import time
import zlib
from pathlib import Path

import numpy as np
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import blender_common as bc

TEX, RENDERS = HERE / 'textures', HERE / 'renders'
for path in (TEX, RENDERS):
    path.mkdir(parents=True, exist_ok=True)
QUICK = '--quick' in sys.argv
START = time.time()


def png_write(path, data):
    data = np.clip(np.rint(data), 0, 255).astype(np.uint8)
    h, w, channels = data.shape
    assert channels == 3
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff)
    rows = b''.join(b'\x00' + row.tobytes() for row in data)
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) +
                         chunk(b'IDAT', zlib.compress(rows, 7)) + chunk(b'IEND', b''))


def srgb(value):
    return np.where(value <= .0031308, value * 12.92, 1.055 * np.maximum(value, 0) ** (1 / 2.4) - .055)


def linear(value):
    return np.where(value <= .04045, value / 12.92, ((value + .055) / 1.055) ** 2.4)


TEXTURE_SOURCES = []
def painted_material(key, color, rough, source, amount, wood=False):
    """Freeze source texture multiplied/tinted in linear light into portable PBR maps."""
    path = ROOT / source
    TEXTURE_SOURCES.append(source)
    image = bpy.data.images.load(str(path), check_existing=False)
    image.colorspace_settings.name = 'Non-Color'
    w, h = image.size
    pixels = np.asarray(image.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1, :, :3]
    bpy.data.images.remove(image)
    if wood:
        # One timber board interior, without flooring/plank-joint lines on a chair foot.
        pixels = pixels[int(h * .05):int(h * .45), int(w * .061):int(w * .141)]
    pixels = pixels[::max(1, pixels.shape[0] // 512), ::max(1, pixels.shape[1] // 512)]
    src = linear(pixels)
    factor = (1 - amount) + amount * src
    factor /= factor.mean(axis=(0, 1), keepdims=True)
    rgb = srgb(np.clip(np.asarray(color) * factor, 0, 1))
    albedo, orm = TEX / f'ACP_{key}_basecolor.png', TEX / f'ACP_{key}_orm.png'
    png_write(albedo, rgb * 255)
    luminance = src.mean(axis=2)
    maps = np.ones_like(src)
    maps[:, :, 1] = np.clip(rough + (luminance - luminance.mean()) * .07, .1, 1)
    maps[:, :, 2] = 0
    png_write(orm, maps * 255)
    mat = bc.material('M_ACP_' + key, color, rough=rough)
    mat.use_backface_culling = True
    nt = mat.node_tree
    bs = nt.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = (1, 1, 1, 1)
    # Linked maps are authoritative. Sensible unlinked fallbacks also survive FBX
    # importers that do not understand packed roughness/metallic channel routing.
    bs.inputs['Roughness'].default_value = rough
    bs.inputs['Metallic'].default_value = 0
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(albedo), check_existing=True)
    tex.image.colorspace_settings.name = 'sRGB'
    nt.links.new(tex.outputs['Color'], bs.inputs['Base Color'])
    packed = nt.nodes.new('ShaderNodeTexImage')
    packed.image = bpy.data.images.load(str(orm), check_existing=True)
    packed.image.colorspace_settings.name = 'Non-Color'
    separate = nt.nodes.new('ShaderNodeSeparateColor')
    nt.links.new(packed.outputs['Color'], separate.inputs['Color'])
    nt.links.new(separate.outputs['Green'], bs.inputs['Roughness'])
    nt.links.new(separate.outputs['Blue'], bs.inputs['Metallic'])
    # No shader noise, fake micro-normal, emission or texture-transform dependency.
    bs.inputs['Specular IOR Level'].default_value = .30
    return mat


def mesh(name, verts, faces, mat, smooth=True):
    data = bpy.data.meshes.new('ACP_' + name)
    data.from_pydata(verts, [], faces)
    data.update()
    ob = bpy.data.objects.new('ACP_' + name, data)
    bpy.context.scene.collection.objects.link(ob)
    bc.assign(ob, mat)
    bm = bmesh.new()
    bm.from_mesh(data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(data)
    bm.free()
    for p in data.polygons:
        p.use_smooth = smooth
    return ob


def roundrect(width, height, radius, segments=5):
    """Clockwise-perimeter-independent rounded rectangle: large straight main edges."""
    points = []
    for cx, cy, angle in ((width/2-radius, height/2-radius, 0),
                          (-width/2+radius, height/2-radius, 90),
                          (-width/2+radius, -height/2+radius, 180),
                          (width/2-radius, -height/2+radius, 270)):
        for i in range(segments + 1):
            a = math.radians(angle + i * 90 / segments)
            points.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
    return points


def pillow(name, outline, half_depth, mapper, mat, slight_pinches=False):
    """Pressure-fitted cushion/profile loft; broad planes bulge before tucked perimeter.

    Flat central plateau, pressure crown, rounded edge and flattened back.
    This is a radial sewn-volume loft, never a bevelled box or subdivision cube.
    """
    rings = [(.54, -1.00), (.88, -.87), (.97, -.52), (1.00, 0),
             (.97, .52), (.88, .87), (.54, 1.00)]
    vertices, faces = [], []
    n = len(outline)
    for scale, depth in rings:
        for i, (u, v) in enumerate(outline):
            tuck = 1
            if slight_pinches and i in (1, 7, 13, 19):
                tuck -= .012 * (1 - abs(depth))
            vertices.append(mapper(u * scale * tuck, v * scale, half_depth * depth))
    for ring in range(len(rings)-1):
        for i in range(n):
            j = (i+1) % n
            faces.append((ring*n+i, ring*n+j, (ring+1)*n+j, (ring+1)*n+i))
    faces.append(tuple(reversed(range(n))))
    faces.append(tuple(range((len(rings)-1)*n, len(rings)*n)))
    return mesh(name, vertices, faces, mat)


def tube(name, points, radius, mat, closed=True, sides=4):
    """Small authored welt/fold tube, capped when open; no curve export conversion."""
    positions = [Vector(p) for p in points]
    n, vertices, faces = len(points), [], []
    for i, p in enumerate(positions):
        prev = positions[(i-1) % n] if closed or i > 0 else p
        nxt = positions[(i+1) % n] if closed or i < n-1 else p
        tangent = (nxt-prev).normalized()
        reference = Vector((0, 0, 1))
        if abs(tangent.dot(reference)) > .90:
            reference = Vector((0, 1, 0))
        a = tangent.cross(reference).normalized()
        b = tangent.cross(a).normalized()
        for k in range(sides):
            angle = k * math.tau / sides
            vertices.append(tuple(p + radius * (a * math.cos(angle) + b * math.sin(angle))))
    for i in range(n if closed else n-1):
        j = (i+1) % n
        for k in range(sides):
            q = (k+1) % sides
            faces.append((i*sides+k, i*sides+q, j*sides+q, j*sides+k))
    if not closed:
        faces += [tuple(reversed(range(sides))), tuple(range((n-1)*sides, n*sides))]
    return mesh(name, vertices, faces, mat)


def arm(name, side):
    """Soft elongated roll with an intentional cloth cap and broad smooth upper arc."""
    profile = []
    for i in range(24):
        a = i * math.tau / 24
        x = .095 * math.cos(a)
        z = .081 * math.sin(a)
        # Gently flatten the pressure area where forearms rest.
        if z > .050:
            z = .050 + (z-.050) * .68
        profile.append((x, z))
    stations = [(-.368, .62), (-.357, .88), (-.334, 1), (-.18, 1),
                (.045, .97), (.220, .92), (.271, .72), (.287, .43)]
    verts, faces = [], []
    for y, scale in stations:
        for x, z in profile:
            verts.append((side*.345 + x*scale, y, .550 + z*scale + .016*((y+.368)/.655)))
    n = len(profile)
    for r in range(len(stations)-1):
        for i in range(n):
            j = (i+1) % n
            faces.append((r*n+i, r*n+j, (r+1)*n+j, (r+1)*n+i))
    faces += [tuple(reversed(range(n))), tuple(range((len(stations)-1)*n, len(stations)*n))]
    mesh(name + '_Roll', verts, faces, BODY)
    # Sewn oval end panel: enough relief to read as rolled upholstery, no spiral lump.
    cap_outline = [(x*.82, z*.82) for x,z in profile]
    mapper = lambda u,v,w:(side*.345+u, -.359+w, .550+v)
    pillow(name+'_EndCap', cap_outline, .009, mapper, CUSHION)
    tube(name+'_CapWelt', [(side*.345+x*.79, -.3695, .550+z*.79) for x,z in profile],
         .0022, BODY)
    # A single controlled inward tuck is a recognisable scroll, but is only a fine seam.
    tuck = []
    for i in range(18):
        t = i/17
        a = math.radians(210 - 290*t) * side
        radius = .045 * (1-.71*t)
        tuck.append((side*.345 + radius*math.cos(a), -.3700, .550+radius*.82*math.sin(a)))
    tube(name+'_RolledTuck', tuck, .0024, BODY, closed=False)


def select(objs):
    bpy.ops.object.select_all(action='DESELECT')
    for ob in objs:
        ob.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]


def finish(ob):
    select([ob])
    for mod in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method='FIXED', ngon_method='BEAUTY')
    bm.to_mesh(ob.data)
    bm.free()
    bc.smart_uv(ob, angle=72, margin=.018)
    # Fine textile repeats live in actual UVs, so identical PBR survives GLB / FBX.
    if any(m and ('Body' in m.name or 'Cushion' in m.name) for m in ob.data.materials):
        for loop in ob.data.uv_layers.active.data:
            loop.uv *= 2.2
    return ob


def qa(objs):
    mn, mx = bc.world_bounds(objs)
    nonmanifold, welded_nonmanifold, degenerate, total = 0, 0, 0, 0
    for ob in objs:
        ob.data.calc_loop_triangles()
        total += len(ob.data.loop_triangles)
        degenerate += sum(t.area < 1e-12 for t in ob.data.loop_triangles)
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        nonmanifold += sum(not edge.is_manifold for edge in bm.edges)
        # glTF correctly duplicates vertices at UV/material/normal seams. Verify
        # the positional topology separately rather than labelling those seams holes.
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-7)
        welded_nonmanifold += sum(not edge.is_manifold for edge in bm.edges)
        bm.free()
    return {'triangles':total, 'meshes':len(objs), 'materials':len({m.name for o in objs for m in o.data.materials if m}),
            'bounds_min_m':[round(v, 6) for v in mn], 'bounds_max_m':[round(v, 6) for v in mx],
            'dimensions_m':[round(v, 6) for v in mx-mn],
            'all_uv0':all(len(o.data.uv_layers)>0 and len(o.data.uv_layers.active.data)==len(o.data.loops) for o in objs),
            'all_identity_transforms':all(max(abs(o.matrix_world[i][j]-Matrix.Identity(4)[i][j]) for i in range(4) for j in range(4))<1e-6 for o in objs),
            'nonmanifold_edges':nonmanifold, 'position_weld_nonmanifold_edges':welded_nonmanifold,
            'position_weld_epsilon_m':1e-7, 'degenerate_triangles':degenerate}


def studio():
    scene = bpy.context.scene
    bc.setup_studio(scene, bg=(.18,.185,.20), strength=.7, floor=True)
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'AgX - Medium High Contrast'
    return scene


bc.reset_scene()
BODY = painted_material('Body', (.34,.111,.048), .76, 'art/textures/fabric_soft.png', .28)
CUSHION = painted_material('Cushion', (.40,.145,.071), .75, 'art/textures/fabric_soft.png', .25)
WELT = painted_material('Welt', (.50,.32,.19), .79, 'art/textures/fabric_soft.png', .20)
WOOD = painted_material('Timber', (.082,.044,.022), .66,
                        'assets/maps/showhome/kit/textures/oak_boards.png', .28, wood=True)

# Upholstered lower timber frame: a broad apron with small softened shoulders.
# Its shallow silhouette loft carries the structure rather than looking like a loose bolster.
base_outline = roundrect(.708,.650,.058)
base_stations = [(.153,.95),(.166,.994),(.280,1),(.309,.95)]
base_vertices = [(u*scale,v*scale+.002,z) for z,scale in base_stations for u,v in base_outline]
base_faces=[]
for r in range(3):
    for i in range(24):
        j=(i+1)%24
        base_faces.append((r*24+i,r*24+j,(r+1)*24+j,(r+1)*24+i))
base_faces += [tuple(reversed(range(24))),tuple(range(72,96))]
mesh('LowerFrame',base_vertices,base_faces,BODY)

# Left/right outer side panels are broad cloth-covered frames under the arm rolls.
side_outline = roundrect(.615,.335,.048)
for side, label in ((-1,'Right'),(1,'Left')):
    pillow(label+'_SidePanel', side_outline, .068,
           lambda u,v,w,s=side:(s*.344+w,u-.002,.352+v), BODY)
    arm(label+'_Arm', side)

# Rear upholstery shell and a distinct, plump pressure-fitted back cushion.
shell_outline = roundrect(.706,.670,.125)
pillow('BackShell', shell_outline, .035,
       lambda u,v,w:(u,.281+.18*v+w,.593+v+.022*(1-(u/.353)**2)*max(0,(v-.15)/.185)), BODY)
back_outline = roundrect(.585,.514,.089)
pillow('BackCushion', back_outline, .054,
       lambda u,v,w:(u,.228+.18*v+w,.668+v), CUSHION, slight_pinches=True)
tube('BackCushion_Welt', [(u*.97,.228+.18*v*.97-.029,.668+v*.97) for u,v in back_outline],
     .0018, WELT)

# Generous seat: a broad plateau, soft shoulders, and sewn, rounded front corners.
seat_outline = roundrect(.554,.501,.057)
pillow('SeatCushion', seat_outline, .065,
       lambda u,v,w:(u,v-.060,.375+w), CUSHION, slight_pinches=True)
tube('SeatCushion_Welt', [(u*.97,v*.97-.060,.409) for u,v in seat_outline], .0018, WELT)

# Four tapered, slightly splayed timber feet, full tread on Z=0.
for side in (-1,1):
    for front in (-1,1):
        x, y = side*.286, front*.245
        verts = []
        for z, width, depth, sx, sy in ((0,.045,.043,side*.011,front*.010),
                                      (.159,.065,.061,0,0)):
            verts += [(x+sx-width/2,y+sy-depth/2,z),(x+sx+width/2,y+sy-depth/2,z),
                      (x+sx+width/2,y+sy+depth/2,z),(x+sx-width/2,y+sy+depth/2,z)]
        faces = [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
        ob=mesh(f'TimberFoot_{side}_{front}',verts,faces,WOOD,smooth=False)
        bc.add_bevel(ob,.004,1)

ASSET = [o for o in bpy.context.scene.objects if o.type=='MESH']
# Centre the footprint precisely, including the projecting rolled caps, at the origin.
# Final 2.7% depth adjustment makes the brief's .88 x .76 x .95 envelope exact.
mn,mx=bc.world_bounds(ASSET)
centre=(mn+mx)/2
for ob in ASSET:
    for vertex in ob.data.vertices:
        vertex.co.x=(vertex.co.x-centre.x)*(.88/(mx.x-mn.x))
        vertex.co.y=(vertex.co.y-centre.y)*(.76/(mx.y-mn.y))
        vertex.co.z=(vertex.co.z-mn.z)*(.95/(mx.z-mn.z))
for ob in ASSET:
    finish(ob)
BUILT = qa(ASSET)
assert 3000<=BUILT['triangles']<=8000, BUILT
assert BUILT['materials']<=4 and BUILT['all_uv0'] and BUILT['all_identity_transforms']
assert BUILT['nonmanifold_edges']==0 and BUILT['degenerate_triangles']==0, BUILT
print('[ACP] authored',json.dumps(BUILT),flush=True)
scene=studio()
views=('front','three_quarter') if QUICK else ('front','right','back','three_quarter','three_quarter_back','top')
paths=bc.render_views(str(RENDERS),'armchair',objs=ASSET,views=views,res=(720,720) if QUICK else (1000,1000),
                      samples=32,ortho=True,margin=1.08)
bc.contact_sheet(paths,str(RENDERS/'contact_sheet.png'),cols=2 if QUICK else 3)

if QUICK:
    bpy.ops.wm.save_as_mainfile(filepath=str(HERE/'armchair_preview.blend'),compress=True)
    sys.exit(0)

clay=bc.material('_QA_Clay',(.35,.37,.40),rough=.72)
scene.view_layers[0].material_override=clay
bc.render_views(str(RENDERS),'clay',objs=ASSET,views=('three_quarter',),res=(1000,1000),samples=32,ortho=True,margin=1.08)
scene.view_layers[0].material_override=None

# Retain authored parts in the editable blend. Engine export is one mesh/four primitives.
copies=[]
for ob in ASSET:
    cp=ob.copy();cp.data=ob.data.copy()
    bpy.context.scene.collection.objects.link(cp)
    copies.append(cp)
select(copies)
bpy.ops.object.join()
export=bpy.context.active_object
export.name=export.data.name='ACP_Armchair'
select([export])
base=str(HERE/'armchair')
bpy.ops.export_scene.gltf(filepath=base+'.glb',export_format='GLB',use_selection=True,export_apply=True,
                          export_yup=True,export_normals=True,export_tangents=True)
bpy.ops.export_scene.fbx(filepath=base+'.fbx',use_selection=True,axis_forward='-Z',axis_up='Y',
                         apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',use_mesh_modifiers=True,
                         mesh_smooth_type='FACE',path_mode='COPY',embed_textures=True,object_types={'MESH'},bake_anim=False)
bpy.data.objects.remove(export,do_unlink=True)
select(ASSET)
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=base+'.blend',compress=True)

raw=Path(base+'.glb').read_bytes()
length,kind=struct.unpack('<II',raw[12:20])
assert kind==0x4e4f534a
doc=json.loads(raw[20:20+length])
primitives=[p for m in doc['meshes'] for p in m['primitives']]
gltf={'triangles':sum(doc['accessors'][p['indices']]['count']//3 for p in primitives),
      'meshes':len(doc['meshes']),'primitives':len(primitives),'materials':len(doc['materials']),
      'images':len(doc.get('images',[])), 'all_uv0':all('TEXCOORD_0' in p['attributes'] for p in primitives),
      'node_transform_fields':{n.get('name',str(i)):{k:n[k] for k in ('matrix','translation','rotation','scale') if k in n}
                               for i,n in enumerate(doc['nodes'])},
      'extensions_used':doc.get('extensionsUsed',[])}
assert gltf['triangles']==BUILT['triangles'] and gltf['all_uv0']
assert all(not fields for fields in gltf['node_transform_fields'].values()), gltf

QA={'asset':'armchair_procedural','geometry':'Original authored radial pressure lofts and profiles; no imported geometry or generated mesh',
    'front':'-Y in Blender, +Z in glTF','units':'metres','origin':'centre of footprint on ground, all mesh origins world zero',
    'target_dimensions_m':[.88,.76,.95],'seat_surface_height_m':.44,
    'reference_image':'assets/props/_tests/trellis2/inputs/PICK_b_armchair.png (visual proportions only)',
    'texture_sources':sorted(set(TEXTURE_SOURCES)),
    'pbr':'Baked sRGB basecolor; linear ORM R=1, G=roughness, B=0; authored geometry normals; no noise/normal-map shader',
    'built':BUILT,'gltf_document':gltf}
for format in ('glb','fbx'):
    bc.reset_scene()
    if format=='glb':
        bpy.ops.import_scene.gltf(filepath=base+'.glb')
    else:
        bpy.ops.import_scene.fbx(filepath=base+'.fbx')
    imported=[o for o in bpy.context.scene.objects if o.type=='MESH']
    report=qa(imported)
    assert report['triangles']==BUILT['triangles'] and report['all_uv0'],report
    assert max(abs(a-b) for a,b in zip(report['dimensions_m'],BUILT['dimensions_m']))<1e-4,report
    assert report['all_identity_transforms'],report
    assert report['position_weld_nonmanifold_edges']==0 and report['degenerate_triangles']==0,report
    QA['fresh_'+format+'_import']=report
    studio()
    bc.render_views(str(RENDERS),'imported_'+format,objs=imported,views=('three_quarter',),
                    res=(1000,1000),samples=32,ortho=True,margin=1.08)
QA['wall_seconds']=round(time.time()-START,2)
(HERE/'QA.json').write_text(json.dumps(QA,indent=2))
print('[ACP] complete',QA['wall_seconds'],'seconds',flush=True)
