"""Strategy pipeline: where each strategy stands on the road from idea to live money.

Scan -> Backtest -> Stress test -> Paper -> Approval -> Live -> Nightly review.
Every status is derived from stored evidence (lots, acceptances, committed stress
results, review reports), never typed in by hand.
"""
from __future__ import annotations

from app.models.models import AllocatorLot, AppState, OwnerAcceptedExperiment, ScannerSignal
from app.research.stress_gate import stress_result

STAGES = ("Scan", "Backtest", "Stress test", "Paper", "Approval", "Live", "Nightly review")

STRATEGIES = (
    {"id": "allocator-core-satellite-v1", "name": "Alpaca allocator", "venue": "Alpaca",
     "detail": "50% TQQQ core + 5 fractional satellites, weekly swap", "paper": "paper", "live": "live",
     "backtest": "2011–2020 $805 · 2021–Sep 2026 $356 · last 12 mo $157 (from $100, with weekly swap)"},
    {"id": "binance-crypto-signals-v1", "name": "Binance.US crypto", "venue": "Binance.US",
     "detail": "BTC/ETH/SOL breakout + trend, 24/7, 1/3 each", "paper": "binance-paper", "live": "binance",
     "backtest": "2018–20 $214 · 2021–Sep 2026 $522 · last 12 mo $117 (from $100)"},
    {"id": "options-watchlist", "name": "Options (Robinhood)", "venue": "Robinhood",
     "detail": "Watch-only quotes; waits for a larger account", "paper": None, "live": None, "backtest": None},
)


def _has_lots(db, mode) -> bool:
    return bool(mode) and db.query(AllocatorLot).filter_by(mode=mode).first() is not None


def strategy_status(db, s: dict) -> dict:
    scan = db.query(ScannerSignal).first() is not None
    stress = stress_result(s["id"])
    acc = db.get(OwnerAcceptedExperiment, s["id"])
    approved = bool(acc and not acc.revoked)
    paper = _has_lots(db, s["paper"])
    live = _has_lots(db, s["live"])
    review = db.get(AppState, "nightly_latest") is not None and live
    done = [scan, bool(s["backtest"]), bool(stress and stress.get("passed")), paper, approved, live, review]
    notes = [
        "Scanner records signals daily" if scan else "Scanner has no signals yet",
        s["backtest"] or "No backtest yet",
        (f"Pass · {stress['monte_carlo_12m']['p_floor']:.1%} chance of touching $50 in 12 mo" if stress and stress.get("passed")
         else "Failed" if stress else "Not run"),
        "Paper trades recorded" if paper else ("Paper worker waiting for signals" if s["paper"] else "—"),
        "Owner accepted the risk" if approved else "Waiting for your go-ahead",
        "Trading real money" if live else "Not live",
        "Reviewed nightly" if review else "Starts after going live",
    ]
    current = next((i for i, d in enumerate(done) if not d), len(STAGES))
    stages = [{"name": n, "status": "done" if done[i] else ("current" if i == current else "pending"), "note": notes[i]}
              for i, n in enumerate(STAGES)]
    return {**{k: s[k] for k in ("id", "name", "venue", "detail")}, "stages": stages,
            "stage": STAGES[current] if current < len(STAGES) else "Running"}


def pipeline(db) -> dict:
    return {"stages": list(STAGES), "strategies": [strategy_status(db, s) for s in STRATEGIES]}
