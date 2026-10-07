"""KESTREL - finish the TRELLIS.2 image-to-3D model into a game-ready, rigged character.

Re-runnable from scratch (raw TRELLIS glb -> finished asset):

  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/characters/kestrel/build_kestrel.py" -- [--no-renders] [--quick]

Stages (all run by default, in order):
  A  import + normalise (1.70 m, feet on Z=0, centred, facing -Y) + clean-up (weld, loose bits, holes, the stray
     wire "glasses arm", the opaque baked lens bulge) + careful decimation (head/hands protected)
  B  texture fixes in texel space: Cycles bakes of object-space position/normal maps, then masks/clones/inpaint in
     numpy (brow smear, cheek streak, left eye rebuilt as a mirror of the right eye, brows, gloves, collar piping,
     jet-pack glow rings) and a final Cycles bake of the hair-tip teal dye (mix material -> new base colour)
  C  eyepiece: separate teal hex lens (glass) + emissive rim + strap + earpiece
  D  UE5-mannequin-named armature from mesh cross-section analysis, skinning (heat weights on a voxel proxy,
     transferred), rigid parts, cleanup to 4 influences
  E  sockets, materials, export (.blend/.glb/.fbx), renders, pose tests, contact sheet

Helpers live in kes_lib.py next to this file.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, r"F:/git/val etf/tools")

import kes_lib as K  # noqa: E402

if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    K.main(argv)
