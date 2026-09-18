from unittest.mock import MagicMock
from app.runtime.alpaca_paper_controller import evaluate_candidate

SIGNAL = {"symbol":"AAPL", "direction":"long", "strategy":"test", "decision_id":"d1", "entry_price":10.0, "stop_price":9.5, "target_price":11.0, "thesis":"test", "ai_confidence":0.5}
CONTEXT = {"avg_dollar_volume":5_000_000, "sector":"test", "open_position_count":0, "daily_pnl_pct":0.0, "weekly_drawdown_pct":0.0, "total_drawdown_pct":0.0}

def test_controller_stops_before_broker_when_prerequisites_fail(monkeypatch):
    monkeypatch.setattr('app.runtime.alpaca_paper_controller.execution_prerequisites', lambda *_: {"ready":False,"reason":"stale_quote"})
    assert evaluate_candidate(MagicMock(), MagicMock(), 'acct', SIGNAL, CONTEXT) == {"submitted":False,"reason":"stale_quote"}
