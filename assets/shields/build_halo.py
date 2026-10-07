"""Build the HALO shield kit from scratch: meshes, materials, empties, exports and showcase renders.

Run (absolute paths, the project path contains a space):
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/shields/build_halo.py" -- [--renders all|none|grid,lineup,sil,coverage,char,pickups,turn,parts]
                                                         [--iter vNN] [--no-export]

Outputs (all in assets/shields/):
  halo_kit.blend / .glb / .fbx          full kit (every mesh at the halo origin, empties, all materials)
  export/HALO_<Core>.glb/.fbx           4 arcs + Medium/Heavy band per core (named nodes)
  export/HALO_Common.glb/.fbx           tier pip, PIP_1..4 empties, power cell, shards
  export/HALO_Pickups.glb/.fbx          the four loot cores
  export/HALO_Materials.glb             swatch quads carrying every material (T1-T4 lit glass, Off, Graphite...)
  sprites/*.png                         made by make_sprites.py (system Python + PIL; called from here)
  renders/                              showcase renders
"""
import os
import shutil
import subprocess
import sys

HERE = r"F:/git/val etf/assets/shields"
sys.path.insert(0, r"F:/git/val etf/tools")
sys.path.insert(0, HERE)

import bpy  # noqa: E402

import blender_common as bc  # noqa: E402
import halo_lib as hl  # noqa: E402
import halo_parts as hp  # noqa: E402

for m in ("halo_lib", "halo_parts"):
    pass

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


# ------------------------------------------------------------------------------------------------ build
def build_kit():
    bc.reset_scene()
    M = hl.make_materials()
    kit = bc.collection("HALO_Kit")
    cols = {c: bc.collection(f"HALO_{c}", kit) for c in hl.CORES}
    common = bc.collection("HALO_Common", kit)
    pick = bc.collection("HALO_Pickups", kit)
    arc_mats = [M["T1"], M["graphite"]]
    band_mats = [M["graphite"], M["gunmetal"]]
    objs = {}
    for core in hl.CORES:
        for zone in hl.ZONES:
            o = hp.build_arc(core, zone, arc_mats, cols[core])
            o["halo_core"] = core
            o["halo_zone"] = zone
            o["halo_slot0"] = "glass: M_HALO_Glass_T<tier> when covered, M_HALO_Glass_Off when not"
            objs[o.name] = o
        for w in ("Medium", "Heavy"):
            o = hp.build_band(core, w, band_mats, cols[core])
            o["halo_core"] = core
            o["halo_weight"] = w
            objs[o.name] = o
    pip = hp.build_pip([M["T1"]], common)
    cell = hp.build_cell([M["T1"], M["graphite"]], common)
    shards = hp.build_shards([M["T1"]], common)
    for i, p in enumerate(hl.PIP_POS):
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
    swatch_mats = [M["T1"], M["T2"], M["T3"], M["T4"], M["off"], M["graphite"], M["gunmetal"], M["bone"]]
    for i, m in enumerate(swatch_mats):
        o = bc.box("HALO_Swatch_" + m.name.replace("M_HALO_", ""), (0.02, 0.002, 0.02),
                   loc=(0.5 + i * 0.025, 0.5, 0), col=sw, mat=m, smooth=None)
    bc.uv_all()
    return M


def export(objs, base):
    os.makedirs(os.path.dirname(base), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=base + ".glb", export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_extras=True)
    bpy.ops.export_scene.fbx(filepath=base + ".fbx", use_selection=True, apply_unit_scale=True,
                             apply_scale_options="FBX_SCALE_ALL", axis_forward="-Z", axis_up="Y",
                             use_mesh_modifiers=True, add_leaf_bones=False, use_custom_props=True)
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
        print(f"  {core}: arcs {arcs}, +Medium {tot[f'HALO_{core}_Band_Medium']}, "
              f"+Heavy {tot[f'HALO_{core}_Band_Heavy']}")
    return tot


# ------------------------------------------------------------------------------------------------ main
def main():
    build_kit()
    tot = report()
    if DO_EXPORT:
        export_all_parts()
    os.makedirs(OUT, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "halo_kit.blend"), compress=True)
    print("SAVED blend")

    if RENDERS == "none":
        return
    # sprites (procedural, PIL) are needed by the hit render
    spr_script = os.path.join(HERE, "make_sprites.py")
    py = shutil.which("python") or shutil.which("py")
    if py and os.path.exists(spr_script):
        try:
            subprocess.run([py, spr_script], check=True, timeout=300)
        except Exception as e:  # sprites are optional for the renders
            print("sprite generation failed:", e)
    import halo_render as hr
    bc.setup_studio()
    hr.kit_visible(False)
    want = set(RENDERS.split(",")) if RENDERS != "all" else {
        "grid", "lineup", "sil", "coverage", "char", "pickups", "turn", "parts"}
    os.makedirs(REN, exist_ok=True)
    made = []
    if "grid" in want:
        made += hr.r_cores_grid(REN)
    if "lineup" in want:
        made += hr.r_weight_lineup(REN)
    if "sil" in want:
        made += hr.r_weight_silhouette_all(REN)
        made += hr.r_weight_eyelevel(REN)
    if "coverage" in want:
        made += hr.r_coverage(REN)
    if "pickups" in want:
        made += hr.r_pickups(REN)
    if "parts" in want:
        made += hr.r_parts(REN)
    if "turn" in want:
        made += hr.r_turnaround(REN)
    if "char" in want:
        made += hr.r_character(REN, SPR)
    if ITER:
        d = os.path.join(REN, "_iterations", ITER)
        os.makedirs(d, exist_ok=True)
        for p in made:
            if os.path.exists(p):
                shutil.copy(p, os.path.join(d, os.path.basename(p)))
    print("DONE", len(made), "renders")


main()
