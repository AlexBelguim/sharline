"""Review pass 2b: localise suspicious weights (read-only)."""
import sys
sys.dont_write_bytecode = True
exec(open(r"F:/git/val etf/assets/characters/kestrel/review/rv2_weights.py", encoding="utf-8").read().split('P("=== far-field')[0])

def near_seg(n):
    b = arm.data.bones[n]
    return seg_dist(co, np.array(b.head_local), np.array(b.tail_local))

x, y, z = co[:, 0], co[:, 1], co[:, 2]
P("=== strong far weights (w>0.3 and >0.15 m from the bone; not head/spine/pelvis)")
for n in names:
    if n in ("root", "pelvis", "spine_01", "spine_02", "spine_03", "head", "neck_01"):
        continue
    d = near_seg(n)
    m = (W[:, bi[n]] > 0.3) & (d > 0.15)
    if m.sum() == 0:
        continue
    # cluster by coarse 5 cm grid
    keys = np.floor(co[m] / 0.05).astype(int)
    u, c = np.unique(keys, axis=0, return_counts=True)
    top = np.argsort(-c)[:4]
    P(f"{n:12s} {m.sum():5d} verts; densest 5cm cells (centre, count): " + "; ".join(f"{((u[i] + 0.5) * 0.05).round(3)} x{c[i]}" for i in top))

P("=== forearm weights on verts that are closer to the spine than to the upper arm (torso side)")
sp = seg_dist(co, np.array(arm.data.bones['spine_02'].head_local), np.array(arm.data.bones['spine_03'].tail_local))
for s in ("l", "r"):
    ua = near_seg(f"upperarm_{s}")
    la = near_seg(f"lowerarm_{s}")
    m = (W[:, bi[f"lowerarm_{s}"]] > 0.1) & (sp < ua) & (sp < la)
    P(f"lowerarm_{s}: {m.sum()} torso-side verts with w>0.1 (max {W[m, bi[f'lowerarm_{s}']].max() if m.any() else 0:.2f}); "
      f"bbox {co[m].min(0).round(3) if m.any() else '-'} .. {co[m].max(0).round(3) if m.any() else '-'}")
    m2 = (W[:, bi[f"upperarm_{s}"]] > 0.2) & (np.abs(x) < 0.12)
    P(f"upperarm_{s}: {m2.sum()} verts with |x|<0.12 and w>0.2 (max {W[m2, bi[f'upperarm_{s}']].max() if m2.any() else 0:.2f}); "
      f"bbox {co[m2].min(0).round(3) if m2.any() else '-'} .. {co[m2].max(0).round(3) if m2.any() else '-'}")

P("=== cross-leg weights (thigh_l on x<-0.03 / thigh_r on x>0.03, w>0.2)")
for s, sgn in (("l", 1), ("r", -1)):
    m = (W[:, bi[f"thigh_{s}"]] > 0.2) & (sgn * x < -0.03)
    P(f"thigh_{s}: {m.sum()} verts on the other leg's side (max w {W[m, bi[f'thigh_{s}']].max() if m.any() else 0:.2f}); "
      f"bbox {co[m].min(0).round(3) if m.any() else '-'} .. {co[m].max(0).round(3) if m.any() else '-'}")

def region(label, mask):
    idx = np.where(mask)[0]
    tot = W[idx].sum(0)
    order = np.argsort(-tot)[:6]
    P(f"{label}: {len(idx)} verts; " + ", ".join(f"{names[i]} mean {W[idx, i].mean():.2f} max {W[idx, i].max():.2f}" for i in order if tot[i] > 0))
region("holster (-0.30<x<-0.17, 0.60<z<0.85)", (x > -0.30) & (x < -0.17) & (z > 0.60) & (z < 0.85))
region("belt pouch L (0.10<x<0.26, y<-0.03, 0.88<z<1.02)", (x > 0.10) & (x < 0.26) & (y < -0.03) & (z > 0.88) & (z < 1.02))
region("knee pad L (0.1<x<0.25, y<-0.04, 0.42<z<0.58)", (x > 0.1) & (x < 0.25) & (y < -0.04) & (z > 0.42) & (z < 0.58))
region("collar front (|x|<0.06, y<-0.06, 1.40<z<1.50)", (np.abs(x) < 0.06) & (y < -0.06) & (z > 1.40) & (z < 1.50))
