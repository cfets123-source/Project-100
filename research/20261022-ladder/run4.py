import random, sys, time
sys.path.insert(0, '.')
import ladder as L
from run3 import go
days = L.load('/home/claude/data/qqq/noise_days.pkl'); keys = sorted(days)
H = 1260
for b in (500, 1000):
    go("opt b%d upg300 5y" % b, L.Policy(budget=b, upgrade_cash=300), h=H)
go("opt b1000 upg300 5y +15%/yr broker", L.Policy(budget=1000, upgrade_cash=300, broker_rate=0.15), h=H)
go("opt b1000 50K-only 5y", L.Policy(budget=1000, upgrade_cash=1e12), h=H)
