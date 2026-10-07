"""Transparent ortho side + top renders of the full default loadout (Warden exports + other agents' default
optic_sniper and bipod, read-only) for 64/128 px silhouette checks. Writes review/renders/silfull_*.png"""
import os, sys, math
import bpy
from mathutils import Matrix, Vector
sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc
D = r"F:/git/val etf/assets/weapons/vk50_warden"; ATT = r"F:/git/val etf/assets/weapons/attachments"
OUT = os.path.join(D, "review", "renders")
bpy.ops.wm.read_factory_settings(use_empty=True)
bc.setup_studio()
def imp(p, at=None):
    b = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=p)
    n = [o for o in bpy.data.objects if o not in b]
    if at is not None:
        for r in [o for o in n if o.parent is None]:
            r.matrix_world = Matrix.Translation(at) @ r.matrix_world
    bpy.context.view_layer.update(); return n
g = {o.name: o for o in imp(os.path.join(D, "warden_default.glb"))}
imp(os.path.join(ATT, "optics", "ATT_optic_sniper.glb"), g["WARDEN_SOCKET_Optic"].matrix_world.translation.copy())
imp(os.path.join(ATT, "tactical", "ATT_bipod.glb"), g["WARDEN_SOCKET_Under"].matrix_world.translation.copy())
sc = bpy.context.scene
bc.setup_cycles_gpu(sc, 8)
sc.render.film_transparent = True
sc.render.image_settings.color_mode = "RGBA"
cd = bpy.data.cameras.new("_c"); cam = bpy.data.objects.new("_c", cd); sc.collection.objects.link(cam); sc.camera = cam
cd.type = "ORTHO"
for nm, loc, rot, scale, res in (("side", (2.0, -0.39, 0.0), (math.radians(90), 0, math.radians(90)), 1.50, (1500, 600)),
                                 ("top", (0, -0.39, 2.0), (0, 0, math.radians(90)), 1.50, (1500, 400)),
                                 ("front", (0, -3.0, 0.0), (math.radians(90), 0, 0), 0.45, (600, 600))):
    cam.location = loc; cam.rotation_euler = rot; cd.ortho_scale = scale
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = os.path.join(OUT, f"silfull_{nm}_raw.png")
    bpy.ops.render.render(write_still=True)
