"""Render the five Job 2 edge studies from the actual exported GLBs, after ground v2 export is ready.

  blender -b --factory-startup -P render_ground_v2.py -- [--quick] [--cpu] [--views kerb_road,paving_lawn]

Every camera is at eye height 1.6 m in the design frame. Preview height blending is restored by ground_blend
because the engine consumes the documented RGBA masks and height maps through its ground shader.
"""
from pathlib import Path
import hashlib
import json
import math
import subprocess
import sys

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
KIT = HERE / "kit"
OUT = KIT / "renders/ground/v2"
sys.path.insert(0, str(HERE))
import lookdev_common as LD

VIEWS = {
    "kerb_road": dict(label="Kerb / road / pavement", camera=(32.5, 21.0, 1.6), target=(30.12, 24.0, 0.08), lens=38,
                      concept="A_showhome_ground_s11.png", crop=(0.65, 0.67, 1.0, 0.96),
                      detail="Chamfered 1 m kerb units, recessed joints, gully, worn road and pavement edge."),
    "paving_lawn": dict(label="Paving / lawn", camera=(26.5, 26.0, 1.6), target=(24.5, 26.8, 0.015), lens=38,
                        concept="A_showhome_ground_s12.png", crop=(0.0, 0.61, 0.35, 0.87),
                        detail="Front-door path: thin grass into dirt, soft moss blend and low edging."),
    "gravel_lawn": dict(label="Gravel / lawn and wall drip strip", camera=(23.5, 24.2, 1.6), target=(21.45, 22.0, 0.012), lens=38,
                        concept="A_showhome_aerial_s12.png", crop=(0.67, 0.63, 0.83, 0.89),
                        detail="House gravel drip strip with steel edging, gravel spill and worn grass margin."),
    "truck_verge": dict(label="Truck verge", camera=(32.7, 17.0, 1.6), target=(32.0, 24.0, 0.15), lens=38,
                        concept="A_showhome_ground_s11.png", crop=(0.33, 0.43, 0.73, 0.86),
                        detail="Tyre wear and soft earth / wet blending beside the removal truck and kerb verge."),
    "construction_edge": dict(label="Construction plot / street", camera=(7.8, 56.9, 1.6), target=(12.0, 60.6, 0.08), lens=38,
                              concept="A_showhome_aerial_s11.png", crop=(0.02, 0.10, 0.29, 0.43),
                              detail="Sand and mud washing over the plot edge, pavement and unfinished street kerb."),
}


def options():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    views = args[args.index("--views") + 1].split(",") if "--views" in args else list(VIEWS)
    assert all(n in VIEWS for n in views), views
    return dict(views=views, quick="--quick" in args, cpu="--cpu" in args)


def import_kit():
    hashes = {}
    for name in ("houses.glb", "ground.glb", "props_placed.glb"):
        path = KIT / name
        if not path.exists():
            raise FileNotFoundError(f"Export {path} first; these studies use real game deliverables.")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        bpy.ops.import_scene.gltf(filepath=str(path))
    return hashes


def mask_report():
    report = []
    for ob in bpy.data.objects:
        if ob.type != "MESH" or not ob.name.startswith(("GND_Ground", "GND_Skirt")):
            continue
        ca = ob.data.color_attributes.active_color
        if ca is None:
            raise AssertionError("Missing ground blend COLOR_0: " + ob.name)
        data = [d.color for d in ca.data]
        mn = [round(min(v[k] for v in data), 5) for k in range(4)]
        mx = [round(max(v[k] for v in data), 5) for k in range(4)]
        report.append(dict(mesh=ob.name, layer=ca.name, count=len(data), minimum=mn, maximum=mx))
    if not report or not any(r["minimum"][3] < 0.99 for r in report):
        raise AssertionError("Ground v2 RGBA masks are not exported yet. Rebuild ground before rendering.")
    return report


def main():
    opts = options()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    OUT.mkdir(parents=True, exist_ok=True)
    hashes = import_kit()
    masks = mask_report()
    import ground_blend as GB
    installer = getattr(GB, "install_preview", None) or GB.setup_preview
    installed = installer()
    print("Ground preview blend installed:", installed)
    cam, sun = LD.setup(quick=opts["quick"], fog=True)
    if opts["cpu"]:
        sc.cycles.device = "CPU"
    cam.data.dof.use_dof = False
    tiles = []
    for name in opts["views"]:
        view = VIEWS[name]
        assert view["camera"][2] == 1.6
        raw = OUT / (name + ".png")
        try:
            LD.render(cam, raw, view["camera"], view["target"], lens=view["lens"],
                      resolution=(960, 540) if opts["quick"] else (1280, 720))
        except RuntimeError as exc:
            if sc.cycles.device != "GPU" or not any(s in str(exc).lower() for s in ("memory", "device", "cuda", "optix")):
                raise
            print("GPU render unavailable; continuing with Cycles CPU:", exc)
            sc.cycles.device = "CPU"
            LD.render(cam, raw, view["camera"], view["target"], lens=view["lens"],
                      resolution=(960, 540) if opts["quick"] else (1280, 720))
        tiles.append(dict(name=name, path=str(raw), **view))
    manifest = dict(frame="Design metres x=east,y=north,z=up; actual GLBs imported at identity",
                    eye_height_m=1.6, sun=dict(azimuth_deg=188, elevation_deg=54, linear_rgb=[1, .84, .66], energy=2.5),
                    world_strength=.65, fog=dict(start_m=80, end_m=420, colour_srgb=[.66, .76, .86]),
                    source_glb_sha256=hashes, masks=masks, tiles=tiles,
                    blend_contract="assets/maps/showhome/kit/ground_blend_contract.json",
                    renderer=sc.render.engine, device=sc.cycles.device)
    (OUT / "render_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    subprocess.run(["python", str(HERE / "compare_ground_v2.py"), str(OUT / "render_manifest.json")], check=True)
    print("GROUND V2 STUDIES COMPLETE:", len(tiles), "views", OUT)


if __name__ == "__main__":
    main()
