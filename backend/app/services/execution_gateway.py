"""
ExecutionGateway is the single choke point between a validated Signal and a
BrokerAdapter. Nothing else in the codebase is permitted to call
BrokerAdapter.place_order(). Enforced, in order:

  1. Schema validation (SignalSchema, extra='forbid' -> unknown/injected fields fail closed)
  2. System-state gate (OFF/RESEARCH/SAFE/HALTED block all new entries)
  3. Designated-account enforcement
  4. Deterministic RiskEngine evaluation (per-trade veto/sizing)
  5. Aggregate risk/buying-power/sector reservation (cross-position limits)
  6. Durable, decision-id-keyed idempotent intent (DB primary key, not wall clock)
  7. Mode-specific broker handling: SHADOW never touches a broker; PAPER requires a
     PaperBrokerAdapter; LIVE requires the hard LIVE_TRADING_ENABLED flag AND state==LIVE
  8. State re-check immediately before the broker call (closes the kill-switch race window)
  9. Broker submission; an exception or non-terminal response becomes status='unknown'
     for later reconciliation — NEVER a blind retry
  10. Audit logging at every step, approved or rejected

THREAT MODEL: this class is the only wired-in path to place_order() in this
codebase today. It cannot prevent a future developer from adding another path
that ignores it; that is a code-review/architecture responsibility, documented
in docs/THREAT_MODEL.md, not a runtime guarantee.
"""
import hashlib
import json
from dataclasses import dataclass
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.schemas.signal import SignalSchema
from app.risk.engine import RiskEngine, TradeProposal, RiskDecision
from app.brokers.base import BrokerAdapter, OrderRequest, Quote
from app.brokers.paper_broker import PaperBrokerAdapter
from app.models.models import OrderIntent, TradeDecisionRecord
from app.audit.logger import log_and_commit
from app.services.state_machine import StateManager, SHADOW, PAPER, LIVE
from app.services import risk_budget


class WrongAccountError(Exception):
    pass


@dataclass
class GatewayResult:
    submitted: bool
    reason: str
    trade_id: str | None = None
    order_id: str | None = None
    risk_decision: RiskDecision | None = None


def _intent_key(account_id: str, decision_id: str) -> str:
    return hashlib.sha256(f"{account_id}|{decision_id}".encode()).hexdigest()


class ExecutionGateway:
    def __init__(self, db: Session, broker: BrokerAdapter, risk_engine: RiskEngine,
                 state_manager: StateManager, designated_account_id: str):
        self.db = db
        self.broker = broker
        self.risk_engine = risk_engine
        self.state_manager = state_manager
        self.designated_account_id = designated_account_id

    def submit(self, raw_signal: dict, account_id: str, quote: Quote,
               risk_context: dict, account_equity: float, buying_power: float) -> GatewayResult:
        # --- 1. Schema validation ---
        try:
            signal = SignalSchema(**raw_signal)
        except ValidationError as e:
            log_and_commit(self.db, "signal_rejected_schema",
                            {"errors": json.loads(e.json()), "raw": raw_signal})
            return GatewayResult(submitted=False, reason="schema_validation_failed")

        # --- 2. System-state gate ---
        allowed, why = self.state_manager.can_open_new_entries()
        if not allowed:
            log_and_commit(self.db, "entry_blocked_by_state", {"symbol": signal.symbol, "reason": why})
            return GatewayResult(submitted=False, reason=why)

        # --- 3. Designated-account enforcement ---
        if account_id != self.designated_account_id:
            log_and_commit(self.db, "wrong_account_blocked",
                            {"attempted": account_id, "designated": self.designated_account_id})
            raise WrongAccountError(f"account {account_id} is not the designated Project 100 account")

        # --- 4. Deterministic per-trade risk evaluation ---
        proposal = TradeProposal(
            symbol=signal.symbol, direction=signal.direction, entry_price=signal.entry_price,
            stop_price=signal.stop_price, quote=quote, strategy=signal.strategy,
            account_equity=account_equity, **risk_context,
        )
        decision = self.risk_engine.evaluate(proposal)
        log_and_commit(self.db, "risk_decision", {
            "symbol": signal.symbol, "decision_id": signal.decision_id, "approved": decision.approved,
            "reasons": decision.reasons, "position_size": decision.position_size,
        })
        if not decision.approved:
            self.db.add(TradeDecisionRecord(
                symbol=signal.symbol, strategy=signal.strategy, direction=signal.direction,
                entry_thesis=signal.thesis, entry_price=signal.entry_price, stop_price=signal.stop_price,
                ai_confidence=signal.ai_confidence,
                risk_engine_result={"approved": False, "reasons": decision.reasons}, status="rejected",
            ))
            self.db.commit()
            return GatewayResult(submitted=False, reason=",".join(decision.reasons), risk_decision=decision)

        # --- 5. Aggregate reservation (cross-position/sector, buying power) ---
        notional = decision.position_size * signal.entry_price
        reservation = risk_budget.reserve(
            self.db, account_id=account_id, decision_id=signal.decision_id,
            risk_dollars=decision.risk_dollars, notional=notional, account_equity=account_equity,
            buying_power=buying_power, sector=risk_context.get("sector"), cfg=self.risk_engine.cfg,
        )
        if not reservation.approved:
            log_and_commit(self.db, "aggregate_risk_rejected", {"symbol": signal.symbol,
                                                                  "reason": reservation.reason})
            return GatewayResult(submitted=False, reason=reservation.reason, risk_decision=decision)

        # --- 6. Durable, decision-id-keyed idempotent intent ---
        key = _intent_key(account_id, signal.decision_id)
        existing = self.db.get(OrderIntent, key)
        if existing is not None:
            risk_budget.release(self.db, reservation.reservation_id)  # don't double-hold budget
            log_and_commit(self.db, "duplicate_intent_blocked", {"intent_key": key, "status": existing.status})
            return GatewayResult(submitted=False, reason="duplicate_intent_suppressed")

        intent = OrderIntent(intent_key=key, decision_id=signal.decision_id, account_id=account_id,
                              symbol=signal.symbol, side="buy" if signal.direction == "long" else "sell",
                              quantity=decision.position_size, status="pending")
        self.db.add(intent)
        try:
            self.db.commit()
        except Exception:
            # Primary-key collision under concurrent submission of the SAME decision_id:
            # the DB itself is the source of truth for uniqueness, not app-level check-then-act.
            self.db.rollback()
            risk_budget.release(self.db, reservation.reservation_id)
            log_and_commit(self.db, "duplicate_intent_blocked_db_constraint", {"intent_key": key})
            return GatewayResult(submitted=False, reason="duplicate_intent_suppressed")

        rec = TradeDecisionRecord(
            symbol=signal.symbol, strategy=signal.strategy, direction=signal.direction,
            entry_thesis=signal.thesis, entry_price=signal.entry_price, stop_price=signal.stop_price,
            target_price=signal.target_price, position_size=decision.position_size,
            risk_dollars=decision.risk_dollars, ai_confidence=signal.ai_confidence,
            risk_engine_result={"approved": True, "reasons": []}, status="open",
        )
        self.db.add(rec)
        self.db.commit()
        self.db.refresh(rec)
        intent.trade_id = rec.trade_id
        self.db.commit()

        # --- 7. Mode-specific broker handling ---
        state = self.state_manager.get_state()
        if state == SHADOW:
            intent.status = "shadow_only"
            rec.status = "shadow_only"
            self.db.commit()
            log_and_commit(self.db, "shadow_decision_recorded", {"trade_id": rec.trade_id, "symbol": signal.symbol})
            return GatewayResult(submitted=False, reason="shadow_mode_no_broker_call",
                                  trade_id=rec.trade_id, risk_decision=decision)

        if state == PAPER and not isinstance(self.broker, PaperBrokerAdapter):
            # Defense in depth: PAPER state must never be wired to a real adapter.
            raise RuntimeError("PAPER state requires a PaperBrokerAdapter; refusing to submit")

        if state == LIVE:
            live_ok, live_why = self.state_manager.live_broker_mutation_allowed()
            if not live_ok:
                intent.status = "rejected"
                self.db.commit()
                log_and_commit(self.db, "live_execution_blocked", {"symbol": signal.symbol, "reason": live_why})
                return GatewayResult(submitted=False, reason=live_why, trade_id=rec.trade_id)

        # --- 8. Re-check state immediately before the broker call (kill-switch race window) ---
        recheck_allowed, recheck_why = self.state_manager.can_open_new_entries()
        if not recheck_allowed:
            intent.status = "canceled"
            self.db.commit()
            log_and_commit(self.db, "entry_blocked_by_state_at_recheck", {"symbol": signal.symbol,
                                                                            "reason": recheck_why})
            return GatewayResult(submitted=False, reason=recheck_why, trade_id=rec.trade_id)

        # --- 9. Broker submission — exceptions/uncertain outcomes never trigger a retry here ---
        order = OrderRequest(symbol=signal.symbol, side=intent.side, quantity=decision.position_size)
        try:
            result = self.broker.place_order(order)
        except Exception as e:  # noqa: BLE001 — broker-side failure of unknown kind
            intent.status = "unknown"
            self.db.commit()
            log_and_commit(self.db, "uncertain_broker_outcome", {"trade_id": rec.trade_id,
                                                                   "intent_key": key, "error": str(e)})
            return GatewayResult(submitted=False, reason="uncertain_outcome_pending_reconciliation",
                                  trade_id=rec.trade_id, risk_decision=decision)

        intent.status = result.status
        intent.quantity_filled = result.filled_qty
        intent.broker_order_id = result.order_id
        rec.order_id = result.order_id
        rec.fill_price = result.fill_price
        if result.status == "rejected":
            rec.status = "rejected"
            risk_budget.release(self.db, reservation.reservation_id)
        self.db.commit()

        log_and_commit(self.db, "order_submitted", {
            "trade_id": rec.trade_id, "intent_key": key, "broker_order_id": result.order_id,
            "status": result.status,
        })

        return GatewayResult(submitted=result.status == "filled", reason=result.status,
                              trade_id=rec.trade_id, order_id=result.order_id, risk_decision=decision)
