"""Build the HALO shield kit from scratch: sprites, meshes, materials, empties, exports, catalog and renders.

Run (absolute paths, the project path contains a space):
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/shields/build_halo.py" -- [--renders all|none|<list>] [--iter vNN] [--no-export]
  <list> = comma-separated subset of: grid,lineup,sil,eye,coverage,underside,char,pickups,turn,parts,lod

Outputs (all in assets/shields/):
  sprites/*.png                         make_sprites.py (system Python + PIL + numpy), run first: the broken-arc
                                        material uses sprites/crack_tile.png
  halo_kit.blend / .glb / .fbx          full kit (every mesh at the halo origin, empties, all materials)
  export/HALO_<Core>.glb/.fbx           4 arcs + Medium/Heavy band + HALO_<Core>_PIP_1..4 + far LOD set per core
  export/HALO_Common.glb/.fbx           tier pip, shared PIP_1..4 empties, power cell, shards
  export/HALO_Pickups.glb/.fbx          the four loot cores
  export/HALO_Materials.glb             swatch quads carrying every material (T1-T4, Off, Broken_T1-T4, Edge, ...)
  armor_catalog.example.json            make_catalog.py (reads game/assets/data/armor.ron + the design JSON and
                                        fails loudly if they disagree)
  renders/                              showcase renders (see NOTES.md for the list)
NOTES.md is hand-written documentation.
"""
import os
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True   # keep __pycache__ out of the asset folder
HERE = r"F:/git/val etf/assets/shields"
sys.path.insert(0, r"F:/git/val etf/tools")
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
ALL_RENDERS = ("grid", "lineup", "sil", "eye", "coverage", "underside", "pickups", "parts", "lod", "turn", "char")


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
def build_kit(crack_path):
    bc.reset_scene()
    M = hl.make_materials(crack_path)
    kit = bc.collection("HALO_Kit")
    cols = {c: bc.collection(f"HALO_{c}", kit) for c in hl.CORES}
    common = bc.collection("HALO_Common", kit)
    pick = bc.collection("HALO_Pickups", kit)
    arc_mats = [M["T1"], M["graphite"], M["edge"]]
    band_mats = [M["graphite"], M["gunmetal"], M["T1"], M["edge"]]
    for core in hl.CORES:
        for zone in hl.ZONES:
            o = hp.build_arc(core, zone, arc_mats, cols[core])
            o["halo_core"] = core
            o["halo_zone"] = zone
            o["halo_slot0"] = "glass: M_HALO_Glass_T<arc tier> covered, _Off uncovered, _Broken_T<tier> broken"
        for w in ("Medium", "Heavy"):
            o = hp.build_band(core, w, band_mats, cols[core])
            o["halo_core"] = core
            o["halo_weight"] = w
            o["halo_slot2"] = "lip glass: M_HALO_Glass_T<highest arc tier>"
        for i, p in enumerate(hp.pip_positions(core)):
            e = bpy.data.objects.new(f"HALO_{core}_PIP_{i + 1}", None)
            e.empty_display_type = "PLAIN_AXES"
            e.empty_display_size = 0.006
            e.location = p
            e["halo_pip_index"] = i + 1
            e["halo_core"] = core
            cols[core].objects.link(e)
        far = bc.collection(f"HALO_{core}_Far", cols[core])
        for o in hp.build_far(core, [M["T1"]], [M["graphite"], M["edge"], M["T1"]], far):
            o["halo_core"] = core
            o["halo_lod"] = "far"
            if "_Glass_" in o.name:
                o["halo_zone"] = o.name.rsplit("_", 1)[1]
            else:
                o["halo_weight"] = o.name.rsplit("_", 1)[1]
            o.hide_set(True)          # viewport only (exports still include them)
    hp.build_pip([M["T1"]], common)
    hp.build_cell([M["T1"], M["graphite"]], common)
    hp.build_shards([M["T1"]], common)
    # shared HALO_PIP_1..4 (spec name): the Bulwark seat, kept as the generic default
    for i, p in enumerate(hp.pip_positions("Bulwark")):
        e = bpy.data.objects.new(f"HALO_PIP_{i + 1}", None)
        e.empty_display_type = "PLAIN_AXES"
        e.empty_display_size = 0.006
        e.location = p
        e["halo_pip_index"] = i + 1
        common.objects.link(e)
    for core in hl.CORES:
        o = hp.build_pickup(core, [M["T1"], M["graphite"], M["bone"]], pick)
        o["halo_core"] = core
        o["halo_slot0"] = "window glass: M_HALO_Glass_T<tier>"
    # material swatches so every material ships in the glTF/FBX library
    sw = bc.collection("HALO_MaterialSwatches", kit)
    keys = ["T1", "T2", "T3", "T4", "off", "B1", "B2", "B3", "B4", "edge", "graphite", "gunmetal", "bone"]
    for i, k in enumerate(keys):
        m = M[k]
        bc.box("HALO_Swatch_" + m.name.replace("M_HALO_", ""), (0.02, 0.002, 0.02),
               loc=(0.5 + i * 0.025, 0.5, 0), col=sw, mat=m, smooth=None)
    bc.uv_all()
    return M


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
    for core in hl.CORES:
        for o in col(f"HALO_{core}_Far"):
            o.hide_set(True)


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
    for core in hl.CORES:
        arcs = sum(tot[f"HALO_{core}_Arc_{z}"] for z in hl.ZONES)
        far = sum(tot[f"HALO_{core}_Far_Glass_{z}"] for z in hl.ZONES)
        print(f"  {core}: arcs {arcs}, +Medium {tot[f'HALO_{core}_Band_Medium']}, "
              f"+Heavy {tot[f'HALO_{core}_Band_Heavy']} | far glass {far} + frame L/M/H "
              + "/".join(str(tot[f'HALO_{core}_Far_Frame_{w}']) for w in ("Light", "Medium", "Heavy")))
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
            "eye": lambda: hr.r_core_read_eyelevel(REN),
            "coverage": lambda: hr.r_coverage(REN) + hr.r_arc_tiers(REN),
            "underside": lambda: hr.r_underside(REN), "pickups": lambda: hr.r_pickups(REN),
            "parts": lambda: hr.r_parts(REN), "lod": lambda: hr.r_far_lod(REN),
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
