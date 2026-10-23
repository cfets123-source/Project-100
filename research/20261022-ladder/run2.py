import random, sys, time
sys.path.insert(0, '.')
import ladder as L
days = L.load('/home/claude/data/qqq/noise_days.pkl'); keys = sorted(days)
H, N = 756, 400
def go(name, pol, d=days, k=keys, seed=1):
    rng = random.Random(seed); t0 = time.time()
    res = [L.run_path(L.bootstrap(k, d, H, rng), pol) for _ in range(N)]
    print(L.fmt(name, L.summarize(res, H)), "%.0fs" % (time.time() - t0), flush=True)
for b in (300, 500, 1000):
    go("budget %d" % b, L.Policy(budget=b))
go("budget 500 stagger10", L.Policy(budget=500, stagger_days=10))
go("budget 500 pause-not-finish", L.Policy(budget=500, buffer_mode="pause"))
