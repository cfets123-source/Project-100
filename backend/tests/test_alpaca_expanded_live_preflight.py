from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models import models  # noqa: F401
from app.models.models import (ExternalPaperExit, ExternalPaperProtection, OrderIntent,
                               RiskReservation, StrategyValidationRecord,
                               SystemStateRecord, TradeDecisionRecord)
from app.runtime.alpaca_expanded_live_preflight import report
from app.strategies.daily_trend_pullback import EXPANDED_STRATEGY_VERSION


def test_preflight_requires_closed_broker_reconciled_paper_lifecycle_and_flat_accounts():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        trade = TradeDecisionRecord(trade_id="paper-trade", symbol="CVX",
                                    strategy=EXPANDED_STRATEGY_VERSION, direction="long",
                                    order_id="entry-1", status="open", fill_price=205)
        db.add_all([
            StrategyValidationRecord(strategy=EXPANDED_STRATEGY_VERSION,
                                     methodology_version="test", trades=126, win_rate=.5,
                                     total_return=.22, max_drawdown=.1, passed=True, reasons=[]),
            SystemStateRecord(id="current", state="live"), trade,
            ExternalPaperProtection(entry_order_id="entry-1", symbol="CVX", quantity=.2,
                                    stop_price=200, protective_order_id="stop-1"),
            OrderIntent(intent_key="intent-1", account_id="paper-account", decision_id="decision-1",
                        trade_id="paper-trade", symbol="CVX", side="buy", quantity=.2),
            RiskReservation(id="risk-1", account_id="paper-account", decision_id="decision-1",
                            risk_dollars=1, notional=41, status="active"),
        ])
        db.commit()
        paper, live = MagicMock(), MagicMock()
        paper.get_positions.return_value = [{"symbol": "CVX", "qty": ".2"}]
        paper.get_orders.return_value = [{"id": "stop-1", "status": "accepted"}]
        paper.get_account_capabilities.return_value = {"status": "ACTIVE"}
        live.get_positions.return_value = []
        live.get_orders.return_value = []
        live.get_account_capabilities.return_value = {"status": "ACTIVE"}
        with patch("app.runtime.alpaca_expanded_live_preflight.load_read_only_adapter",
                   side_effect=[(paper, True), (live, False)] * 4):
            cfg = SimpleNamespace(BROKER_TOKEN_ENCRYPTION_KEY="test")
            pending = report(db, cfg)
            assert not pending["ready"]
            assert "latest expanded paper trade has not closed" in pending["blockers"]
            assert "paper broker still holds a position" in pending["blockers"]

            paper.get_positions.return_value = []
            paper.get_orders.return_value = [
                {"id": "stop-1", "status": "canceled"},
                {"id": "exit-1", "status": "filled", "filled_qty": ".2",
                 "filled_avg_price": "207"},
            ]
            trade.status = "closed"
            trade.exit_price = 207
            trade.pnl = .4
            trade.exit_reason = "session_close"
            trade.post_trade_analysis = {"broker_reconciled": True}
            db.add(ExternalPaperExit(entry_order_id="entry-1", symbol="CVX", quantity=.2,
                                     target_price=0, exit_order_id="exit-1", status="filled"))
            db.commit()
            still_reserved = report(db, cfg)
            assert "paper risk reservation is still active" in still_reserved["blockers"]

            db.get(RiskReservation, "risk-1").status = "released"
            db.commit()
            ready = report(db, cfg)
            assert ready["ready"] is True
            assert ready["paper_lifecycle"]["exit_order_id"] == "exit-1"
            assert ready["order_submission"] is False

            live.get_account_capabilities.return_value = {
                "status": "ACTIVE", "trade_suspended_by_user": True,
            }
            blocked = report(db, cfg)
            assert "live broker account does not permit orders" in blocked["blockers"]
