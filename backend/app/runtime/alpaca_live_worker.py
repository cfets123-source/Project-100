"""Isolated live worker. The compose profile remains default-off."""
import time
from datetime import datetime, timedelta, timezone
from app.runtime.alpaca_live_execution import load_finally_authorized_adapter
from app.strategies.daily_trend_pullback import DailyTrendPullback
from app.services.execution_gateway import ExecutionGateway
from app.services.state_machine import StateManager
from app.risk.engine import RiskEngine
from app.services.alpaca_paper_protection import ensure_protective_stops
from app.audit.logger import log_and_commit
from app.runtime.alpaca_live_position_manager import (
    manage_live_positions, manage_session_close, reconcile_broker_bracket_exits,
    release_flat_account_reservations,
)
from app.brokers.alpaca_adapter import AlpacaBrokerError
from app.runtime.alpaca_position_supervisor import supervise_positions
from app.services.account_risk import measured_risk_context, RiskEvidenceUnavailable
from app.services.alpaca_risk_reconciliation import collect_risk_observation

LIVE_SYMBOLS=("SPY","QQQ","IWM","GLD","TLT")


def allocated_live_equity(balances: dict, cfg) -> float:
    """Use the designated live account's current equity for compounding.

    STARTING_CAPITAL is the launch baseline, not a permanent ceiling.  Keeping
    the ceiling here would make the system incapable of scaling an earned gain
    into the next capital stage.  Position, stop, and circuit-breaker limits
    still apply independently in the deterministic risk engine.
    """
    equity = float(balances["equity"])
    if equity <= 0:
        raise RuntimeError("live_account_equity_must_be_positive")
    return equity

def start_live_worker(db, cfg, strategy: DailyTrendPullback | None = None):
    strategy = strategy or DailyTrendPullback()
    # This constructs the broker mutation adapter only after state, final flag,
    # and this exact strategy's passing validation record have all been checked.
    return load_finally_authorized_adapter(db, cfg, strategy.name)

def run_cycle(db, cfg, *, strategy: DailyTrendPullback | None = None,
              symbols: tuple[str, ...] = LIVE_SYMBOLS):
    """One guarded live cycle; disabled gates fail before any broker mutation."""
    strategy = strategy or DailyTrendPullback()
    # Position supervision comes before entry approval. A strategy failure must
    # not stop observing/managing already held exposure.
    supervision = supervise_positions(db, cfg)
    if supervision.get('risk_ready') is False:
        return {'started': True, 'entries': [], 'reason': 'risk_reconciliation_unavailable',
                'supervision': supervision}
    stage = supervision.get('milestone', {})
    if stage.get('phase') in {'liquidating', 'waiting_for_available_funds', 'stage_complete', 'complete'}:
        return {'started': True, 'entries': [], 'reason': 'milestone_' + stage['phase'],
                'supervision': supervision}
    try:
        adapter=start_live_worker(db,cfg,strategy)
    except RuntimeError as exc:
        return {'started': True, 'entries': [], 'reason': str(exc), 'supervision': supervision}
    account_id=str(adapter.get_accounts()[0]['account_id'])
    released_reservations = release_flat_account_reservations(db, adapter, account_id)
    protection=ensure_protective_stops(db, adapter, cfg, mode="live")
    if not protection.get('protected'):
        if protection.get("reason") == "exit_pending":
            return {"started": True, "entries": [], "reason": "exit_pending",
                    "protection": protection}
        StateManager(db,cfg).activate_kill_switch('live position lacks verified protective stop')
        return {"started": True, "entries": [], "protection": protection}
    session_close = manage_session_close(db, adapter, cfg, mode="live")
    lifecycle = manage_live_positions(db, adapter, allow_legacy_target_exit=True)
    bracket_reconciliation = reconcile_broker_bracket_exits(db, adapter, mode="live")
    if session_close["due"]:
        return {"started": True, "entries": [], "reason": "session_closing",
                "protection": protection, "session_close": session_close,
                "lifecycle": lifecycle, "bracket_reconciliation": bracket_reconciliation,
                "released_reservations": released_reservations}
    positions = adapter.get_positions()
    if positions:
        return {"started": True, "entries": [], "reason": "position_already_open",
                "protection": protection, "lifecycle": lifecycle,
                "bracket_reconciliation": bracket_reconciliation,
                "released_reservations": released_reservations}
    signal=strategy.portfolio_signal(adapter, symbols)
    if not signal:
        log_and_commit(db, "alpaca_live_worker_no_qualifying_signal", {"strategy": strategy.name})
        return {"started": True, "entries": [], "reason": "no_qualifying_signal",
                "protection": protection, "lifecycle": lifecycle,
                "bracket_reconciliation": bracket_reconciliation}
    quote=adapter.get_quotes([signal['symbol']])[0]
    balances=adapter.get_balances(); equity=allocated_live_equity(balances, cfg)
    now = datetime.now(timezone.utc)
    bars = adapter.get_daily_bars(signal['symbol'],
                                 (now - timedelta(days=45)).date().isoformat(),
                                 now.date().isoformat())
    try:
        collect_risk_observation(db, adapter, getattr(cfg, 'STATE_SCOPE', 'current'))
        if len(bars) < 20:
            raise RiskEvidenceUnavailable('observed liquidity history is incomplete')
        liquidity = sum(float(b['close']) * float(b['volume']) for b in bars[-20:]) / 20
        risk_context = measured_risk_context(db, scope=getattr(cfg, 'STATE_SCOPE', 'current'),
                                             account_id=account_id, equity=equity,
                                             avg_dollar_volume=liquidity)
    except (RiskEvidenceUnavailable, KeyError, TypeError, ValueError) as exc:
        log_and_commit(db, 'live_entry_blocked_risk_evidence', {'reason': str(exc)})
        return {'started': True, 'entries': [], 'reason': str(exc), 'supervision': supervision}
    result=ExecutionGateway(db,adapter,RiskEngine(cfg),StateManager(db,cfg),account_id).submit(
        signal, account_id, quote,
        risk_context,
        equity, min(float(balances['buying_power']), equity*cfg.MAX_POSITION_PCT))
    log_and_commit(db, "alpaca_live_worker_cycle_completed", {"strategy": strategy.name,
                   "submitted": result.submitted, "reason": result.reason, "trade_id": result.trade_id})
    return {"started": True, **result.__dict__, "protection": protection, "lifecycle": lifecycle,
            "bracket_reconciliation": bracket_reconciliation,
            "released_reservations": released_reservations}


if __name__ == '__main__':
    import argparse
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import Settings
    from app.runtime.alpaca_live_worker_lock import exclusive_live_worker
    parser=argparse.ArgumentParser(); parser.add_argument('--database', required=True); parser.add_argument('--once', action='store_true'); parser.add_argument('--interval', type=float, default=60.0)
    args=parser.parse_args(); cfg=Settings(); engine=create_engine(args.database)
    with exclusive_live_worker(args.database):
        while True:
            with Session(engine) as db:
                # Read throttling is an external, temporary condition.  Never let
                # it terminate the supervised live worker or turn into an order
                # retry; record it and wait for the next normal cycle instead.
                try:
                    result = run_cycle(db, cfg)
                except AlpacaBrokerError as exc:
                    log_and_commit(db, "alpaca_live_worker_rate_limited", {
                        "error": type(exc).__name__,
                    })
                    result = {"started": True, "entries": [], "reason": "broker_rate_limited"}
                print(result, flush=True)
            if args.once: break
            time.sleep(max(5.0, args.interval))
