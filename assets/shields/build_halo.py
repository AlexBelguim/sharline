"""Build the HALO shield kit from scratch: sprites, meshes, materials, empties, exports, catalog and renders.

Run (absolute paths, the project path contains a space; paths inside are resolved from this file, so any
checkout works):
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup
      -P "F:/git/val etf/assets/shields/build_halo.py" -- [--renders all|none|<list>] [--iter vNN] [--no-export]
  (one command line)
  <list> = comma-separated subset of: grid,lineup,sil,eye,blind,coverage,underside,pickups,parts,lod,turn,char

Outputs (all in assets/shields/):
  sprites/*.png                         make_sprites.py (system Python + PIL + numpy), run first: the broken-arc
                                        material uses sprites/crack_tile.png
  halo_kit.blend / .glb / .fbx          full kit (every mesh at the halo origin, empties, all materials)
  export/HALO_<Core>.glb/.fbx           six group nodes per core (toggle a whole group in the engine):
                                          _Near    HALO_<Core>_Arc_<Zone> x4 (glass only, swap per arc)
                                          _Frames  HALO_<Core>_Frame_<Light|Medium|Heavy> (graphite + edge of all
                                                   arcs + the weight band; show exactly one)
                                          _Bands   HALO_<Core>_Band_<Medium|Heavy> (spec meshes, band alone)
                                          _Pips    HALO_<Core>_PIP_Centre + centred rows HALO_<Core>_PIP_<n>_<i>
                                          _Cells   HALO_PowerCell_<Core> (the core's own cell silhouette)
                                          _Far     HALO_<Core>_Far_Glass_<Zone> x4 + HALO_<Core>_Far_Frame_<Weight>
  export/HALO_Common.glb/.fbx           tier pip, shared PIP_1..4 empties, generic power cell, shards
  export/HALO_Pickups.glb/.fbx          the four loot cores
  export/HALO_Materials.glb             swatch quads carrying every material (T1-T4, Off, Broken_T1-T4, Edge, ...)
  armor_catalog.example.json            make_catalog.py (reads game/assets/data/armor.ron + the design JSON and
                                        fails loudly if they disagree)
  renders/                              showcase renders (see NOTES.md for the list)
NOTES.md is hand-written documentation.  QA: qa/qa_glb.py (system Python) and qa/qa_blender.py (Blender).
"""
import os
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True   # keep __pycache__ out of the asset folder
HERE = os.path.dirname(os.path.abspath(__file__))                  # works from any checkout (review r2 #10)
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402

import blender_common as bc  # noqa: E402
import halo_lib as hl  # noqa: E402
import halo_parts as hp  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    if name in argv:
        i = argv.index(name)
        return argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else True
    return default


RENDERS = arg("--renders", "all")
ITER = arg("--iter", None)
DO_EXPORT = not arg("--no-export", False)

OUT = HERE
EXP = os.path.join(OUT, "export")
REN = os.path.join(OUT, "renders")
SPR = os.path.join(OUT, "sprites")
ALL_RENDERS = ("grid", "lineup", "sil", "eye", "blind", "coverage", "underside", "pickups", "parts", "lod", "turn",
               "char")


# ------------------------------------------------------------------------------------------------ sprites
def make_sprites():
    spr_script = os.path.join(HERE, "make_sprites.py")
    py = shutil.which("python") or shutil.which("py")
    if py:
        try:
            subprocess.run([py, "-B", spr_script], check=True, timeout=600)
        except Exception as e:
            print("sprite generation failed:", e)
    p = os.path.join(SPR, "crack_tile.png")
    if not os.path.exists(p):
        raise RuntimeError("sprites/crack_tile.png is missing (make_sprites.py needs system Python + PIL + numpy)")
    return p


# ------------------------------------------------------------------------------------------------ build
GLASS_HINT = "glass: M_HALO_Glass_T<arc tier> covered, _Off uncovered, _Broken_T<tier> broken"
LIP_HINT = "lip glass (material M_HALO_Glass_T1 as shipped): swap to M_HALO_Glass_T<highest arc tier>"


def empty(name, col, loc=(0, 0, 0), parent=None, size=0.006, kind="PLAIN_AXES"):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = kind
    e.empty_display_size = size
    e.location = loc
    col.objects.link(e)
    if parent is not None:
        e.parent = parent
    return e


def group(name, col, role, note):
    """Group empty at the halo origin (glTF node with children): the engine toggles a whole group at once
    (review r2 #8: spawning HALO_<Core>.glb#Scene0 used to draw every LOD and both bands at once)."""
    g = empty(name, col, size=0.03, kind="CIRCLE")
    g["halo_group"] = role
    g["halo_note"] = note
    return g


def build_kit(crack_path):
    bc.reset_scene()
    M = hl.make_materials(crack_path)
    kit = bc.collection("HALO_Kit")
    cols = {c: bc.collection(f"HALO_{c}", kit) for c in hl.CORES}
    common = bc.collection("HALO_Common", kit)
    pick = bc.collection("HALO_Pickups", kit)
    work = bc.collection("_HALO_Work")
    arc_mats = [M["T1"], M["graphite"], M["edge"]]
    band_mats = [M["graphite"], M["gunmetal"], M["T1"], M["edge"]]
    frame_mats = {"Light": [M["graphite"], M["edge"]],
                  "Medium": [M["graphite"], M["edge"], M["T1"]],
                  "Heavy": [M["graphite"], M["edge"], M["gunmetal"], M["T1"]]}
    for core in hl.CORES:
        col = cols[core]
        g_near = group(f"HALO_{core}_Near", col, "near",
                       "near arcs (glass only, swap per arc); show with exactly ONE HALO_<Core>_Frame_<weight>")
        g_frame = group(f"HALO_{core}_Frames", col, "frames",
                        "pick ONE per weight class: graphite + edge of all 4 arcs (+ the weight band)")
        g_band = group(f"HALO_{core}_Bands", col, "bands",
                       "spec meshes: the weight band alone (already inside Frame_Medium/Heavy). Alternative "
                       "assembly: Frame_Light + Band_<weight>. Never with Frame_Medium/Heavy")
        g_pips = group(f"HALO_{core}_Pips", col, "pips",
                       "tier pip seats: n pips at PIP_<n>_1..PIP_<n>_<n> (centred row), n = highest arc tier")
        g_cells = group(f"HALO_{core}_Cells", col, "cells",
                        "orbiting power cell of this core (1/2/3 per weight class)")
        g_far = group(f"HALO_{core}_Far", col, "far",
                      "far LOD (> 20 m): 4 glass arcs + ONE Far_Frame_<weight>; replaces Near + Frames")
        # arcs: one closed shell each, split by material (glass stays per arc, the frame parts are merged)
        frame_parts = []
        for zone in hl.ZONES:
            full = hp.build_arc(core, zone, arc_mats, work)
            full.name = full.data.name = f"_full_{core}_{zone}"
            arc = hl.split_object(full, [M["T1"]], f"HALO_{core}_Arc_{zone}", col)
            arc.parent = g_near
            arc["halo_core"] = core
            arc["halo_zone"] = zone
            arc["halo_slot0"] = GLASS_HINT
            frame_parts.append(hl.split_object(full, [M["graphite"], M["edge"]], f"_frame_{core}_{zone}", work))
            bpy.data.objects.remove(full, do_unlink=True)
        bands = {}
        for w in ("Medium", "Heavy"):
            o = hp.build_band(core, w, band_mats, col)
            o.parent = g_band
            o["halo_core"] = core
            o["halo_weight"] = w
            o["halo_lip"] = LIP_HINT
            bands[w] = o
        for w in ("Light", "Medium", "Heavy"):
            parts = frame_parts + ([bands[w]] if w in bands else [])
            o = hl.merge_objects(parts, f"HALO_{core}_Frame_{w}", frame_mats[w], col)
            o.parent = g_frame
            o["halo_core"] = core
            o["halo_weight"] = w
            if w != "Light":
                o["halo_lip"] = LIP_HINT
        for o in frame_parts:
            bpy.data.objects.remove(o, do_unlink=True)
        # pips: a centre seat plus one centred row per count (review r2 #3)
        e = empty(f"HALO_{core}_PIP_Centre", col, hp.pip_centre(core), g_pips)
        e["halo_core"] = core
        e["halo_pip_spacing_m"] = hp.PIP_SPACING
        for n in range(1, 5):
            for i, p in enumerate(hp.pip_positions(core, n)):
                e = empty(f"HALO_{core}_PIP_{n}_{i + 1}", col, p, g_pips)
                e["halo_core"] = core
                e["halo_pip_count"] = n
                e["halo_pip_index"] = i + 1
        o = hp.build_core_cell(core, [M["T1"], M["graphite"]], col)
        o.parent = g_cells
        o["halo_core"] = core
        o["halo_slot0"] = "glass: M_HALO_Glass_T<highest arc tier>"
        for o in hp.build_far(core, [M["T1"]], [M["graphite_far"], M["edge"], M["T1"]], col):
            o.parent = g_far
            o["halo_core"] = core
            o["halo_lod"] = "far"
            if "_Glass_" in o.name:
                o["halo_zone"] = o.name.rsplit("_", 1)[1]
            else:
                o["halo_weight"] = o.name.rsplit("_", 1)[1]
    bpy.data.collections.remove(work)
    hp.build_pip([M["T1"]], common)
    hp.build_cell([M["T1"], M["graphite"]], common)
    hp.build_shards([M["T1"]], common)
    # shared HALO_PIP_1..4 (spec name): the 4-pip row on the Bulwark seat, kept as the generic default
    for i, p in enumerate(hp.pip_positions("Bulwark", 4)):
        e = empty(f"HALO_PIP_{i + 1}", common, p)
        e["halo_pip_index"] = i + 1
    for core in hl.CORES:
        o = hp.build_pickup(core, [M["T1"], M["graphite"], M["bone"]], pick)
        o["halo_core"] = core
        o["halo_slot0"] = "window glass: M_HALO_Glass_T<tier>"
    # material swatches so every material ships in the glTF/FBX library
    sw = bc.collection("HALO_MaterialSwatches", kit)
    keys = ["T1", "T2", "T3", "T4", "off", "B1", "B2", "B3", "B4", "edge", "graphite", "graphite_far", "gunmetal",
            "bone"]
    for i, k in enumerate(keys):
        m = M[k]
        bc.box("HALO_Swatch_" + m.name.replace("M_HALO_", ""), (0.02, 0.002, 0.02),
               loc=(0.5 + i * 0.025, 0.5, 0), col=sw, mat=m, smooth=None)
    bc.uv_all()
    viewport_tidy()
    return M


def viewport_tidy():
    """halo_kit.blend opens showing one clean Heavy halo per core (near arcs + Frame_Heavy + pips + cell).
    Viewport only: exports unhide what they export."""
    for core in hl.CORES:
        for o in bpy.data.collections[f"HALO_{core}"].all_objects:
            hide = (o.name.startswith((f"HALO_{core}_Far", f"HALO_{core}_Band_"))
                    or o.name in (f"HALO_{core}_Frame_Light", f"HALO_{core}_Frame_Medium"))
            o.hide_set(hide)


def export(objs, base):
    os.makedirs(os.path.dirname(base), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=base + ".glb", export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_extras=True)
    bpy.ops.export_scene.fbx(filepath=base + ".fbx", use_selection=True, apply_unit_scale=True,
                             apply_scale_options="FBX_SCALE_ALL", axis_forward="-Z", axis_up="Y",
                             use_mesh_modifiers=True, add_leaf_bones=False, use_custom_props=True,
                             path_mode="COPY", embed_textures=True)
    print("EXPORTED", base)


def export_all_parts():
    col = lambda n: [o for o in bpy.data.collections[n].all_objects]  # noqa: E731
    for core in hl.CORES:
        export(col(f"HALO_{core}"), os.path.join(EXP, f"HALO_{core}"))
    export(col("HALO_Common"), os.path.join(EXP, "HALO_Common"))
    export(col("HALO_Pickups"), os.path.join(EXP, "HALO_Pickups"))
    export(col("HALO_MaterialSwatches"), os.path.join(EXP, "HALO_Materials"))
    every = [o for o in bpy.data.collections["HALO_Kit"].all_objects]
    export(every, os.path.join(OUT, "halo_kit"))
    viewport_tidy()


def report():
    print("=== TRI COUNTS ===")
    dg = bpy.context.evaluated_depsgraph_get()
    tot = {}
    for o in sorted(bpy.data.collections["HALO_Kit"].all_objects, key=lambda o: o.name):
        if o.type != "MESH":
            continue
        me = o.evaluated_get(dg).to_mesh()
        t = sum(len(p.vertices) - 2 for p in me.polygons)
        o.evaluated_get(dg).to_mesh_clear()
        tot[o.name] = t
        print(f"  {t:>6}  {o.name}")
    W = ("Light", "Medium", "Heavy")
    for core in hl.CORES:
        arcs = sum(tot[f"HALO_{core}_Arc_{z}"] for z in hl.ZONES)
        far = sum(tot[f"HALO_{core}_Far_Glass_{z}"] for z in hl.ZONES)
        cell = tot[f"HALO_PowerCell_{core}"]
        near = {w: arcs + tot[f"HALO_{core}_Frame_{w}"] + cell * hl.WEIGHT[w]["cells"] for w in W}
        print(f"  {core}: arc glass {arcs} + frame L/M/H " + "/".join(str(tot[f'HALO_{core}_Frame_{w}']) for w in W)
              + f" | bands M/H {tot[f'HALO_{core}_Band_Medium']}/{tot[f'HALO_{core}_Band_Heavy']}"
              f" | far glass {far} + frame L/M/H "
              + "/".join(str(tot[f'HALO_{core}_Far_Frame_{w}']) for w in W)
              + f" | cell {cell} | per halo with cells L/M/H " + "/".join(str(near[w]) for w in W))
        for w in W:
            fo = bpy.data.objects[f"HALO_{core}_Frame_{w}"]
            used = {p.material_index for p in fo.data.polygons}
            print(f"    draws {w}: 4 arc glass + {len(used)} frame + {hl.WEIGHT[w]['cells']} cells x 2"
                  f" = {4 + len(used) + 2 * hl.WEIGHT[w]['cells']} (+ up to 4 instanced pips)")
    return tot


# ------------------------------------------------------------------------------------------------ main
def main():
    crack = make_sprites()
    build_kit(crack)
    report()
    if DO_EXPORT:
        export_all_parts()
    os.makedirs(OUT, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0   # no halo_kit.blend1 backups
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "halo_kit.blend"), compress=True)
    print("SAVED blend")

    import make_catalog   # armor_catalog.example.json (plain Python, cross-checked against the game data)
    make_catalog.main()
    if RENDERS == "none":
        return
    import halo_render as hr
    bc.setup_studio()
    hr.kit_visible(False)
    want = set(RENDERS.split(",")) if RENDERS != "all" else set(ALL_RENDERS)
    os.makedirs(REN, exist_ok=True)
    made = []
    jobs = {"grid": lambda: hr.r_cores_grid(REN), "lineup": lambda: hr.r_weight_lineup(REN),
            "sil": lambda: hr.r_weight_silhouette_all(REN) + hr.r_weight_eyelevel(REN),
            "eye": lambda: hr.r_core_read_eyelevel(REN), "blind": lambda: hr.r_core_blind(REN),
            "coverage": lambda: hr.r_coverage(REN) + hr.r_arc_tiers(REN) + hr.r_arc_states_range(REN),
            "underside": lambda: hr.r_underside(REN), "pickups": lambda: hr.r_pickups(REN),
            "parts": lambda: hr.r_parts(REN), "lod": lambda: hr.r_far_lod(REN) + hr.r_far_lod_switch(REN),
            "turn": lambda: hr.r_turnaround(REN), "char": lambda: hr.r_character(REN, SPR)}
    for k in ALL_RENDERS:
        if k in want:
            made += jobs[k]()
    if ITER:
        d = os.path.join(REN, "_iterations", ITER)
        os.makedirs(d, exist_ok=True)
        for p in made:
            if os.path.exists(p):
                shutil.copy(p, os.path.join(d, os.path.basename(p)))
    print("DONE", len(made), "renders")


main()
