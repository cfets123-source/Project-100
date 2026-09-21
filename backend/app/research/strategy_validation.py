"""Walk-forward promotion gate for trading strategies.

Promotion needs enough untouched observations and acceptable loss behavior.  A
profitable in-sample backtest alone never passes this gate.
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from sqlalchemy.orm import Session

from app.audit.logger import log_and_commit
from app.models.models import StrategyValidationRecord


METHODOLOGY_VERSION = "walk-forward-v1"


@dataclass(frozen=True)
class ValidationResult:
    trades: int
    win_rate: float
    total_return: float
    max_drawdown: float
    passed: bool
    reasons: list[str]


def assess_out_of_sample(returns: list[float], *, minimum_trades: int = 30,
                         max_drawdown: float = 0.15, minimum_return: float = 0.0) -> ValidationResult:
    """Assess untouched returns after fees/slippage have been applied."""
    equity = peak = 1.0
    worst_drawdown = 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        worst_drawdown = min(worst_drawdown, equity / peak - 1.0)
    reasons: list[str] = []
    if len(returns) < minimum_trades:
        reasons.append("insufficient out-of-sample trades")
    if equity - 1.0 <= minimum_return:
        reasons.append("out-of-sample return did not clear threshold")
    if abs(worst_drawdown) > max_drawdown:
        reasons.append("out-of-sample drawdown exceeded threshold")
    return ValidationResult(trades=len(returns),
                            win_rate=(sum(value > 0 for value in returns) / len(returns)) if returns else 0.0,
                            total_return=equity - 1.0,
                            max_drawdown=worst_drawdown,
                            passed=not reasons, reasons=reasons)


def record_validation(db: Session, *, strategy: str, result: ValidationResult,
                      sample_start: dt.datetime | None = None,
                      sample_end: dt.datetime | None = None,
                      actor: str = "research") -> StrategyValidationRecord:
    """Persist research evidence. A failed rerun replaces any prior approval.

    This intentionally does not select parameters or activate live trading.
    """
    record = db.get(StrategyValidationRecord, strategy)
    if record is None:
        record = StrategyValidationRecord(strategy=strategy, methodology_version=METHODOLOGY_VERSION,
                                          trades=0, win_rate=0, total_return=0, max_drawdown=0,
                                          passed=False, reasons=[])
        db.add(record)
    record.methodology_version = METHODOLOGY_VERSION
    record.evaluated_at = dt.datetime.utcnow()
    record.sample_start = sample_start
    record.sample_end = sample_end
    record.trades = result.trades
    record.win_rate = result.win_rate
    record.total_return = result.total_return
    record.max_drawdown = result.max_drawdown
    record.passed = result.passed
    record.reasons = result.reasons
    db.flush()
    log_and_commit(db, "strategy_validation_recorded", {
        "strategy": strategy, "methodology_version": METHODOLOGY_VERSION,
        "trades": result.trades, "total_return": result.total_return,
        "max_drawdown": result.max_drawdown, "passed": result.passed,
        "reasons": result.reasons,
    }, actor=actor)
    return record


def require_passing_validation(db: Session, strategy: str) -> StrategyValidationRecord:
    """Fail closed unless this exact deployed strategy has passing evidence."""
    record = db.get(StrategyValidationRecord, strategy)
    if record is None:
        raise RuntimeError(f"strategy_validation_missing:{strategy}")
    if record.methodology_version != METHODOLOGY_VERSION:
        raise RuntimeError(f"strategy_validation_methodology_mismatch:{strategy}")
    if not record.passed:
        raise RuntimeError(f"strategy_validation_failed:{strategy}:{','.join(record.reasons or [])}")
    return record
