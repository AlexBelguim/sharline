"""Locate stretched edges per pose (review helper)."""
import sys
sys.dont_write_bytecode = True
sys.argv = [sys.argv[0], "--", "none"]
exec(open(r"F:/git/val etf/assets/characters/kestrel/review/render_review.py", encoding="utf-8").read().split("FN = {")[0])
import numpy as np
sc, arm, body, ep = load()
me = body.data
ed = np.zeros(len(me.edges) * 2, int); me.edges.foreach_get("vertices", ed); ed = ed.reshape(-1, 2)
gname = {g.index: g.name for g in body.vertex_groups}
dom = np.array([gname[max(v.groups, key=lambda g: g.weight).group] for v in me.vertices])
reset(arm); rest = edge_stats(body, arm)
L0 = np.linalg.norm(rest[ed[:, 0]] - rest[ed[:, 1]], axis=1)
for pname in ("rifle", "zipline", "stress", "squat"):
    reset(arm); POSES[pname](arm); co = edge_stats(body, arm)
    L = np.linalg.norm(co[ed[:, 0]] - co[ed[:, 1]], axis=1)
    st = (L - L0 > 0.02)
    P(f"== {pname}: edges stretched by >2 cm: {st.sum()}")
    pairs = {}
    for e in np.where(st)[0]:
        a, b = ed[e]
        k = tuple(sorted((dom[a], dom[b])))
        pairs.setdefault(k, []).append(e)
    for k, es in sorted(pairs.items(), key=lambda x: -len(x[1]))[:10]:
        es = np.array(es)
        mid = (rest[ed[es, 0]] + rest[ed[es, 1]]) / 2
        P(f"   {k}: {len(es)} edges, rest-len median {np.median(L0[es])*1000:.1f} mm, posed median {np.median(L[es])*1000:.1f} mm max {L[es].max()*1000:.0f} mm, rest centre {mid.mean(0).round(3)} bbox {mid.min(0).round(3)} {mid.max(0).round(3)}")
