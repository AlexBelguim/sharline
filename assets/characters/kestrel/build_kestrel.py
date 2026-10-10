"""KESTREL - finish the TRELLIS.2 image-to-3D model into a game-ready, rigged character.

Re-runnable from scratch (raw TRELLIS glb -> finished asset):

  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/characters/kestrel/build_kestrel.py" -- [--from X] [--to Y] [--no-renders]

Stages (all run by default, in order; each saves _work/<stage>.blend so later stages can be re-run alone):
  A  import + normalise (1.70 m, feet on Z=0, centred, facing -Y) + clean-up (weld, loose bits, the stray wire
     "glasses arm", hole fill, temple creases) + careful decimation (head/hands protected)          kes_lib.py
  B  texture fixes in object space: Cycles bakes of position/normal maps, face repaint on a front-projected canvas
     (eyes, brows, the baked strap, her left eye under the new lens), misc readability fixes, normal/AO clean-up,
     Cycles AO bake, and the Cycles hair-tip teal dye bake                     kes_tex.py, kes_face.py, kes_fix.py
  C  eyepiece: teal hex glass lens + emissive rim + graphite housing + straps + earpiece          kes_eyepiece.py
  D  UE5-mannequin-named armature from mesh cross-sections, skinning (heat weights on a voxel proxy, transferred),
     rigid parts, cleanup to 4 influences                                                  kes_rig.py, kes_skin.py
  E  sockets, export (.blend/.glb/.fbx), renders, pose tests, contact sheet                          kes_export.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, r"F:/git/val etf/tools")

import kes_lib as K  # noqa: E402

STAGES = "ABCDE"


def main(argv):
    start = argv[argv.index("--from") + 1] if "--from" in argv else "A"
    stop = argv[argv.index("--to") + 1] if "--to" in argv else "E"
    renders = "--no-renders" not in argv
    prev = None
    for st in STAGES:
        if not (start <= st <= stop):
            prev = st
            continue
        if st == start and st != "A":
            K.load_work(prev)
        K.log(f"===== stage {st}")
        if st == "A":
            K.stage_a_import_clean()
        elif st == "B":
            import kes_tex
            obj = K.body()
            imgs = kes_tex.stage_b_textures(obj)
            kes_tex.make_body_material(obj, *imgs)
            for im in ("KES_BaseColor_src", "KES_Normal_src", "KES_ORM_src"):
                if im in K.bpy.data.images:
                    K.bpy.data.images.remove(K.bpy.data.images[im])
            for m in list(K.bpy.data.materials):
                if m.users == 0:
                    K.bpy.data.materials.remove(m)
        elif st == "C":
            import kes_eyepiece
            kes_eyepiece.build_eyepiece()
        elif st == "D":
            import kes_skin
            kes_skin.build_rig()
        elif st == "E":
            import kes_export
            kes_export.finish(renders_on=renders)
        K.save_work(st)
        prev = st
    K.log("finished")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
