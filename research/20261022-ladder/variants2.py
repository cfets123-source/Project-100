import datetime as dt, sys
sys.path.insert(0, '.')
import daily, variants as V
raw = daily.load('/home/claude/data/qqq/QQQ_5m.csv.gz')
dev = lambda ks: [k for k in ks if k <= dt.date(2023, 12, 29)]
conf = lambda ks: [k for k in ks if k >= dt.date(2024, 1, 2)]
tests = [("hourly", {"every": 60}), ("hourly+vt1.0", {"every": 60, "voltarget": 0.010}),
         ("hourly+vt1.3", {"every": 60, "voltarget": 0.013}), ("hourly+k0.8", {"every": 60, "k": 0.8}),
         ("hourly+k1.2", {"every": 60, "k": 1.2}), ("hourly cost x3", {"every": 60, "cost": 0.0001})]
for name, kw in tests:
    pd = V.build(raw, **kw); ks = sorted(pd)
    print(V.score(pd, dev(ks), name + " DEV")[0]); print(V.score(pd, conf(ks), name + " CONF")[0], flush=True)
