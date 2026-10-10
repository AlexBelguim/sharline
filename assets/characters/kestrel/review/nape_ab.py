"""Review helper: rest vs head pitched down (aim down) seen from a third-person camera behind/above."""
import sys
sys.dont_write_bytecode = True
sys.argv = [sys.argv[0], "--", "none"]
exec(open(r"F:/git/val etf/assets/characters/kestrel/review/render_review.py", encoding="utf-8").read().split("FN = {")[0])
sc, arm, body, ep = load()
bc.setup_studio()
paths = []
for nm, pitch, yaw in (("rest", 0, 0), ("down25", 25, 0), ("down25_yaw35", 25, 35), ("up20", -20, 0)):
    reset(arm)
    if yaw:
        rot_world(arm, "neck_01", (0, 0, 1), yaw * 0.4)
        rot_world(arm, "head", (0, 0, 1), yaw * 0.6)
    if pitch:
        rot_world(arm, "neck_01", (1, 0, 0), pitch * 0.35)
        rot_world(arm, "head", (1, 0, 0), pitch * 0.65)
    camera((0.0, 0.06, 1.45), (0.35, 1, 0.55), radius=0.22, lens=85)
    paths.append(render(OUT + f"nape_{nm}.png", res=(700, 700), samples=48))
reset(arm)
bc.contact_sheet(paths, OUT + "nape_sheet.png", cols=4)
