import datetime as dt, sys
import tp as T
days = T.load(sys.argv[1])
for v in (250, 400, 600):
    pd = T.build(days, tp=v); ks = sorted(pd)
    dev = [k for k in ks if k <= dt.date(2023, 12, 29)]; conf = [k for k in ks if k >= dt.date(2024, 1, 2)]
    print("TP $%d (2-tick fill) DEV  %s" % (v, T.score(pd, dev))); print("                     CONF %s" % T.score(pd, conf), flush=True)
