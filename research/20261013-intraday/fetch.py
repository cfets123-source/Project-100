"""Download 5-minute bars for the intraday test (read-only). Run inside the API container:
    docker exec -i project-100-api-1 python - < fetch.py
Writes /data/research/intraday/<SYM>_5m.csv.gz (t,o,h,l,c,v; t in UTC ISO). Never places orders.
"""
import csv
import gzip
import os
import sys

from app.brokers import alpaca_connection
from app.core.config import settings
from app.db.session import SessionLocal

SYMBOLS = ("QQQ", "TQQQ", "SQQQ")
START, END = "2019-01-01T00:00:00Z", "2026-10-01T00:00:00Z"
OUT = "/data/research/intraday"


def fetch(adapter, sym, feed):
    params = {"timeframe": "5Min", "start": START, "end": END, "adjustment": "all", "feed": feed, "limit": 10000}
    rows, token = [], None
    for _ in range(400):
        q = {**params, **({"page_token": token} if token else {})}
        raw = adapter._request("GET", f"/v2/stocks/{sym}/bars", data_api=True, params=q)
        rows.extend(raw.get("bars") or [])
        token = raw.get("next_page_token")
        if not token:
            return rows
    raise RuntimeError("pagination bound exceeded")


def main():
    os.makedirs(OUT, exist_ok=True)
    db = SessionLocal()
    adapter, _ = alpaca_connection.load_read_only_adapter(db, settings.BROKER_TOKEN_ENCRYPTION_KEY, paper=False)
    for sym in SYMBOLS:
        used = None
        for feed in ("sip", "iex"):
            try:
                rows = fetch(adapter, sym, feed)
                used = feed
                break
            except Exception as exc:  # SIP may be refused on the free plan
                print(f"{sym}: {feed} failed ({type(exc).__name__}: {str(exc)[:80]})", file=sys.stderr)
        if not used:
            sys.exit(f"{sym}: no data")
        path = f"{OUT}/{sym}_5m.csv.gz"
        with gzip.open(path, "wt", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["t", "o", "h", "l", "c", "v"])
            for b in rows:
                w.writerow([b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]])
        print(f"FETCH {sym} feed={used} bars={len(rows)} first={rows[0]['t'][:10]} last={rows[-1]['t'][:10]}")


main()
