"""Build NOISE (hourly checks + 1% vol sizing) daily paths for SPY/IWM/GLD (proxies for MES/M2K/MGC)."""
import os, pickle, sys
L = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "20261022-ladder")
sys.path.insert(0, L); sys.path.insert(0, os.path.join(L, "..", "..", "prop"))
import daily, variants as V
sym = sys.argv[1]
raw = daily.load('/home/claude/data/multi/%s_5m.csv.gz' % sym)
pd = V.build(raw, every=60, voltarget=0.010)
pickle.dump(pd, open('/home/claude/data/multi/v_%s.pkl' % sym, 'wb'))
print(sym, len(pd), min(pd), max(pd))
