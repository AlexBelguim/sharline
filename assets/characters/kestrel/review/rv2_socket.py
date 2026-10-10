"""Review pass 2: weapon-socket position vs the hand's web (weapon origin convention) in socket-local axes."""
import sys
sys.dont_write_bytecode = True
import bpy
from mathutils import Vector
bpy.ops.wm.open_mainfile(filepath=r"F:/git/val etf/assets/characters/kestrel/kestrel.blend")
arm = bpy.data.objects["KES_Armature"]
for s, S in (("r", "R"), ("l", "L")):
    sock = bpy.data.objects[f"KES_SOCKET_Weapon{S}"]
    M = sock.matrix_world
    b = arm.data.bones
    web = (b[f"thumb_01_{s}"].head_local + b[f"index_01_{s}"].head_local) / 2
    knuck = b[f"middle_01_{s}"].head_local
    wrist = b[f"hand_{s}"].head_local
    inv = M.inverted()
    for nm, p in (("web (thumb_01/index_01 midpoint)", web), ("middle knuckle", knuck), ("wrist", wrist)):
        loc = inv @ (arm.matrix_world @ p)
        print(f"[RV2] Weapon{S}: {nm} in socket local = ({loc.x*100:.1f}, {loc.y*100:.1f}, {loc.z*100:.1f}) cm, dist {loc.length*100:.1f} cm")
