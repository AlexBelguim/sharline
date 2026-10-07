import sys, time
sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc

bc.reset_scene()
gun = bc.material("Gunmetal", (0.05, 0.055, 0.06), rough=0.45, metal=0.8)
acc = bc.material("Accent", (0.0, 0.8, 0.7), emission=(0.0, 0.9, 0.8), emission_strength=4)
poly = bc.material("Polymer", (0.25, 0.22, 0.18), rough=0.7,
                   tex=r"F:/git/val etf/art/_test/tex_test.png", tex_scale=3, tex_mix=0.6)
body = bc.profile_extrude("Receiver", [(-0.15, 0), (0.25, 0), (0.25, 0.06), (0.05, 0.08), (-0.15, 0.07)],
                          0.03, mat=gun, bevel=0.004)
grip = bc.profile_extrude("Grip", [(0.0, 0), (0.04, 0), (0.07, -0.12), (0.03, -0.13)], 0.028,
                          mat=poly, bevel=0.005)
barrel = bc.lathe("Barrel", [(0, 0), (0.008, 0), (0.008, 0.35), (0.0, 0.35)], rot=(90, 0, 0),
                  loc=(0, -0.15, 0.04), mat=gun)
strip = bc.box("Strip", (0.032, 0.12, 0.004), loc=(0, 0.05, 0.075), mat=acc)
bc.uv_all()
bc.setup_studio()
bc.stats()
t = time.time()
bc.render_views(r"F:/git/val etf/art/_test/renders", "eevee", views=("right", "three_quarter"), res=(600, 600))
print("eevee secs", time.time() - t)
t = time.time()
bc.render_views(r"F:/git/val etf/art/_test/renders", "cycles", views=("three_quarter",), res=(600, 600),
                engine="CYCLES", samples=64)
print("cycles secs", time.time() - t)
bc.export_all(r"F:/git/val etf/art/_test/test_gun")
