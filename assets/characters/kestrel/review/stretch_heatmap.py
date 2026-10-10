"""Review helper: per-vertex stretch heat map (red = edges stretched >2x / torn webs) for key poses + grip-web offset."""
import sys
sys.dont_write_bytecode = True
sys.argv = [sys.argv[0], "--", "none"]
exec(open(r"F:/git/val etf/assets/characters/kestrel/review/render_review.py", encoding="utf-8").read().split("FN = {")[0])
import numpy as np


def heat_material():
    m = bpy.data.materials.new("_heat")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    att = nt.nodes.new("ShaderNodeAttribute"); att.attribute_name = "stretch"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.75, 0.75, 0.78, 1)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (1.0, 0.0, 0.0, 1)
    e = ramp.color_ramp.elements.new(0.35); e.color = (1.0, 0.85, 0.0, 1)
    bsdf = nt.nodes.new("ShaderNodeBsdfDiffuse")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(att.outputs["Fac"], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], bsdf.inputs[0])
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    return m


sc, arm, body, ep = load()
bc.setup_studio(floor=True)
me = body.data
ed = np.zeros(len(me.edges) * 2, int); me.edges.foreach_get("vertices", ed); ed = ed.reshape(-1, 2)
reset(arm); rest = edge_stats(body, arm)
L0 = np.linalg.norm(rest[ed[:, 0]] - rest[ed[:, 1]], axis=1)
attr = me.attributes.new("stretch", "FLOAT", "POINT")
hm = heat_material()
body.material_slots[0].material = hm


def head_down(a):
    rot_world(a, "neck_01", (1, 0, 0), 10)
    rot_world(a, "head", (1, 0, 0), 25)


shots = {
    "rifle": (POSES["rifle"], [("front34", (0.5, -1, 0.3), (0.0, -0.05, 1.2), 0.32), ("her_right_low", (-1, -0.5, -0.35), (-0.15, 0.0, 1.2), 0.3), ("back", (-0.4, 1, 0.3), (0.0, 0.1, 1.2), 0.38)]),
    "head_down": (head_down, [("back34", (0.5, 1, 0.35), (0.0, 0.05, 1.42), 0.2)]),
    "zipline": (POSES["zipline"], [("front34", (0.5, -1, 0.2), (0.0, 0.0, 1.35), 0.42)]),
}
for pname, (fn, views) in shots.items():
    reset(arm); fn(arm)
    co = edge_stats(body, arm)
    L = np.linalg.norm(co[ed[:, 0]] - co[ed[:, 1]], axis=1)
    r = np.clip((L / np.maximum(L0, 1e-6) - 1.0) / 2.0, 0, 1)   # 0 = unchanged, 1 = 3x length
    r[(L - L0) < 0.003] = 0
    v = np.zeros(len(me.vertices))
    np.maximum.at(v, ed[:, 0], r); np.maximum.at(v, ed[:, 1], r)
    attr.data.foreach_set("value", v)
    me.update()
    for vn, d, c, rad in views:
        camera(c, d, radius=rad, lens=85)
        render(OUT + f"heat_{pname}_{vn}.png", res=(800, 800), samples=24)
reset(arm)

# grip web offset in the socket frame
for s in ("r", "l"):
    sock = bpy.data.objects[f"KES_SOCKET_Weapon{s.upper()}"]
    M = sock.matrix_world
    b = arm.data.bones
    web = (b[f"thumb_02_{s}"].head_local + b[f"index_01_{s}"].head_local) / 2
    loc = M.inverted() @ web
    P(f"hand_{s}: web point (thumb MCP/index MCP midpoint) {tuple(round(x, 3) for x in web)}; in socket frame x {loc.x*100:.1f} cm, y {loc.y*100:.1f} cm (-y = forward), z {loc.z*100:.1f} cm (+z = thumb side); distance {(web - M.translation).length*100:.1f} cm")
