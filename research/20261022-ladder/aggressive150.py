import datetime as dt, pickle, sys
sys.path.insert(0, '.')
import firms as F, aggressive as A
F.PLANS.update({
 "Topstep 150K (Standard)": dict(price=149, monthly=True, target=9000, dd=4500, lock_eval=0, dll=3000, cons=0.50,
    act=149, f_dd=4500, f_lock=0, floor_after_payout=0, f_dll=3000, rule="days", ndays=5, qday=150, pmin=125,
    pmax=[5000], pfrac=0.5, buffer=0, f_cons=None, split=0.90, max_funded=5, extra_monthly=14.5),
 "Lucid 150K Flex": dict(price=244, monthly=False, target=9000, dd=4500, lock_eval=100, dll=None, cons=0.40,
    act=0, f_dd=4500, f_lock=100, floor_after_payout=100, f_dll=None, rule="days", ndays=5, qday=250,
    cycle_min=1, pmin=500, pmax=[3000], pfrac=0.5, buffer=0, f_cons=None, split=0.90, max_funded=5, extra_monthly=0),
 "MFFU 150K Rapid EOD": dict(price=300, monthly=False, target=9000, dd=4500, lock_eval=None, dll=None, cons=0.50,
    min_days=2, act=0, f_dd=4500, f_lock=100, floor_after_payout=None, f_dll=None, rule="every", every=1,
    cycle_min=1, pmin=500, pmax=[1e9], pfrac=1.0, buffer=4600, f_cons=None, split=0.90, max_funded=3, extra_monthly=0),
})
if __name__ == "__main__":
    days = pickle.load(open('/home/claude/data/qqq/v_hourly+vt1.0.pkl', 'rb')); keys = sorted(days)
    periods = [[days[k] for k in keys if k >= dt.date(2024, 1, 2)], [days[k] for k in keys]]
    for name in ("Topstep 150K (Standard)", "Lucid 150K Flex", "MFFU 150K Rapid EOD"):
        P = F.PLANS[name]; rows = []
        for ne in (4, 6, 9, 12):
            for nf in (3, 6, 9):
                for cush in (2000,):
                    r = [A.slot_income(seq, P, ne, nf, cush) for seq in periods]
                    rows.append((r[0][0], r[1][0], ne, nf, cush))
        print("\n" + name + "  $/slot/month 2024-26 | all-years")
        for a, b, ne, nf, c in sorted(rows, reverse=True)[:4]:
            print("   %+6.0f | %+6.0f   eval %d  funded %d" % (a, b, ne, nf))
