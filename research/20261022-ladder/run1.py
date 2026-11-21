import random, sys, time
sys.path.insert(0, '.')
import ladder as L
days = L.load('/home/claude/data/qqq/noise_days.pkl')
keys = sorted(days)
H = 756
t0 = time.time()
rng = random.Random(1)
res = [L.run_path(L.bootstrap(keys, days, H, rng), L.Policy()) for _ in range(200)]
print(L.fmt("base, bootstrap 200x3y", L.summarize(res, H)), "%.0fs" % (time.time() - t0))
