"""Controlled external-paper candidate evaluation; no implicit activation."""
from app.brokers.base import Quote
from app.runtime.alpaca_paper_execution import execution_prerequisites
from app.services.execution_gateway import ExecutionGateway
from app.services.state_machine import StateManager
from app.risk.engine import RiskEngine


def evaluate_candidate(db, cfg, designated_account_id, signal, risk_context):
    check = execution_prerequisites(db, cfg, signal['symbol'])
    if not check['ready']:
        return {'submitted': False, 'reason': check['reason']}
    q = check['quote']
    quote = Quote('alpaca', q.symbol, q.source_timestamp, q.age_seconds, q.bid, q.ask, q.last, q.market_session)
    # Adapter is intentionally read-only here; a future submission constructor
    # must prove the explicit paper gate again at the call site.
    from app.brokers.alpaca_connection import load_paper_execution_adapter
    adapter = load_paper_execution_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY,
                                           enabled=cfg.ALPACA_PAPER_EXECUTION_ENABLED)
    balances = check['account']['balances']
    # Alpaca paper accounts default to $100k. Project 100 paper validation
    # must instead size from the configured dedicated starting capital.
    effective_equity = min(float(balances['equity']), float(cfg.STARTING_CAPITAL))
    # The strategy can only deploy the configured fraction of its own capital,
    # never the broker's paper buying power.
    effective_buying_power = min(float(balances['buying_power']), effective_equity * cfg.MAX_POSITION_PCT)
    return ExecutionGateway(db, adapter, RiskEngine(cfg), StateManager(db, cfg), designated_account_id,
                            market_data=None).submit(signal, designated_account_id, quote, risk_context,
                                                       effective_equity, effective_buying_power).__dict__
