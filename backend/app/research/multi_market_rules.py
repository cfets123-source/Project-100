"""Frozen multi-market scanner rules (watch-only research).

Three rules are applied identically to every market. A signal is formed on a
completed daily close; its hypothetical entry is the next session's open, and it
exits through a bracket (stop checked before target on the same bar), a time
limit, or the rule's own exit condition at the next open. Nothing here can
place an order.

The 2011-2026 history test (docs: MULTI_MARKET_SCAN_V1_RESULT.md) found no rule
that worked in both 2011-2020 and 2021-2026 as a single $100 position. That is
why this module feeds a forward, watch-only scoreboard rather than live trading.
"""
from __future__ import annotations

from dataclasses import dataclass

RULES_VERSION = "multi-market-scan-v1"


@dataclass(frozen=True)
class Rule:
    name: str
    stop: float
    target: float
    max_hold: int
    description: str


RULES = {
    "trend": Rule("trend", .10, .20, 60, "Close crosses into close > 50-day > 200-day average"),
    "pullback": Rule("pullback", .08, .06, 10, "Above 200-day average with 2-day RSI under 10"),
    "breakout": Rule("breakout", .07, .15, 30, "Close above prior 20-day high while above 200-day average"),
}

LEVERAGED = ("TQQQ", "UPRO", "SPXL", "TNA", "SOXL", "TECL", "FAS", "LABU", "FNGU", "QLD", "SSO",
             "UDOW", "TMF")
INDEX_SECTOR = ("SPY", "QQQ", "IWM", "DIA", "MDY", "RSP", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP",
                "XLI", "XLB", "XLU", "XLRE", "XLC", "SMH", "SOXX", "IBB", "XBI", "KRE", "XHB", "ITB",
                "XME", "GDX", "GDXJ", "ARKK", "IGV")
MACRO = ("TLT", "IEF", "SHY", "HYG", "LQD", "TIP", "AGG", "EMB", "GLD", "SLV", "USO", "UNG", "DBC",
         "CPER", "URA", "EEM", "EFA", "FXI", "EWJ", "EWZ", "EWW", "INDA", "EWY", "EWT", "KWEB")
STOCKS = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "AMD", "NFLX", "ORCL",
          "CRM", "ADBE", "INTC", "QCOM", "MU", "AMAT", "LRCX", "KLAC", "TXN", "JPM", "BAC", "GS",
          "MS", "WFC", "C", "V", "MA", "PYPL", "AXP", "UNH", "LLY", "JNJ", "PFE", "MRK", "ABBV",
          "TMO", "ISRG", "XOM", "CVX", "COP", "OXY", "SLB", "WMT", "COST", "HD", "LOW", "NKE",
          "MCD", "SBUX", "TGT", "BA", "CAT", "DE", "GE", "HON", "LMT", "UPS", "DIS", "CMCSA", "T",
          "VZ", "PLTR", "SHOP", "UBER", "COIN", "MSTR", "SNOW", "CRWD", "PANW", "NOW", "ROKU")
CRYPTO = ("BTC/USD", "ETH/USD", "SOL/USD")
GROUPS = {"leveraged ETF": LEVERAGED, "index/sector ETF": INDEX_SECTOR,
          "bonds/commodities/intl": MACRO, "large stock": STOCKS, "crypto": CRYPTO}
US_UNIVERSE = LEVERAGED + INDEX_SECTOR + MACRO + STOCKS


def group_of(symbol: str) -> str:
    return next((g for g, members in GROUPS.items() if symbol in members), "other")


def indicators(bars: list[dict]) -> dict:
    c = [float(b["close"]) for b in bars]
    n = len(c)

    def sma(k):
        out, s = [None] * n, 0.0
        for i in range(n):
            s += c[i]
            if i >= k:
                s -= c[i - k]
            if i >= k - 1:
                out[i] = s / k
        return out

    rsi2, g, l = [None] * n, None, None
    for i in range(1, n):
        ch = c[i] - c[i - 1]
        up, dn = max(ch, 0.0), max(-ch, 0.0)
        g, l = (up, dn) if g is None else ((g + up) / 2, (l + dn) / 2)
        if i >= 3:
            rsi2[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    hi20 = [None] * n
    for i in range(20, n):
        hi20[i] = max(float(b["high"]) for b in bars[i - 20:i])
    mom126 = [None] * n
    for i in range(126, n):
        mom126[i] = c[i] / c[i - 126] - 1
    return {"c": c, "s5": sma(5), "s50": sma(50), "s200": sma(200), "rsi2": rsi2,
            "hi20": hi20, "mom126": mom126}


def fires(rule: str, x: dict, i: int) -> bool:
    c, s50, s200 = x["c"], x["s50"], x["s200"]
    if i < 1 or s200[i] is None or s50[i] is None:
        return False
    if rule == "trend":
        now = c[i] > s50[i] > s200[i]
        before = s200[i - 1] is not None and c[i - 1] > s50[i - 1] > s200[i - 1]
        return now and not before
    if rule == "pullback":
        return c[i] > s200[i] and x["rsi2"][i] is not None and x["rsi2"][i] < 10
    if rule == "breakout":
        return x["hi20"][i] is not None and c[i] > x["hi20"][i] and c[i] > s200[i]
    raise ValueError(rule)


def rule_exit(rule: str, x: dict, i: int) -> bool:
    if rule == "trend":
        return x["s50"][i] is not None and x["c"][i] < x["s50"][i]
    if rule == "pullback":
        return x["s5"][i] is not None and x["c"][i] > x["s5"][i]
    return False


def signals_on_last_bar(symbol: str, bars: list[dict]) -> list[dict]:
    """Signals formed by the most recent completed bar."""
    if len(bars) < 202:
        return []
    x = indicators(bars)
    i = len(bars) - 1
    out = []
    for name, rule in RULES.items():
        if fires(name, x, i):
            out.append({"symbol": symbol, "rule": name, "group": group_of(symbol),
                        "signal_date": str(bars[i]["timestamp"])[:10], "close": x["c"][i],
                        "stop_pct": rule.stop, "target_pct": rule.target, "max_hold": rule.max_hold,
                        "momentum_6m": x["mom126"][i]})
    return out


def evaluate(rule: str, bars: list[dict], signal_date: str, cost: float = .0005) -> dict:
    """Outcome of a signal given bars that include the signal day and later days."""
    idx = next((k for k, b in enumerate(bars) if str(b["timestamp"])[:10] == signal_date), None)
    if idx is None or idx + 1 >= len(bars):
        return {"status": "waiting_entry"}
    r, x = RULES[rule], indicators(bars)
    entry = float(bars[idx + 1]["open"]) * (1 + cost)
    stop, target = entry * (1 - r.stop), entry * (1 + r.target)
    for j in range(idx + 1, len(bars)):
        b = bars[j]
        o, h, lo = float(b["open"]), float(b["high"]), float(b["low"])
        if lo <= stop:
            return _closed("stop", entry, min(o, stop), b, cost)
        if h >= target:
            return _closed("target", entry, max(o, target), b, cost)
        if j - (idx + 1) >= r.max_hold or rule_exit(rule, x, j):
            if j + 1 < len(bars):
                return _closed("time_or_rule_exit", entry, float(bars[j + 1]["open"]), bars[j + 1], cost)
            return {"status": "exit_next_open", "entry": entry,
                    "mark_pct": float(b["close"]) / entry - 1}
    last = bars[-1]
    return {"status": "open", "entry": entry, "mark_pct": float(last["close"]) / entry - 1}


def _closed(reason, entry, price, bar, cost):
    return {"status": "closed", "exit_reason": reason, "entry": entry,
            "result_pct": price * (1 - cost) / entry - 1, "exit_date": str(bar["timestamp"])[:10]}
