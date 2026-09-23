import uuid
import datetime as dt
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Text, JSON, event
from app.db.session import Base


def gen_id() -> str:
    return str(uuid.uuid4())


class AuditImmutabilityError(Exception):
    """Raised when code attempts to UPDATE or DELETE an audit_log row.
    THREAT MODEL: this is an ORM-level (application-role) guard — it stops this
    application's own code (including a compromised strategy/AI component) from
    mutating history through the normal SQLAlchemy session. It does NOT stop a
    database administrator, a raw SQL console, or anyone with direct DB
    credentials from altering rows. True immutability additionally requires
    revoking UPDATE/DELETE grants for the application's Postgres role and/or an
    append-only storage backend — not implemented here (sqlite dev environment
    has no role-based grants). This limitation is intentional to document, not
    to hide."""


class AuditLogEntry(Base):
    """Immutable audit trail. Never delete rows from this table."""
    __tablename__ = "audit_log"
    id = Column(String, primary_key=True, default=gen_id)
    timestamp = Column(DateTime, default=dt.datetime.utcnow, index=True)
    event_type = Column(String, index=True)  # config_change, risk_veto, trade_decision, state_change, kill_switch, error
    actor = Column(String, default="system")  # system | user | ai
    payload = Column(JSON)


@event.listens_for(AuditLogEntry, "before_update")
def _block_audit_update(mapper, connection, target):
    raise AuditImmutabilityError("audit_log rows cannot be updated (application-level guard)")


@event.listens_for(AuditLogEntry, "before_delete")
def _block_audit_delete(mapper, connection, target):
    raise AuditImmutabilityError("audit_log rows cannot be deleted (application-level guard)")


class SystemStateRecord(Base):
    """Persisted current autonomous-mode state. Singleton row (id='current')."""
    __tablename__ = "system_state"
    id = Column(String, primary_key=True, default=lambda: "current")
    state = Column(String, default="off")
    reason = Column(String, nullable=True)
    updated_at = Column(DateTime, default=dt.datetime.utcnow)


class TradeDecisionRecord(Base):
    """Every proposed and executed trade. Never delete."""
    __tablename__ = "trade_decisions"
    trade_id = Column(String, primary_key=True, default=gen_id)
    timestamp = Column(DateTime, default=dt.datetime.utcnow, index=True)
    symbol = Column(String, index=True)
    asset_class = Column(String, default="equity")
    strategy = Column(String, index=True)
    direction = Column(String)  # long | short
    market_regime = Column(String, nullable=True)
    entry_thesis = Column(Text, nullable=True)
    catalyst = Column(JSON, nullable=True)
    technical_conditions = Column(JSON, nullable=True)
    entry_price = Column(Float, nullable=True)
    stop_price = Column(Float, nullable=True)
    target_price = Column(Float, nullable=True)
    risk_dollars = Column(Float, nullable=True)
    position_size = Column(Float, nullable=True)
    expected_rr = Column(Float, nullable=True)
    signal_score = Column(Float, nullable=True)
    ai_confidence = Column(Float, nullable=True)
    risk_engine_result = Column(JSON, nullable=True)  # {approved: bool, reasons: []}
    order_preview = Column(JSON, nullable=True)
    order_id = Column(String, nullable=True)
    fill_price = Column(Float, nullable=True)
    slippage = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_reason = Column(String, nullable=True)
    pnl = Column(Float, nullable=True)
    r_multiple = Column(Float, nullable=True)
    post_trade_analysis = Column(JSON, nullable=True)
    status = Column(String, default="proposed")  # proposed|rejected|open|closed


class StrategyStats(Base):
    __tablename__ = "strategy_stats"
    strategy = Column(String, primary_key=True)
    enabled = Column(Boolean, default=True)
    trade_count = Column(Integer, default=0)
    win_count = Column(Integer, default=0)
    loss_count = Column(Integer, default=0)
    total_pnl = Column(Float, default=0.0)
    total_r = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=dt.datetime.utcnow)


class StrategyValidationRecord(Base):
    """Evidence produced by a fixed, out-of-sample strategy evaluation.

    A live strategy must have its own passing record.  This is deliberately
    separate from paper/live P&L so a handful of favorable executions can
    never be mistaken for research validation.
    """
    __tablename__ = "strategy_validation_records"
    strategy = Column(String, primary_key=True)
    methodology_version = Column(String, nullable=False)
    evaluated_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    sample_start = Column(DateTime, nullable=True)
    sample_end = Column(DateTime, nullable=True)
    trades = Column(Integer, nullable=False)
    win_rate = Column(Float, nullable=False)
    total_return = Column(Float, nullable=False)
    max_drawdown = Column(Float, nullable=False)
    passed = Column(Boolean, nullable=False, default=False)
    reasons = Column(JSON, nullable=False, default=list)


class OrderIntent(Base):
    """Durable, idempotent record of a submission attempt. intent_key is the primary
    key and is derived from the ORIGINATING DECISION (decision_id), not wall-clock
    time — so retries, restarts, and time-boundary crossings of the SAME decision
    always collide on this key (DB-enforced uniqueness), while a genuinely NEW
    decision (new decision_id) is never suppressed."""
    __tablename__ = "order_intents"
    intent_key = Column(String, primary_key=True)  # sha256(account_id | decision_id)
    decision_id = Column(String, index=True)
    trade_id = Column(String, index=True)
    account_id = Column(String, index=True)
    symbol = Column(String, index=True)
    side = Column(String)
    quantity = Column(Float)
    quantity_filled = Column(Float, default=0.0)
    status = Column(String, default="pending", index=True)
    # pending -> submitted -> {filled, partial, rejected, canceled, unknown}
    # 'unknown' = broker response was not received (timeout/exception after send);
    # must be resolved by reconciliation, never blindly resubmitted.
    broker_order_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow)


class RiskReservation(Base):
    """Aggregate risk/buying-power/sector reservation, held for the lifetime of a
    pending or open position so two individually-valid proposals cannot jointly
    breach account-level limits. Concurrency note: enforced via sequential
    check-then-insert within one process/session — this is NOT a distributed lock
    and does not by itself guarantee correctness across multiple worker processes
    hitting the same account concurrently against a real DB; that requires a
    SELECT ... FOR UPDATE / serializable-isolation transaction in Postgres,
    not implemented against sqlite here. Documented as a deployment requirement."""
    __tablename__ = "risk_reservations"
    id = Column(String, primary_key=True, default=gen_id)
    account_id = Column(String, index=True)
    decision_id = Column(String, index=True)
    risk_dollars = Column(Float)
    notional = Column(Float)
    sector = Column(String, nullable=True)
    status = Column(String, default="active")  # active|released
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class AccountSnapshot(Base):
    """Daily/periodic equity snapshots for drawdown + return calculations."""
    __tablename__ = "account_snapshots"
    id = Column(String, primary_key=True, default=gen_id)
    timestamp = Column(DateTime, default=dt.datetime.utcnow, index=True)
    equity = Column(Float)
    cash = Column(Float)
    buying_power = Column(Float)
    realized_pnl = Column(Float, default=0.0)
    unrealized_pnl = Column(Float, default=0.0)
    stage = Column(Integer, default=0)


class PaperRuntimeState(Base):
    """One isolated simulated account, committed atomically with each paper event."""
    __tablename__ = "paper_runtime"
    id = Column(String, primary_key=True)
    payload = Column(JSON, nullable=False)
    heartbeat = Column(Float, nullable=False)
    status = Column(String, nullable=False, default="waiting")
    last_error = Column(String, nullable=True)


class PaperEvent(Base):
    __tablename__ = "paper_events"
    event_id = Column(String, primary_key=True)
    sequence = Column(Integer, nullable=False, unique=True)
    payload_hash = Column(String, nullable=False)
    result = Column(JSON, nullable=False)


class CapitalStageState(Base):
    __tablename__ = "capital_stage_state"
    id = Column(String, primary_key=True)
    payload = Column(JSON, nullable=False)


class BrokerOAuthState(Base):
    """Short-lived PKCE state. The verifier is not exposed through the API."""
    __tablename__ = "broker_oauth_states"
    state = Column(String, primary_key=True)
    code_verifier = Column(String, nullable=False)
    client_id = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)


class BrokerConnection(Base):
    """One encrypted OAuth session per named broker; never return token fields."""
    __tablename__ = "broker_connections"
    broker = Column(String, primary_key=True)
    client_id = Column(String, nullable=False)
    encrypted_refresh_token = Column(Text, nullable=False)
    connected_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    status = Column(String, nullable=False, default="connected")

class ExternalPaperRuntimeState(Base):
    """Durable state for the external Alpaca paper worker."""
    __tablename__ = "external_paper_runtime"
    id = Column(String, primary_key=True, default=lambda: "alpaca-paper-1")
    payload = Column(JSON, nullable=False)
    heartbeat = Column(Float, nullable=False)
    status = Column(String, nullable=False, default="waiting")

class StrategyScheduleState(Base):
    __tablename__ = "strategy_schedule_state"
    id = Column(String, primary_key=True)
    last_decision_month = Column(String, nullable=True)


class ExternalPaperProtection(Base):
    """One broker-side stop bound to the exact filled external entry order."""
    __tablename__ = "external_paper_protections"
    entry_order_id = Column(String, primary_key=True)
    symbol = Column(String, nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    stop_price = Column(Float, nullable=False)
    protective_order_id = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)


class ExternalLiveProtection(Base):
    """Live-account stop bound to the precise broker entry order.

    This ledger is intentionally separate from paper evidence so an old paper
    stop can never be mistaken for a live position's protection.
    """
    __tablename__ = "external_live_protections"
    entry_order_id = Column(String, primary_key=True)
    symbol = Column(String, nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    stop_price = Column(Float, nullable=False)
    protective_order_id = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)


class RobinhoodTradeLifecycle(Base):
    """Broker-linked entry and stop for one Agentic account trade."""
    __tablename__ = "robinhood_trade_lifecycles"
    trade_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False, index=True)
    asset_class = Column(String, nullable=False)
    symbol = Column(String, nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    stop_price = Column(Float, nullable=False)
    entry_order_id = Column(String, nullable=False, unique=True)
    stop_ref_id = Column(String, nullable=False, unique=True)
    stop_order_id = Column(String, nullable=True, unique=True)
    status = Column(String, nullable=False, default="entry_pending")
    last_error = Column(String, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow,
                        nullable=False)


class ExternalLiveExit(Base):
    """Idempotent live target-exit request tied to one original entry."""
    __tablename__ = "external_live_exits"
    entry_order_id = Column(String, primary_key=True)
    symbol = Column(String, nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    target_price = Column(Float, nullable=False)
    exit_order_id = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="submitted")
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)


class ExternalPaperExit(Base):
    """Idempotent paper target-exit request tied to one original entry."""
    __tablename__ = "external_paper_exits"
    entry_order_id = Column(String, primary_key=True)
    symbol = Column(String, nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    target_price = Column(Float, nullable=False)
    exit_order_id = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="submitted")
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)


class ExternalTargetExitRetry(Base):
    """Durable backoff after an unambiguous target-exit submission failure."""
    __tablename__ = "external_target_exit_retries"
    entry_order_id = Column(String, primary_key=True)
    mode = Column(String, nullable=False)
    retry_after = Column(Float, nullable=False)
    failures = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
