import uuid
import datetime as dt
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Text, JSON
from app.db.session import Base


def gen_id() -> str:
    return str(uuid.uuid4())


class AuditLogEntry(Base):
    """Immutable audit trail. Never delete rows from this table."""
    __tablename__ = "audit_log"
    id = Column(String, primary_key=True, default=gen_id)
    timestamp = Column(DateTime, default=dt.datetime.utcnow, index=True)
    event_type = Column(String, index=True)  # config_change, risk_veto, trade_decision, state_change, kill_switch, error
    actor = Column(String, default="system")  # system | user | ai
    payload = Column(JSON)


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
