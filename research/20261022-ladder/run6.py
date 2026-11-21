import datetime as dt, pickle, random, sys
sys.path.insert(0, '.')
import ladder as L
from run3 import go
H = 1260
d = L.prep(pickle.load(open('/home/claude/data/qqq/v_hourly+vt1.0.pkl', 'rb'))) if False else pickle.load(open('/home/claude/data/qqq/v_hourly+vt1.0.pkl', 'rb'))
keys = sorted(d)
best = L.Policy(budget=1000, upgrade_cash=300, max_combines=1, cushion_per50=2000)
dev = [k for k in keys if k <= dt.date(2023, 12, 29)]; conf = [k for k in keys if k >= dt.date(2024, 1, 2)]
go("NEW full 2019-2026", best, d=d, k=keys, h=H)
go("NEW 2019-2023 only", best, d=d, k=dev, h=H)
go("NEW 2024-2026 only", best, d=d, k=conf, h=H)
go("NEW 2024-2026 budget 500", L.Policy(budget=500, upgrade_cash=300, max_combines=1, cushion_per50=2000), d=d, k=conf, h=H)
go("NEW full edge cut 25%", best, d=L.haircut(d, 0.25), k=keys, h=H)
