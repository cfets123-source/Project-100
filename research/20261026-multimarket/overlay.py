"""QQQ at full size plus GLD added on top (extra risk, not split)."""
import os, sys
sys.argv = ["x"]; exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "analyze.py")).read().split('print("== standalone')[0])
def overlay(wg):
    out = {}
    for k in common:
        q, g = P["QQQ"][k], P["GLD"][k]; n = min(len(q["c"]), len(g["c"]))
        f = lambda key: [q[key][i] * q["scale"] + wg * g[key][i] * g["scale"] for i in range(n)]
        c, x, w = f("c"), f("x"), f("w")
        out[k] = {"c": c, "x": x, "w": w, "end": c[-1], "flat": all(abs(e) < 1e-12 for e in c), "scale": 1.0}
    return out
for wg in (0.25, 0.5):
    pd = overlay(wg)
    print(V.score(pd, inn(common, DEV), "QQQ+%.2fGLD DEV" % wg)[0]); print(V.score(pd, inn(common, CONF), "QQQ+%.2fGLD CONF" % wg)[0], flush=True)
