import json
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.core.config import Settings
from app.models.models import (PaperEvent, PaperRuntimeState, RiskReservation,
    StrategyStats, TradeDecisionRecord, AuditLogEntry, SystemStateRecord)
from app.runtime.paper import PaperRuntime, ReplayFrame
from app.services.state_machine import StateManager, PAPER, HALTED


def config(**kwargs):
    return Settings(_env_file=None, AUTO_EXECUTION=True, AUTONOMY_LEVEL=2, **kwargs)


@pytest.fixture
def runtime(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'paper.db'}", connect_args={'timeout': 10})
    rt = PaperRuntime(engine, config())
    rt.enable()
    yield rt
    engine.dispose()


def frame(n=1, price=9.5, **kw):
    return dict(event_id=f'event-{n}', sequence=n, prices={'TST': price}, reference_prices={'TST': 10}, **kw)


def test_entry_stop_and_ledger_survive_restart(runtime):
    first = runtime.process(frame())
    assert first['entries'][0]['status'] == 'filled'
    before = runtime.status()
    assert 'TST' in before['positions']
    restarted = PaperRuntime(runtime.engine, config())
    assert restarted.status()['positions'] == before['positions']
    exit_result = restarted.process(frame(2, 8.9))
    assert exit_result['closed_symbols'] == ['TST']
    assert restarted.status()['positions'] == {}
    with Session(runtime.engine) as db:
        rec = db.query(TradeDecisionRecord).filter_by(status='closed').one()
        assert rec.exit_reason == 'stop_hit'
        assert rec.pnl < 0
        assert db.query(RiskReservation).filter_by(status='active').count() == 0
        stats = db.query(StrategyStats).one()
        assert stats.trade_count == 1 and stats.loss_count == 1
        assert stats.total_pnl == pytest.approx(rec.pnl)
    assert restarted.process(frame(2, 8.9))['duplicate']
    with Session(runtime.engine) as db:
        assert db.query(StrategyStats).one().trade_count == 1


def test_target_closes_and_cancels_stop(runtime):
    runtime.process(frame())
    assert runtime.process(frame(2, 11))['closed_symbols'] == ['TST']
    with Session(runtime.engine) as db:
        row = db.get(PaperRuntimeState, 'paper-1')
        assert row.payload['broker']['pending_stops'] == {}
        rec = db.query(TradeDecisionRecord).filter_by(status='closed').one()
        assert rec.exit_reason == 'target_hit' and rec.pnl > 0


def test_replayed_event_and_concurrent_workers_do_not_duplicate_entry(runtime):
    def tick(_):
        return PaperRuntime(runtime.engine, config()).process(frame())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(tick, range(2)))
    assert sum(bool(r.get('duplicate')) for r in results) == 1
    with Session(runtime.engine) as db:
        assert db.query(PaperEvent).count() == 1
        assert db.query(TradeDecisionRecord).filter_by(status='open').count() == 1
        assert db.query(RiskReservation).filter_by(status='active').count() == 1


def test_exception_rolls_back_broker_audit_and_intents(runtime, monkeypatch):
    import app.runtime.paper as module
    original = module.log_and_commit
    def fail(db, event, payload, **kwargs):
        if event == 'paper_event_committed':
            raise RuntimeError('injected storage failure')
        return original(db, event, payload, **kwargs)
    monkeypatch.setattr(module, 'log_and_commit', fail)
    with pytest.raises(RuntimeError):
        runtime.process(frame())
    assert runtime.status()['positions'] == {}
    assert runtime.status()['cash'] == 100
    with Session(runtime.engine) as db:
        assert db.query(PaperEvent).count() == 0
        assert db.query(TradeDecisionRecord).count() == 0
        assert db.query(RiskReservation).count() == 0
        assert db.query(AuditLogEntry).filter_by(event_type='order_submitted').count() == 0
    monkeypatch.setattr(module, 'log_and_commit', original)
    assert runtime.process(frame())['entries'][0]['status'] == 'filled'


def test_stale_input_pauses_and_fresh_input_recovers(runtime):
    assert runtime.process(frame(source_timestamp=time.time()-60))['status'] == 'blocked'
    assert runtime.status()['positions'] == {}
    assert runtime.process(frame())['entries'][0]['status'] == 'filled'


def test_halt_survives_worker_restart_and_enable_cannot_reset(runtime):
    runtime.halt('test halt')
    restarted = PaperRuntime(runtime.engine, config())
    with pytest.raises(ValueError):
        restarted.enable()
    assert restarted.process(frame())['reason'] == HALTED
    restarted.reset()
    restarted.enable()
    assert restarted.process(frame())['entries'][0]['status'] == 'filled'


def test_reused_event_id_with_changed_price_halts(runtime):
    runtime.process(frame())
    assert runtime.process(frame(price=8))['reason'] == 'event_payload_conflict'
    assert runtime.status()['status'] == 'halted'


def test_lower_sequence_halts(runtime):
    runtime.process(frame(2))
    assert runtime.process(frame(1))['reason'] == 'out_of_order_sequence'


def test_missing_open_position_quote_enters_safe_without_losing_position(runtime):
    runtime.process(frame())
    other = dict(event_id='next', sequence=2, prices={'OTHER': 20})
    assert runtime.process(other)['reason'] == 'missing_quote'
    assert 'TST' in runtime.status()['positions']


def test_market_closed_does_not_fill_or_trigger_stop(runtime):
    runtime.process(frame())
    assert runtime.process(frame(2, 8.9, market_open=False))['closed_symbols'] == []
    assert 'TST' in runtime.status()['positions']


def test_default_configuration_cannot_enable_paper(tmp_path):
    rt = PaperRuntime(create_engine(f"sqlite:///{tmp_path/'default.db'}"), Settings(_env_file=None))
    with pytest.raises(ValueError):
        rt.enable()


def test_live_flag_is_rejected_even_if_paper_mode(runtime):
    with pytest.raises(ValueError):
        PaperRuntime(runtime.engine, config(LIVE_TRADING_ENABLED=True))


def test_bulk_sql_audit_deletion_is_rejected(runtime):
    with runtime.engine.begin() as conn:
        with pytest.raises(Exception):
            conn.execute(text('DELETE FROM audit_log'))


def test_costs_are_persisted_and_cannot_silently_change(runtime):
    with pytest.raises(ValueError):
        PaperRuntime(runtime.engine, config(), commission=1).process(frame())


def test_invalid_frame_rejected_without_writes(runtime):
    with pytest.raises(ValueError):
        runtime.process(frame(price=float('nan')))
    assert runtime.status()['positions'] == {}


def test_heartbeat_does_not_make_stale_feed_ready(runtime):
    runtime.process(frame())
    with Session(runtime.engine) as db:
        row = db.get(PaperRuntimeState, 'paper-1')
        payload = dict(row.payload)
        payload['last_data_at'] = time.time()-60
        row.payload = payload
        db.commit()
    assert not runtime.pulse()['ready']


def test_readiness_reflects_external_halt_immediately(runtime):
    runtime.process(frame())
    assert runtime.status()['ready']
    with Session(runtime.engine) as db:
        StateManager(db).activate_kill_switch('external halt')
    assert not runtime.status()['ready']


def test_fees_are_included_in_trade_pnl_and_risk_budget(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'fees.db'}")
    rt = PaperRuntime(engine, config(), commission=.05)
    rt.enable()
    rt.process(frame())
    rt.process(frame(2, 11))
    with Session(engine) as db:
        rec = db.query(TradeDecisionRecord).filter_by(status='closed').one()
        expected = (rec.exit_price-rec.fill_price)*rec.position_size-.10
        assert rec.pnl == pytest.approx(expected)
        assert rec.risk_dollars <= 1 + 1e-9
        assert rt.status()['cash'] == pytest.approx(100+expected)
    engine.dispose()


def test_api_readiness_uses_runtime_and_data_health(runtime):
    from fastapi.testclient import TestClient
    from app.main import app, get_db
    def override():
        with Session(runtime.engine) as db:
            yield db
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client:
            assert client.get('/ready').status_code == 503
            runtime.process(frame())
            assert client.get('/ready').status_code == 200
            assert client.get('/paper/status').json()['simulated']
            runtime.halt()
            assert client.get('/ready').status_code == 503
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize('break_stop', [False, True])
def test_corrupt_position_or_protection_halts_before_new_entries(runtime, break_stop):
    runtime.process(frame())
    with Session(runtime.engine) as db:
        from copy import deepcopy
        row = db.get(PaperRuntimeState, 'paper-1')
        payload = deepcopy(row.payload)
        if break_stop:
            payload['broker']['pending_stops'] = {}
        else:
            payload['open_trades'] = {}
        row.payload = payload
        db.commit()
    assert runtime.process(frame(2, 9.6))['status'] == 'halted'
    assert not runtime.status()['ready']
