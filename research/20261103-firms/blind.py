"""Blind judgment test: 48 random set-and-forget setups (2020-2026), drawn as anonymous charts (no symbol, no date,
no prices, nothing after the setup day). Outcomes are written to a separate file and only read after the calls."""
import datetime as dt, glob, json, os, random
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sf, sf2
data = {os.path.basename(p)[:-4]: sf.load(p) for p in sorted(glob.glob("/home/claude/fx/*.csv"))}
cands = []
for s, rows in data.items():
    for t in sf2.scored(s, rows):
        if dt.date(2020, 1, 1) <= t["date"] <= dt.date(2026, 9, 30): cands.append(t)
rng = random.Random(20261029); pick = rng.sample(cands, 48)
os.makedirs("blind", exist_ok=True)
json.dump([{"id": n + 1, "r": t["r"], "sym": t["sym"], "date": str(t["date"])} for n, t in enumerate(pick)],
          open("blind/outcomes_SEALED.json", "w"))
for g in range(4):
    fig, axes = plt.subplots(3, 4, figsize=(20, 12))
    for k, ax in enumerate(axes.flat):
        n = g * 12 + k; t = pick[n]; rows = data[t["sym"]]
        idx = [i for i, r in enumerate(rows) if r[0] == t["date"]][0] - 1           # setup (rejection) day
        win = rows[max(0, idx - 79): idx + 1]; closes = [r[4] for r in rows[: idx + 1]]
        e20 = sf.ema(closes, 20)[-len(win):]; e100 = sf.ema(closes, 100)[-len(win):]
        base = win[-1][4]
        for x, (_, o, h, l, c) in enumerate(win):
            col = "#1f77b4" if c >= o else "#d62728"
            ax.plot([x, x], [l / base, h / base], color=col, lw=0.8)
            ax.add_patch(plt.Rectangle((x - 0.3, min(o, c) / base), 0.6, max(abs(c - o), 1e-9) / base, color=col))
        ax.plot(range(len(win)), [v / base for v in e20], color="#2a6df4", lw=1)
        ax.plot(range(len(win)), [v / base for v in e100], color="#999999", lw=1, ls="--")
        side = t["side"]; atr = sum(r[2] - r[3] for r in win[-14:]) / 14
        sl = (win[-1][3] - 0.1 * atr) if side > 0 else (win[-1][2] + 0.1 * atr)
        ent = win[-1][4]; tp = ent + side * 3 * abs(ent - sl)
        x0 = len(win)
        ax.fill_between([x0, x0 + 12], ent / base, tp / base, color="green", alpha=0.15)
        ax.fill_between([x0, x0 + 12], ent / base, sl / base, color="red", alpha=0.15)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title("#%d  %s" % (n + 1, "BUY" if side > 0 else "SELL"), fontsize=14)
    plt.tight_layout(); plt.savefig("blind/grid%d.png" % (g + 1), dpi=60); plt.close()
print(len(cands), "candidates; 48 charts drawn; outcomes sealed")
