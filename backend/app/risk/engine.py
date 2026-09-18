"""
Risk Engine — deterministic, rule-based, no LLM in this path.
Every proposed trade must pass through evaluate() before an OrderRequest is built.
The engine can only REJECT or APPROVE; it never modifies strategy intent silently
beyond size clamping, and every clamp/veto reason is returned for the audit log.
"""
from dataclasses import dataclass, field
import math
import time
from app.core.config import settings
from app.brokers.base import Quote


@dataclass
class TradeProposal:
    symbol: str
    direction: str            # long|short
    entry_price: float
    stop_price: float
    account_equity: float
    strategy: str
    quote: Quote
    avg_dollar_volume: float
    sector: str | None = None
    sector_exposure_pct: float = 0.0   # current exposure to this sector, 0..1
    open_position_count: int = 0
    daily_pnl_pct: float = 0.0         # negative = loss, fraction of equity
    weekly_drawdown_pct: float = 0.0
    total_drawdown_pct: float = 0.0
    strategy_enabled: bool = True
    is_martingale_after_loss: bool = False  # size increase following a loss
    uses_margin: bool = False
    is_short: bool = False
    is_option: bool = False
    estimated_round_trip_fees: float = 0.0


@dataclass
class RiskDecision:
    approved: bool
    reasons: list[str] = field(default_factory=list)
    position_size: float = 0.0
    risk_dollars: float = 0.0


class RiskEngine:
    def __init__(self, cfg=settings):
        self.cfg = cfg

    def evaluate(self, p: TradeProposal) -> RiskDecision:
        reasons: list[str] = []
        if p.stop_price is None:
            return RiskDecision(False, ["missing_or_invalid_stop"])
        if p.quote is None:
            return RiskDecision(False, ["missing_quote"])
        values = (p.entry_price, p.stop_price, p.account_equity, p.avg_dollar_volume,
                  p.sector_exposure_pct, p.open_position_count, p.daily_pnl_pct,
                  p.weekly_drawdown_pct, p.total_drawdown_pct, p.quote.bid,
                  p.quote.ask, p.quote.last, p.quote.timestamp, p.quote.age_seconds,
                  p.estimated_round_trip_fees)
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
            return RiskDecision(False, ["invalid_numeric_input"])
        if min(p.entry_price, p.stop_price, p.account_equity, p.quote.bid,
               p.quote.ask, p.quote.last) <= 0 or p.quote.bid > p.quote.ask:
            return RiskDecision(False, ["invalid_price_or_equity"])
        if p.direction not in ("long", "short"):
            return RiskDecision(False, ["invalid_direction"])
        if p.estimated_round_trip_fees < 0:
            return RiskDecision(False, ["invalid_fee_estimate"])
        if p.quote.symbol != p.symbol:
            return RiskDecision(False, ["quote_symbol_mismatch"])

        # --- Hard prohibitions ---
        if p.uses_margin and not self.cfg.ALLOW_MARGIN:
            reasons.append("margin_disabled")
        if (p.direction == "short" or p.is_short) and not self.cfg.ALLOW_SHORTS:
            reasons.append("shorts_disabled")
        if p.is_option and not self.cfg.ALLOW_OPTIONS:
            reasons.append("options_disabled")
        if p.is_martingale_after_loss:
            reasons.append("martingale_forbidden")
        if not p.strategy_enabled:
            reasons.append("strategy_disabled")

        # --- Missing stop = automatic rejection ---
        if p.stop_price is None or p.stop_price == p.entry_price:
            reasons.append("missing_or_invalid_stop")
        elif ((p.direction == "long" and p.stop_price > p.entry_price)
              or (p.direction == "short" and p.stop_price < p.entry_price)):
            reasons.append("stop_wrong_side_of_entry")

        # --- Data freshness ---
        now = time.time()
        if p.quote.timestamp > now + 1 or p.quote.age_seconds < 0:
            reasons.append("invalid_quote_timestamp")
        if max(p.quote.age_seconds, now - p.quote.timestamp) > self.cfg.MAX_QUOTE_AGE_SECONDS:
            reasons.append("stale_market_data")

        # --- Spread quality ---
        mid = (p.quote.bid + p.quote.ask) / 2 if (p.quote.bid and p.quote.ask) else p.entry_price
        spread_pct = (p.quote.ask - p.quote.bid) / mid if mid else 1.0
        if spread_pct > self.cfg.MAX_SPREAD_PCT:
            reasons.append("excessive_spread")

        # --- Liquidity / price floors ---
        if p.avg_dollar_volume < self.cfg.MIN_AVG_DOLLAR_VOLUME:
            reasons.append("insufficient_liquidity")
        if p.entry_price < self.cfg.MIN_PRICE:
            reasons.append("price_below_minimum")

        # --- Loss / drawdown circuit breakers ---
        if p.daily_pnl_pct <= -self.cfg.MAX_DAILY_LOSS:
            reasons.append("daily_loss_limit_reached")
        if p.weekly_drawdown_pct >= self.cfg.MAX_WEEKLY_DRAWDOWN:
            reasons.append("weekly_drawdown_limit_reached")
        if p.total_drawdown_pct >= self.cfg.MAX_TOTAL_DRAWDOWN:
            reasons.append("total_drawdown_limit_reached")

        # --- Position/sector concentration ---
        if p.open_position_count >= self.cfg.MAX_POSITIONS:
            reasons.append("max_positions_reached")
        if p.sector and p.sector_exposure_pct >= self.cfg.MAX_SECTOR_CONCENTRATION:
            reasons.append("sector_concentration_limit")

        if reasons:
            return RiskDecision(approved=False, reasons=reasons)

        # --- Position sizing (risk-based) ---
        risk_dollars = p.account_equity * self.cfg.MAX_RISK_PER_TRADE
        price_risk_budget = risk_dollars - p.estimated_round_trip_fees
        if price_risk_budget <= 0:
            return RiskDecision(False, ["fees_exceed_risk_budget"])
        per_share_risk = abs(p.entry_price - p.stop_price)
        if per_share_risk <= 0:
            return RiskDecision(approved=False, reasons=["invalid_risk_distance"])

        raw_size = price_risk_budget / per_share_risk
        max_position_dollars = p.account_equity * self.cfg.MAX_POSITION_PCT
        size_capped_by_notional = max_position_dollars / p.entry_price
        position_size = min(raw_size, size_capped_by_notional)

        if position_size <= 0:
            return RiskDecision(approved=False, reasons=["position_size_zero"])

        return RiskDecision(approved=True, reasons=[], position_size=position_size,
                            risk_dollars=position_size * per_share_risk + p.estimated_round_trip_fees)
