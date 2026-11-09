import datetime as dt, pickle, sys
sys.path.insert(0, '.')
import daily, variants as V
raw = daily.load('/home/claude/data/qqq/QQQ_5m.csv.gz')
dev = lambda ks: [k for k in ks if k <= dt.date(2023, 12, 29)]
conf = lambda ks: [k for k in ks if k >= dt.date(2024, 1, 2)]
for name, kw in [("base 30-min", {}), ("hourly", {"every": 60}), ("hourly+vt1.0 whole", {"every": 60, "voltarget": 0.010}),
                 ("hourly+vt1.3 whole", {"every": 60, "voltarget": 0.013})]:
    pd = V.build(raw, **kw); ks = sorted(pd)
    pickle.dump(pd, open('/home/claude/data/qqq/v_%s.pkl' % name.split()[0], 'wb'))
    print(V.score(pd, dev(ks), name + " DEV")[0]); print(V.score(pd, conf(ks), name + " CONF")[0], flush=True)
