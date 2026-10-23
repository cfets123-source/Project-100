"""Download MNQ 5-minute history from TopstepX for the full ladder simulation (read-only: no orders).

Run on the Mac (uses the Keychain credentials from install.sh):
    python3 ~/Documents/p100-prop/fetch_history.py
Writes ~/Documents/p100-prop/data/mnq_5m.csv.gz (t,o,h,l,c,v,contract) using the front-month contract for each
date (rolls 8 days before the 3rd-Friday expiry of Mar/Jun/Sep/Dec, the usual CME equity-index roll).
Resumable: contracts already in the file are skipped. Prints a coverage summary at the end.
"""
import csv
import datetime as dt
import gzip
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from topstepx import TopstepX, TopstepXError  # noqa: E402
from worker import credentials, iso  # noqa: E402

OUT = os.path.expanduser("~/Documents/p100-prop/data/mnq_5m.csv.gz")
MONTHS = {3: "H", 6: "M", 9: "U", 12: "Z"}
FIRST_YEAR = 2019  # MNQ launched May 2019
CHUNK_DAYS = 20     # ~5,500 five-minute bars per request (23-hour sessions), under the 20,000 limit
PAUSE = 0.8         # stay well inside the API rate limit


def third_friday(year, month):
    d = dt.date(year, month, 15)
    return d + dt.timedelta(days=(4 - d.weekday()) % 7)


def roll_date(year, month):
    return third_friday(year, month) - dt.timedelta(days=8)


def contracts(until):
    """[(contract_id, front_from, front_to)] in date order, ending with the contract that is front on `until`."""
    out, prev = [], dt.date(FIRST_YEAR, 5, 1)
    for year in range(FIRST_YEAR, until.year + 2):
        for month, code in MONTHS.items():
            roll = roll_date(year, month)
            if roll <= prev:
                continue
            out.append(("CON.F.US.MNQ.%s%02d" % (code, year % 100), prev, roll))
            prev = roll
            if roll > until:
                return out
    return out


def load_done(path):
    if not os.path.exists(path):
        return set(), []
    with gzip.open(path, "rt") as fh:
        rows = list(csv.DictReader(fh))
    return {r["contract"] for r in rows}, rows


def fetch_contract(api, cid, start, end, pause=PAUSE):
    rows, a = {}, dt.datetime.combine(start, dt.time(0), dt.timezone.utc)
    stop = dt.datetime.combine(end, dt.time(0), dt.timezone.utc)
    while a < stop:
        b = min(a + dt.timedelta(days=CHUNK_DAYS), stop)
        for bar in api.bars(cid, iso(a), iso(b), limit=20000):
            rows[bar["t"]] = (bar["o"], bar["h"], bar["l"], bar["c"], bar["v"])
        a = b
        time.sleep(pause)
    return rows


def main(api=None, out=OUT, today=None, pause=PAUSE):
    api = api or TopstepX(*credentials())
    today = today or dt.date.today()
    os.makedirs(os.path.dirname(out), exist_ok=True)
    done, rows = load_done(out)
    summary = []
    for cid, start, end in contracts(today):
        end = min(end, today + dt.timedelta(days=1))
        if cid in done:
            summary.append((cid, "kept", sum(1 for r in rows if r["contract"] == cid)))
            continue
        try:
            got = fetch_contract(api, cid, start, end, pause)
        except TopstepXError as e:
            summary.append((cid, "error: %s" % e, 0))
            continue
        for t in sorted(got):
            o, h, l, c, v = got[t]
            rows.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v, "contract": cid})
        summary.append((cid, "%s..%s" % (start, end), len(got)))
        print("%-20s %s..%s  %6d bars" % (cid, start, end, len(got)), flush=True)
    rows.sort(key=lambda r: r["t"])
    tmp = out + ".tmp"
    with gzip.open(tmp, "wt", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["t", "o", "h", "l", "c", "v", "contract"])
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, out)
    have = [s for s in summary if s[2] > 0]
    print("\nDONE: %d bars, %d contracts with data, %d without. File: %s" % (
        len(rows), len(have), len(summary) - len(have), out))
    if have:
        first = min(r["t"] for r in rows)
        print("Coverage from %s to %s" % (first[:10], max(r["t"] for r in rows)[:10]))
    return summary


if __name__ == "__main__":
    main()
