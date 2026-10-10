"""SOLACE - finish the TRELLIS.2 image-to-3D model (seed 42) into a game-ready, rigged character.

Re-runnable from scratch (raw TRELLIS glb -> finished asset):

  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup
      -P "F:/git/val etf/assets/characters/solace/build_solace.py" -- [--from A] [--to E] [--no-renders] [--quick]

Stages (all run by default; each saves _work/<stage>.blend so later stages can be re-run alone with --from):
  A  sol_lib     import + normalise (1.68 m, feet on Z=0, centred, facing -Y), weld, drop bits, cull the hidden
                 inner sheet of the double-walled TRELLIS shell (face-ID renders from 300+ views), carve the
                 hallucinated box backpack + shoulder fins and rebuild the coat back / shoulder caps
                 (constrained-Delaunay membrane patches), rebuild the eye zones (TRELLIS lash-smear ridge), cut out
                 the TRELLIS heal drone + antenna and patch the hip (SOL_Drone replaces it), close pin-holes
  B  sol_tex     texel-space texture fixes (Cycles position/normal bakes -> numpy): skin regrade, pants -> sand,
     sol_face    pouch -> sand, hair de-metalled, old shoulder mark painted out, new ORM; a 1024^2 front-projected
                 face texture with clean painted eyes / brows / lips (M_SOL_Face)
  N  sol_pose    rest-pose normalisation: a temporary rig aims the limbs at Kestrel's rest directions (shared
                 animation set), levels the shoulders and squares the stance; the deformation becomes the new rest
                 shape of SOL_Body
  C  sol_parts   Bloom regen module (mount, spine, yoke + LEDs, hub + glow ring, glowing core) + 3 hinged vanes
                 (bud leans back 7 deg, coral edge bands), the procedural heal drone SOL_Drone (separate object),
                 harness straps, drone dock cradle, Bloom emblem (sand hex + 3 coral petals) on her LEFT upper arm
  D  sol_joints  UE5-mannequin armature from mesh cross-sections with Kestrel's bone conventions (spine curve,
     sol_rig     clavicle line, rolls); heat weights with the voxel-proxy fallback; weight rules (head/hair rigid,
                 ponytail blend, coat-tail pelvis/thigh blend, bracer/pouch rigid, no leg weight above the belt, no
                 cross-side weights, fused finger pairs tied); Bloom parented to spine_03 (vanes are its children)
  E  sol_out     sockets (SOL_Drone is a child of SOL_SOCKET_DroneDock), export solace.blend / .glb / .fbx,
                 Cycles renders, pose tests, contact sheets
Stage order: A B N C D E (--from / --to take these letters).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, r"F:/git/val etf/tools")

import bpy  # noqa: E402
import numpy as np  # noqa: E402

import sol_lib as S  # noqa: E402

STAGES = "ABNCDE"


def main(argv):
    start = argv[argv.index("--from") + 1] if "--from" in argv else "A"
    stop = argv[argv.index("--to") + 1] if "--to" in argv else "E"
    renders = "--no-renders" not in argv
    quick = "--quick" in argv
    run = [s for s in STAGES if STAGES.index(start) <= STAGES.index(s) <= STAGES.index(stop)]
    if start != "A":
        S.load_work(STAGES[STAGES.index(start) - 1])
    for st in run:
        S.log(f"===== stage {st}")
        if st == "A":
            S.stage_a(quick=quick)
        elif st == "B":
            S.stage_b(S.body())
        elif st == "N":
            import sol_pose as PN
            PN.stage_n()
        elif st == "C":
            import sol_parts as P
            P.stage_c()
        elif st == "D":
            import sol_rig as R
            arm, J = R.stage_d()
            np.save(os.path.join(S.WORK, "joints.npy"), J, allow_pickle=True)
        elif st == "E":
            stage_e(renders)
            continue
        S.save_work(st)
    S.log("done")


def stage_e(renders):
    import sol_out as O
    import blender_common as bc
    J = np.load(os.path.join(S.WORK, "joints.npy"), allow_pickle=True).item()
    arm = bpy.data.objects["SOL_Armature"]
    if not any(o.name.startswith("SOL_SOCKET_") for o in bpy.data.objects):
        O.make_sockets(arm, J, bpy.data.objects["SOL_Bloom"], bpy.data.objects.get("SOL_Drone"))
    tot = 0
    for o in O.export_objects():
        if o.type == "MESH":
            n = sum(len(p.vertices) - 2 for p in o.data.polygons)
            tot += n
            S.log(f"  {o.name}: {n} tris")
    S.log(f"TOTAL TRIS {tot}; bones {len(arm.data.bones)}")
    base = os.path.join(S.OUT, "solace")
    S.save_work("E")
    O.export_all(base)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=base + ".blend", compress=True)
    S.log("saved", base + ".blend")
    if renders:
        rd = S.RENDERS
        bc.setup_studio()
        p_beauty = O.beauty(rd)
        p_head = O.head_closeups(rd)
        p_bloom = O.bloom_closeups(rd)
        p_pose = O.pose_tests(rd, J=J)
        O.contact(p_beauty, os.path.join(rd, "solace_sheet.png"), 3)
        O.contact(p_beauty + p_head + p_bloom + p_pose, os.path.join(rd, "contact_sheet.png"), 6)
        O.contact(p_pose, os.path.join(rd, "pose_sheet.png"), 5)
        O.contact(p_bloom, os.path.join(rd, "bloom_sheet.png"), 3)
        O.silhouettes(rd)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    main(argv)
