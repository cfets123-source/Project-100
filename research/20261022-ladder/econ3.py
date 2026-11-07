import statistics as st, sys
sys.path.insert(0, '.')
import ladder as L, econ, econ2
days = L.load('/home/claude/data/qqq/noise_days.pkl'); keys = sorted(days); seq = [days[k] for k in keys]
starts = range(0, len(seq) - 130, 3); xs = range(0, len(seq) - 510, 3)
for size in (100, 150):
    T = L.TYPES[size]
    print("COMBINE %dK fee $%d:" % (size, T["fee"]))
    for n in range(2, 9):
        r = [econ.combine(seq[s:], n, T) for s in starts]
        ps = [d for o, d in r if o == "pass"]; rate = len(ps) / len(r)
        fees = st.mean(T["fee"] * (1 + (d - 1) // 21) for o, d in r)
        print("   n=%d pass %5.1f%% med %3.0fd fees/attempt $%4.0f cost/pass $%5.0f" % (n, 100*rate, st.median(ps) if ps else 0, fees, fees/rate + 149 if rate else 0))
for size, per, nmax, cush in ((150, 2500, 6, 9000), (150, 2000, 6, 6000), (150, 2500, 4, 9000), (100, 2500, 4, 6000)):
    T = L.TYPES[size]
    for path in ("standard", "consistency"):
        r = [econ2.xfa(seq[s:], T, per, nmax, 150 * size // 50, cush, path) for s in xs]
        g = sorted(x[0] for x in r)
        firsts = None
        print("XFA %dK per %d nmax %d cush %d %-11s avg $%6.0f med $%5.0f p(any) %4.1f%% alive2y %4.1f%%" % (size, per, nmax, cush, path, st.mean(g), st.median(g), 100*sum(x[1]>0 for x in r)/len(r), 100*sum(x[3]=="alive" for x in r)/len(r)))
