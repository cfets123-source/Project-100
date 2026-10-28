import random, sys, time
sys.path.insert(0, '.')
import ladder as L
days = L.load('/home/claude/data/qqq/noise_days.pkl'); keys = sorted(days)
H, N = 756, 400
def go(name, pol, d=days, k=keys, seed=1, h=H):
    rng = random.Random(seed); t0 = time.time()
    res = [L.run_path(L.bootstrap(k, d, h, rng), pol) for _ in range(N)]
    print(L.fmt(name, L.summarize(res, h)), "%.0fs" % (time.time() - t0), flush=True)
    return res
if __name__ == "__main__":
    go("v1 budget 500", L.Policy(budget=500, xfa_policy="v1"))
    for b in (300, 500, 1000):
        go("v2 budget %d" % b, L.Policy(budget=b))
    go("v2 budget 500 stagger10", L.Policy(budget=500, stagger_days=10))
    go("v2 budget 500 no-upgrade", L.Policy(budget=500, upgrade_cash=1e12))
