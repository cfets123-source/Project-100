import random, sys
sys.path.insert(0, '.')
import ladder as L
from run3 import go
import datetime as dt
days = L.load('/home/claude/data/qqq/noise_days.pkl'); keys = sorted(days)
H = 1260
for mc in (1, 2):
    for cush in (2000, 3000):
        go("b1000 maxComb%d cush%d" % (mc, cush), L.Policy(budget=1000, upgrade_cash=300, max_combines=mc, cushion_per50=cush), h=H)
best = L.Policy(budget=1000, upgrade_cash=300, max_combines=1, cushion_per50=2000)
dev = [k for k in keys if k <= dt.date(2023, 12, 29)]; conf = [k for k in keys if k >= dt.date(2024, 1, 2)]
go("best, 2019-2023 days only", best, k=dev, h=H)
go("best, 2024-2026 days only", best, k=conf, h=H)
for hc in (0.25, 0.5):
    d2 = L.haircut(days, hc)
    go("best, edge cut %d%%" % (hc * 100), best, d=d2, h=H)
