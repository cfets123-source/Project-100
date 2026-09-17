"""
ENGINEERING TEST STRATEGY — v0.1.0 — NOT VALIDATED FOR PROFITABILITY.

This exists to exercise the full pipeline (scan -> qualify -> signal -> risk ->
execution -> exit) end to end. It has no backtest history, no live track record,
and must not be represented as a trading edge. It is deliberately simple: buy on
a fixed percentage dip from a reference price, fixed-percent stop and target.
"""
import uuid
from app.strategies.base import BaseStrategy

STRATEGY_VERSION = "test-dip-buy-v0.1.0"


class TestDipBuyStrategy(BaseStrategy):
    name = STRATEGY_VERSION

    def __init__(self, dip_pct: float = 0.02, stop_pct: float = 0.05, target_r_multiple: float = 2.0):
        self.dip_pct = dip_pct
        self.stop_pct = stop_pct
        self.target_r_multiple = target_r_multiple

    def scan(self, universe: list[str]) -> list[str]:
        return list(universe)

    def qualify(self, symbol: str, context: dict) -> bool:
        ref = context.get("reference_price")
        last = context.get("last_price")
        if ref is None or last is None:
            return False
        return last <= ref * (1 - self.dip_pct)

    def generate_signal(self, symbol: str, context: dict) -> dict | None:
        if not self.qualify(symbol, context):
            return None
        entry = self.calculate_entry(symbol, context)
        stop = self.calculate_stop(symbol, context)
        target = self.calculate_target(symbol, context)
        return {
            "symbol": symbol, "direction": "long", "strategy": self.name,
            "decision_id": str(uuid.uuid4()),
            "entry_price": entry, "stop_price": stop, "target_price": target,
            "thesis": f"engineering test strategy: {self.dip_pct:.1%} dip from reference",
            "ai_confidence": None,
        }

    def calculate_entry(self, symbol: str, context: dict) -> float:
        return context["last_price"]

    def calculate_stop(self, symbol: str, context: dict) -> float:
        return context["last_price"] * (1 - self.stop_pct)

    def calculate_target(self, symbol: str, context: dict) -> float:
        entry = self.calculate_entry(symbol, context)
        stop = self.calculate_stop(symbol, context)
        risk = entry - stop
        return entry + risk * self.target_r_multiple

    def calculate_position_size(self, entry: float, stop: float, risk_dollars: float) -> float:
        return risk_dollars / abs(entry - stop) if entry != stop else 0.0

    def calculate_expected_rr(self, entry: float, stop: float, target: float) -> float:
        risk = abs(entry - stop)
        reward = abs(target - entry)
        return reward / risk if risk else 0.0

    def invalidate(self, symbol: str, context: dict) -> bool:
        return context.get("last_price", 0) <= 0

    def exit_rules(self, position: dict, context: dict) -> str | None:
        last = context["last_price"]
        if last <= position["stop_price"]:
            return "stop_hit"
        if last >= position["target_price"]:
            return "target_hit"
        return None
