"""SOLACE - finish the TRELLIS.2 image-to-3D model (seed 42) into a game-ready, rigged character.

Re-runnable from scratch (raw TRELLIS glb -> finished asset):

  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/characters/solace/build_solace.py" -- [--from X] [--to Y] [--no-renders]

Stages (all run by default, in order; each one saves _work/<stage>.blend so later stages can be re-run alone):
  A  import + normalise (1.68 m, feet on Z=0, centred, facing -Y), weld, drop tiny islands, delete the
     hallucinated box backpack + shoulder fins, patch the coat back, recalc normals, decimate (<= 80k tris)
  B  texture fixes in texel space (Cycles position bake -> numpy): coat back patch inpaint, ivory/sand/charcoal
     recolour, shoulder-emblem area cleared, coral piping restored, face/eye cleanup
  C  procedural parts: Bloom regen module (mount, spine, yoke, LEDs, hub, core, 3 hinged vanes), Bloom emblem
     decal (sand hex patch + three coral petals)
  D  UE5-mannequin-named armature from mesh cross-sections, skinning (heat weights, voxel-proxy fallback),
     rigid parts, cleanup to 4 influences
  E  sockets, export (.blend/.fbx/.glb), Cycles renders, pose tests, contact sheet

Helpers live in sol_lib.py next to this file.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, r"F:/git/val etf/tools")

import sol_lib as S  # noqa: E402

if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    S.main(argv)
