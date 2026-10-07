"""Build both female base presets side by side, render previews, optionally export.

Run:
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P test_base.py -- [opts]
opts: kes | var (build only one) ; body | head (only those renders) ; export ; eevee ; tag=<suffix>
"""
import json
import os
import sys
import time

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402
import female_base as fb  # noqa: E402

OUT = r"F:/git/val etf/assets/characters/_base"
REN = os.path.join(OUT, "renders")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
only = [a for a in argv if a in ("kes", "var")]
views_only = [a for a in argv if a in ("body", "head")]
tag = next((a.split("=", 1)[1] for a in argv if a.startswith("tag=")), "")
engine = "EEVEE" if "eevee" in argv else "CYCLES"

PRESETS = [
    # key, prefix, height, build, skin, eyes, x offset
    ("kes", "KES", 1.70, 0.0, (0.62, 0.42, 0.33), (0.16, 0.30, 0.26), -0.5),
    ("var", "VAR", 1.76, 1.0, (0.38, 0.22, 0.14), (0.22, 0.12, 0.05), 0.5),
]

bc.reset_scene()
results = {}
t0 = time.time()
for key, prefix, h, b, skin, eye, off in PRESETS:
    if only and key not in only:
        continue
    col = bc.collection(prefix)
    r = fb.build_female_base(prefix=prefix, height=h, build=b, skin=skin, eye_color=eye, col=col)
    for o in [r["body"], r["brows"], r["lashes"], *r["eyes"]]:
        o.location.x += off
    results[key] = (r, off)
print(f"BUILD TIME {time.time() - t0:.1f}s")
bc.stats()
bc.setup_studio()
if "wire" in argv:
    import bpy
    wm = bc.material("_WireMat", (0.02, 0.02, 0.025), rough=0.6)
    for key, (r, off) in results.items():
        w = r["body"].copy()
        w.data = r["body"].data.copy()
        w.name = "_wire_" + key
        bpy.context.scene.collection.objects.link(w)
        m = w.modifiers.new("wf", "WIREFRAME")
        m.thickness = 0.0005
        m.use_replace = True
        w.data.materials.clear()
        w.data.materials.append(wm)
sc = __import__("bpy").context.scene
if "norender" not in argv and ("body" in views_only or not views_only):
    bc.render_views(REN, "base" + tag, views=("front", "right", "three_quarter", "back"), res=(900, 1200),
                    engine=engine, samples=48)
if "norender" not in argv and ("head" in views_only or not views_only):
    for key, (r, off) in results.items():
        hc = list(r["dims"]["head_center"])
        hc[0] += off
        hc[2] -= 0.01
        bc.render_views(REN, f"head_{key}{tag}", views=("front", "three_quarter", "right"), res=(900, 900),
                        engine=engine, samples=48, focus=(hc, 0.165))
if "detail" in argv:
    for key, (r, off) in results.items():
        j = r["joints"]
        hand = [j["hand_L"][0] + off + 0.05, j["hand_L"][1] - 0.01, j["hand_L"][2] - 0.04]
        sh = [j["upperarm_L"][0] + off - 0.03, j["upperarm_L"][1], j["upperarm_L"][2] + 0.02]
        bc.render_views(REN, f"hand_{key}{tag}", views=("front", (0.3, -0.3, 1.0), (0.3, 0.2, -1.0)), res=(700, 700),
                        engine=engine, samples=32, focus=(hand, 0.11))
        bc.render_views(REN, f"shoulder_{key}{tag}", views=("three_quarter", "back"), res=(700, 700),
                        engine=engine, samples=32, focus=(sh, 0.16))
for key, (r, off) in results.items():
    d = dict(r["dims"])
    print(key.upper(), "DIMS", json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()
                                           if not isinstance(v, dict)}, default=str))
    for k, v in d.items():
        if isinstance(v, dict):
            print("   ", k, {a: round(b, 4) for a, b in v.items()})
if "export" in argv:
    import bpy
    for key, (r, off) in results.items():
        objs = [r["body"], r["brows"], r["lashes"], *r["eyes"]]
        for o in objs:
            o.location.x -= off
        others = [o for o in bpy.context.scene.objects if o.type == "MESH" and o not in objs]
        for o in others:
            o.hide_set(True)
        name = "kestrel" if key == "kes" else "varga"
        bc.export_all(os.path.join(OUT, f"female_base_{name}"), objs=objs, fbx=True)
        for o in objs:
            o.location.x += off
        for o in others:
            o.hide_set(False)
