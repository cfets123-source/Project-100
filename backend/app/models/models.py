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
