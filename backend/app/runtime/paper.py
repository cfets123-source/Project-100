"""Durable, SQLite-only simulation runtime. Never constructs a real adapter.

Each replay event holds SQLite's write lock and commits broker state, intents,
ledger, audit, statistics, and event deduplication together. This guarantee is
specific to an in-process simulated broker; it cannot cover external execution.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
import datetime as dt
import hashlib
import json
import math
import time
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.audit.logger import log_and_commit
from app.brokers.base import Quote, OrderRequest, OrderResult
from app.brokers.paper_broker import PaperBrokerAdapter
from app.core.config import Settings
from app.db.session import Base
from app.market_data.base import MarketQuote, validate_quote
from app.models.models import (PaperRuntimeState, PaperEvent, OrderIntent,
    RiskReservation, TradeDecisionRecord, StrategyStats, AccountSnapshot, SystemStateRecord)
from app.risk.engine import RiskEngine
from app.services.execution_gateway import ExecutionGateway
from app.services.protective_exit import place_protective_stop
from app.services.state_machine import StateManager, OFF, PAPER, SAFE, HALTED
from app.strategies.test_dip_buy import TestDipBuyStrategy

ACCOUNT = "paper-1"


class ReplayFrame(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    event_id: str = Field(min_length=1, max_length=128)
    sequence: int = Field(ge=0, strict=True)
    prices: dict[str, float]
    reference_prices: dict[str, float] = Field(default_factory=dict)
    # Omission means synthetic prices sampled at processing time, NEVER a claim
    # of real-time market data. Explicit timestamps undergo freshness checks.
    source_timestamp: float | None = None
    market_open: bool = True

    @model_validator(mode="after")
    def valid_prices(self):
        if not self.prices or len(self.prices) > 100:
            raise ValueError("provide 1 to 100 simulated symbols")
        for symbol, price in list(self.prices.items()) + list(self.reference_prices.items()):
            if not symbol or not math.isfinite(price) or price <= 0:
                raise ValueError("symbols and prices must be valid")
        return self


class FrameProvider:
    def __init__(self, frame):
        self.frame = frame
        self.received = time.time()
        self.source = frame.source_timestamp if frame.source_timestamp is not None else self.received

    def get_quote(self, symbol):
        if symbol not in self.frame.prices:
            return None
        px = self.frame.prices[symbol]
        return MarketQuote("replay-simulation", symbol, "equity",
                           "open" if self.frame.market_open else "closed",
                           self.source, self.received, px * .999, px * 1.001, px,
                           entitlement="simulated")

    def get_account_snapshot_age_seconds(self):
        return time.time() - self.received

    def broker_quotes(self, symbols):
        quotes = []
        for symbol in symbols:
            q = self.get_quote(symbol)
            if q is None:
                raise ValueError("missing simulated position quote")
            quotes.append(Quote(q.source, symbol, q.source_timestamp, q.age_seconds,
                                q.bid, q.ask, q.last, q.market_session))
        return quotes


def serialize_broker(broker):
    return {"cash": broker.cash, "starting_cash": broker.starting_cash,
            "positions": deepcopy(broker.positions), "pending_stops": deepcopy(broker.pending_stops),
            "orders": {oid: {"order": asdict(v["order"]), "result": asdict(v["result"]), "ts": v["ts"]}
                       for oid, v in broker.orders.items()}}


def restore_broker(payload, provider, fee, slippage):
    broker = PaperBrokerAdapter(payload["starting_cash"], provider.broker_quotes, fee, slippage)
    broker.cash = payload["cash"]
    broker.positions = deepcopy(payload["positions"])
    broker.pending_stops = deepcopy(payload["pending_stops"])
    broker.orders = {oid: {"order": OrderRequest(**v["order"]), "result": OrderResult(**v["result"]), "ts": v["ts"]}
                     for oid, v in payload["orders"].items()}
    # A replay event explicitly describes its simulated session. No actual
    # exchange-calendar or real-time quote guarantee is implied.
    broker._is_market_open = lambda: provider.frame.market_open
    return broker


class PaperRuntime:
    def __init__(self, engine, cfg=None, *, commission=0.0, slippage_bps=5.0):
        self.engine = engine
        self.cfg = cfg or Settings()
        if engine.dialect.name != "sqlite":
            raise ValueError("paper runtime currently requires SQLite; Postgres locking is not implemented")
        if self.cfg.TRADING_MODE != "paper" or self.cfg.LIVE_TRADING_ENABLED:
            raise ValueError("paper runtime refuses Live configuration")
        if not all(math.isfinite(v) and v >= 0 for v in (commission, slippage_bps)):
            raise ValueError("invalid simulation cost configuration")
        if slippage_bps >= 10000:
            raise ValueError("slippage must be less than 100 percent")
        for field in ("MAX_RISK_PER_TRADE", "MAX_DAILY_LOSS", "MAX_WEEKLY_DRAWDOWN",
                      "MAX_TOTAL_DRAWDOWN", "MAX_POSITION_PCT", "MAX_SECTOR_CONCENTRATION"):
            value = getattr(self.cfg, field)
            if not math.isfinite(value) or not 0 < value <= 1:
                raise ValueError(f"{field} must be a finite fraction in (0, 1]")
        if self.cfg.MAX_POSITIONS < 1 or self.cfg.MAX_QUOTE_AGE_SECONDS < 0:
            raise ValueError("invalid position or freshness limit")
        self.fee, self.slippage = commission, slippage_bps
        self.strategy = TestDipBuyStrategy()
        # Stronger than ORM events for this SQLite simulation. Administrators
        # can still drop triggers or edit the database file; no such claim made.
        with engine.connect() as conn:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            Base.metadata.create_all(conn)
            for action in ("UPDATE", "DELETE"):
                conn.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS paper_audit_no_{action.lower()} "
                    f"BEFORE {action} ON audit_log BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END")
            conn.commit()

    @contextmanager
    def transaction(self):
        with self.engine.connect() as conn:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            with Session(bind=conn, expire_on_commit=False) as db:
                db.info["transaction_owner"] = "paper_runtime"
                try:
                    yield db
                    db.flush()
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise

    def _state(self, db):
        row = db.get(PaperRuntimeState, ACCOUNT)
        if row is None:
            if db.query(OrderIntent).first() is not None:
                raise ValueError("use a clean simulation database; legacy orders require explicit migration")
            cash = self.cfg.STARTING_CAPITAL
            if not math.isfinite(cash) or cash <= 0:
                raise ValueError("starting capital must be finite and positive")
            payload = {"schema_version": 1, "last_sequence": -1, "last_data_at": None,
                "broker": {"cash": cash, "starting_cash": cash, "positions": {}, "pending_stops": {}, "orders": {}},
                "open_trades": {}, "high_water": cash, "realized_pnl": 0.0,
                "day": None, "week": None, "day_equity": cash, "week_equity": cash,
                "last_equity": cash, "costs": {"commission": self.fee, "slippage_bps": self.slippage},
                "strategy": self.strategy.name, "max_drawdown": 0.0}
            row = PaperRuntimeState(id=ACCOUNT, payload=payload, heartbeat=time.time(), status="waiting")
            db.add(row)
            db.flush()
        if row.payload.get("schema_version") != 1:
            raise ValueError("unsupported paper state schema")
        if row.payload["costs"] != {"commission": self.fee, "slippage_bps": self.slippage}:
            raise ValueError("simulation costs changed; use an explicitly separate simulation database")
        return row

    def enable(self):
        if not self.cfg.AUTO_EXECUTION or int(self.cfg.AUTONOMY_LEVEL) != 2:
            raise ValueError("paper enablement requires AUTO_EXECUTION=true and AUTONOMY_LEVEL=2")
        with self.transaction() as db:
            self._state(db)
            sm = StateManager(db, self.cfg)
            if sm.get_state() == PAPER:
                return
            if sm.get_state() != OFF:
                raise ValueError("enable only from OFF; safety shutdowns cannot be reset by worker startup")
            sm.transition(PAPER, "explicit_paper_enablement", actor="operator")

    def pulse(self):
        with self.transaction() as db:
            row = self._state(db)
            row.heartbeat = time.time()
        return self.status()

    def halt(self, reason="operator request"):
        with self.transaction() as db:
            row = self._state(db)
            StateManager(db, self.cfg).activate_kill_switch(reason, actor="operator")
            row.status = "halted"
            row.heartbeat = time.time()

    def reset(self):
        with self.transaction() as db:
            self._state(db)
            StateManager(db, self.cfg).reset(actor="operator", confirm=True)

    def process(self, frame):
        if not isinstance(frame, ReplayFrame):
            frame = ReplayFrame.model_validate(frame)
        digest = hashlib.sha256(json.dumps(frame.model_dump(), sort_keys=True).encode()).hexdigest()
        with self.transaction() as db:
            row = self._state(db)
            sm = StateManager(db, self.cfg)
            previous = db.get(PaperEvent, frame.event_id)
            row.heartbeat = time.time()
            if previous:
                if previous.payload_hash != digest:
                    sm.activate_kill_switch("replay event ID reused with different content")
                    row.status = "halted"
                    return {"status": "halted", "reason": "event_payload_conflict"}
                return {**previous.result, "duplicate": True}
            data = deepcopy(row.payload)
            if frame.sequence <= data["last_sequence"]:
                sm.activate_kill_switch("out-of-order replay sequence")
                row.status = "halted"
                return {"status": "halted", "reason": "out_of_order_sequence"}
            mode = sm.get_state()
            if mode not in (PAPER, SAFE):
                row.status = "halted" if mode == HALTED else "waiting"
                return {"status": "blocked", "reason": mode}
            if mode == PAPER and (not self.cfg.AUTO_EXECUTION or int(self.cfg.AUTONOMY_LEVEL) != 2):
                raise ValueError("paper execution no longer authorized by configuration")
            provider = FrameProvider(frame)
            required = set(frame.prices) | set(data["broker"]["positions"])
            for symbol in required:
                check = validate_quote(provider.get_quote(symbol), self.cfg.MAX_QUOTE_AGE_SECONDS)
                if not check.valid:
                    sm.enter_safe_mode(f"paper_data:{check.reason}")
                    row.status, row.last_error = "data_unavailable", check.reason
                    return {"status": "blocked", "reason": check.reason}
            if mode == SAFE and (sm.get_record().reason or "").startswith("paper_data:"):
                if self.cfg.AUTO_EXECUTION and int(self.cfg.AUTONOMY_LEVEL) == 2:
                    sm.resume_from_safe(PAPER, "simulation data recovered")
            broker = restore_broker(data["broker"], provider, self.fee, self.slippage)
            if set(broker.positions) != set(data["open_trades"]):
                sm.activate_kill_switch("paper position/ledger mismatch")
                row.status = "halted"
                return {"status": "halted", "reason": "position_ledger_mismatch"}
            for symbol, trade in data["open_trades"].items():
                stop = broker.pending_stops.get(trade["stop_id"])
                if not stop or stop["symbol"] != symbol or not math.isclose(stop["quantity"], broker.positions[symbol]["qty"]):
                    sm.activate_kill_switch("paper position lacks matching protective order")
                    row.status = "halted"
                    return {"status": "halted", "reason": "unprotected_position"}
            closed = self._manage_exits(db, broker, data, frame)
            balances = broker.get_balances()
            equity = balances["equity"]
            today = dt.datetime.now(ZoneInfo("America/New_York")).date()
            week = today - dt.timedelta(days=today.weekday())
            for key, period in (("day", today.isoformat()), ("week", week.isoformat())):
                if data[key] != period:
                    data[key] = period
                    data[f"{key}_equity"] = data["last_equity"]
            data["high_water"] = max(data["high_water"], equity)
            daily = equity / data["day_equity"] - 1
            weekly = max(0, 1 - equity / data["week_equity"])
            total = max(0, 1 - equity / data["high_water"])
            data["max_drawdown"] = max(data.get("max_drawdown", 0), total)
            if total >= self.cfg.MAX_TOTAL_DRAWDOWN or weekly >= self.cfg.MAX_WEEKLY_DRAWDOWN:
                sm.activate_kill_switch("paper drawdown breach")
            elif daily <= -self.cfg.MAX_DAILY_LOSS:
                sm.enter_safe_mode(f"paper_daily_loss:{today.isoformat()}")
            elif sm.get_state() == SAFE and (sm.get_record().reason or "").startswith("paper_daily_loss:"):
                if sm.get_record().reason != f"paper_daily_loss:{today.isoformat()}":
                    sm.resume_from_safe(PAPER, "new paper trading day")
            entries = []
            if sm.get_state() == PAPER and frame.market_open:
                for symbol in self.strategy.scan(sorted(frame.prices)):
                    if symbol in broker.positions or symbol in closed:
                        continue
                    context = {"last_price": frame.prices[symbol],
                               "reference_price": frame.reference_prices.get(symbol)}
                    signal = self.strategy.generate_signal(symbol, context)
                    if not signal:
                        continue
                    signal["decision_id"] = f"{self.strategy.name}:{frame.event_id}:{symbol}"
                    # Size against the simulated executable ask including slippage.
                    signal["entry_price"] = provider.get_quote(symbol).ask * (1 + self.slippage / 10000)
                    gw = ExecutionGateway(db, broker, RiskEngine(self.cfg), sm, ACCOUNT, provider)
                    active_notional = db.query(func.coalesce(func.sum(RiskReservation.notional), 0)).filter_by(
                        account_id=ACCOUNT, status="active").scalar()
                    risk_context = dict(avg_dollar_volume=5_000_000, sector="simulated",
                        open_position_count=len(broker.positions), daily_pnl_pct=daily,
                        weekly_drawdown_pct=weekly, total_drawdown_pct=total,
                        estimated_round_trip_fees=2*self.fee)
                    # Existing filled notional is already deducted from cash; add
                    # it back only for the aggregate reservation comparison.
                    outcome = gw.submit(signal, ACCOUNT, provider.broker_quotes([symbol])[0], risk_context,
                                        equity, broker.cash + active_notional)
                    entries.append({"symbol": symbol, "status": outcome.reason})
                    if not outcome.submitted:
                        continue
                    rec = db.get(TradeDecisionRecord, outcome.trade_id)
                    qty = outcome.risk_decision.position_size
                    before = set(broker.pending_stops)
                    protected = place_protective_stop(db, broker, sm, symbol, qty, signal["stop_price"])
                    stop_ids = set(broker.pending_stops) - before
                    data["open_trades"][symbol] = {"trade_id": rec.trade_id, "decision_id": signal["decision_id"],
                        "stop_id": next(iter(stop_ids)) if stop_ids else None,
                        "target": signal["target_price"], "entry_fee": self.fee}
                    if not protected:
                        break
            equity = broker.get_balances()["equity"]
            data.update(broker=serialize_broker(broker), last_sequence=frame.sequence,
                        last_data_at=time.time(), last_equity=equity)
            row.payload = data
            row.status = "halted" if sm.get_state() == HALTED else "healthy" if sm.get_state() == PAPER else "safe"
            row.last_error = None
            result = {"status": row.status, "sequence": frame.sequence, "entries": entries,
                      "closed_symbols": sorted(closed), "equity": equity, "simulated": True}
            db.add(PaperEvent(event_id=frame.event_id, sequence=frame.sequence, payload_hash=digest, result=result))
            db.add(AccountSnapshot(equity=equity, cash=broker.cash, buying_power=broker.cash,
                                   realized_pnl=data["realized_pnl"],
                                   unrealized_pnl=equity-broker.starting_cash-data["realized_pnl"]))
            log_and_commit(db, "paper_event_committed", {"event_id": frame.event_id, **result})
            return result

    def _manage_exits(self, db, broker, data, frame):
        closed = set()
        if not frame.market_open:
            return closed
        fired = {r.order_id: r for r in broker.check_and_trigger_stops()}
        for symbol, trade in list(data["open_trades"].items()):
            result = fired.get(trade["stop_id"])
            reason = "stop_hit"
            if result is None and frame.prices[symbol] >= trade["target"]:
                result = broker.place_order(OrderRequest(symbol, "sell", broker.positions[symbol]["qty"]))
                reason = "target_hit"
                if result.status == "filled" and trade["stop_id"]:
                    broker.cancel_order(trade["stop_id"])
            if result is None or result.status != "filled":
                continue
            rec = db.get(TradeDecisionRecord, trade["trade_id"])
            pnl = (result.fill_price-rec.fill_price)*result.filled_qty - trade["entry_fee"] - self.fee
            rec.status, rec.exit_price, rec.exit_reason = "closed", result.fill_price, reason
            rec.pnl = pnl
            rec.r_multiple = pnl / rec.risk_dollars if rec.risk_dollars else 0
            for reservation in db.query(RiskReservation).filter_by(account_id=ACCOUNT,
                    decision_id=trade["decision_id"], status="active").all():
                reservation.status = "released"
            stats_key = f"paper:{rec.strategy}"
            stats = db.get(StrategyStats, stats_key)
            if stats is None:
                stats = StrategyStats(strategy=stats_key, trade_count=0, win_count=0, loss_count=0,
                                      total_pnl=0, total_r=0, max_drawdown=0)
                db.add(stats)
            stats.trade_count += 1
            stats.win_count += int(pnl > 0)
            stats.loss_count += int(pnl < 0)
            stats.total_pnl += pnl
            stats.total_r += rec.r_multiple
            data["realized_pnl"] += pnl
            del data["open_trades"][symbol]
            closed.add(symbol)
            log_and_commit(db, "paper_trade_closed", {"trade_id": rec.trade_id, "symbol": symbol,
                "order_id": result.order_id, "reason": reason, "pnl": pnl, "r_multiple": rec.r_multiple})
        return closed

    def status(self):
        with Session(self.engine) as db:
            return paper_status(db)


def paper_status(db):
    row = db.get(PaperRuntimeState, ACCOUNT)
    state = db.get(SystemStateRecord, "current")
    if row is None:
        return {"status": "not_started", "simulated": True, "ready": False}
    age = max(0, time.time()-row.heartbeat)
    payload = row.payload
    data_age = None if payload["last_data_at"] is None else max(0, time.time()-payload["last_data_at"])
    return {"status": row.status, "state": state.state if state else "off", "simulated": True,
            "ready": bool(state and state.state == PAPER and row.status == "healthy" and age <= 30
                          and data_age is not None and data_age <= 30),
            "heartbeat_age_seconds": age, "data_age_seconds": data_age,
            "last_sequence": payload["last_sequence"], "equity": payload["last_equity"],
            "cash": payload["broker"]["cash"], "positions": payload["broker"]["positions"],
            "realized_pnl": payload["realized_pnl"], "max_drawdown": payload.get("max_drawdown", 0),
            "last_error": row.last_error}
