"""
ExecutionGateway is the single choke point between a validated Signal and a
BrokerAdapter. Nothing else in the codebase is permitted to call
BrokerAdapter.place_order(). This module enforces, in order:

  1. Schema validation (SignalSchema, extra='forbid' -> unknown/injected fields fail closed)
  2. Designated-account enforcement (never the first account returned by a broker)
  3. Deterministic RiskEngine evaluation (approve/veto, sizing)
  4. Idempotent order-intent persistence (dedupe retries/restarts/duplicate workers)
  5. Broker submission + fill/rejection reconciliation
  6. Audit logging of every step, approved or rejected

If the RiskEngine rejects, execution stops here: place_order is never reached.
"""
import hashlib
import json
import time
from dataclasses import dataclass
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.schemas.signal import SignalSchema
from app.risk.engine import RiskEngine, TradeProposal, RiskDecision
from app.brokers.base import BrokerAdapter, OrderRequest, Quote
from app.models.models import OrderIntent, TradeDecisionRecord
from app.audit.logger import log_and_commit


class WrongAccountError(Exception):
    pass


@dataclass
class GatewayResult:
    submitted: bool
    reason: str
    trade_id: str | None = None
    order_id: str | None = None
    risk_decision: RiskDecision | None = None


def _intent_key(account_id: str, signal: dict, time_bucket: int) -> str:
    raw = f"{account_id}|{signal['symbol']}|{signal['strategy']}|{signal['direction']}|{time_bucket}"
    return hashlib.sha256(raw.encode()).hexdigest()


class ExecutionGateway:
    def __init__(self, db: Session, broker: BrokerAdapter, risk_engine: RiskEngine,
                 designated_account_id: str):
        self.db = db
        self.broker = broker
        self.risk_engine = risk_engine
        self.designated_account_id = designated_account_id

    def submit(self, raw_signal: dict, account_id: str, quote: Quote,
               risk_context: dict) -> GatewayResult:
        # --- 1. Schema validation: fail closed on unknown/malformed fields ---
        try:
            signal = SignalSchema(**raw_signal)
        except ValidationError as e:
            # e.errors() may embed non-JSON-serializable objects (e.g. the raised
            # ValueError itself) in 'ctx'; e.json() guarantees a JSON-safe payload.
            log_and_commit(self.db, "signal_rejected_schema",
                            {"errors": json.loads(e.json()), "raw": raw_signal})
            return GatewayResult(submitted=False, reason="schema_validation_failed")

        # --- 2. Designated-account enforcement ---
        if account_id != self.designated_account_id:
            log_and_commit(self.db, "wrong_account_blocked",
                            {"attempted": account_id, "designated": self.designated_account_id})
            raise WrongAccountError(f"account {account_id} is not the designated Project 100 account")

        # --- 3. Deterministic risk evaluation (final authority) ---
        proposal = TradeProposal(
            symbol=signal.symbol, direction=signal.direction, entry_price=signal.entry_price,
            stop_price=signal.stop_price, quote=quote, strategy=signal.strategy,
            **risk_context,
        )
        decision = self.risk_engine.evaluate(proposal)
        log_and_commit(self.db, "risk_decision", {
            "symbol": signal.symbol, "approved": decision.approved, "reasons": decision.reasons,
            "position_size": decision.position_size,
        })
        if not decision.approved:
            rec = TradeDecisionRecord(
                symbol=signal.symbol, strategy=signal.strategy, direction=signal.direction,
                entry_thesis=signal.thesis, entry_price=signal.entry_price, stop_price=signal.stop_price,
                ai_confidence=signal.ai_confidence,
                risk_engine_result={"approved": False, "reasons": decision.reasons}, status="rejected",
            )
            self.db.add(rec)
            self.db.commit()
            return GatewayResult(submitted=False, reason=",".join(decision.reasons), risk_decision=decision)

        # --- 4. Idempotent intent (dedupe retries / restarts / duplicate workers) ---
        time_bucket = int(time.time() // 60)  # 1-minute dedupe window
        key = _intent_key(account_id, raw_signal, time_bucket)
        existing = self.db.get(OrderIntent, key)
        if existing is not None:
            log_and_commit(self.db, "duplicate_intent_blocked", {"intent_key": key, "status": existing.status})
            return GatewayResult(submitted=False, reason="duplicate_intent_suppressed")

        intent = OrderIntent(intent_key=key, account_id=account_id, symbol=signal.symbol,
                              side="buy" if signal.direction == "long" else "sell",
                              quantity=decision.position_size, status="pending")
        self.db.add(intent)
        self.db.commit()

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

        # --- 5. Broker submission (only reachable path to place_order) ---
        order = OrderRequest(symbol=signal.symbol, side=intent.side, quantity=decision.position_size)
        result = self.broker.place_order(order)

        intent.status = result.status if result.status != "filled" else "filled"
        intent.broker_order_id = result.order_id
        rec.order_id = result.order_id
        rec.fill_price = result.fill_price
        self.db.commit()

        log_and_commit(self.db, "order_submitted", {
            "trade_id": rec.trade_id, "intent_key": key, "broker_order_id": result.order_id,
            "status": result.status,
        })

        return GatewayResult(submitted=result.status == "filled", reason=result.status,
                              trade_id=rec.trade_id, order_id=result.order_id, risk_decision=decision)
