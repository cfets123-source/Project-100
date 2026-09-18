import json
import os
from pathlib import Path
import subprocess
import sys
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models.models import PaperEvent, TradeDecisionRecord

BACKEND = Path(__file__).resolve().parents[1]


def run_worker(db, feed, enable=False):
    args = [sys.executable, '-m', 'app.runtime.worker', '--database', str(db), 'run', '--feed', str(feed), '--once']
    if enable:
        args.append('--enable-paper')
    env = {**os.environ, 'TRADING_MODE': 'paper', 'LIVE_TRADING_ENABLED': 'false'}
    return subprocess.run(args, cwd=BACKEND, env=env, capture_output=True, text=True, timeout=15)


def test_real_process_restart_restores_position_and_stop(tmp_path):
    db, feed = tmp_path/'paper.db', tmp_path/'feed.jsonl'
    feed.write_text(json.dumps(dict(event_id='entry',sequence=1,prices={'TST':9.5},reference_prices={'TST':10}))+'\n')
    first = run_worker(db, feed, enable=True)
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)['entries'][0]['status'] == 'filled'
    with feed.open('a') as f:
        f.write(json.dumps(dict(event_id='exit',sequence=2,prices={'TST':8.9}))+'\n')
    second = run_worker(db, feed)
    assert second.returncode == 0, second.stderr
    results = [json.loads(line) for line in second.stdout.splitlines()]
    assert results[0]['duplicate']
    assert results[1]['closed_symbols'] == ['TST']
    engine = create_engine(f'sqlite:///{db}')
    with Session(engine) as session:
        assert session.query(PaperEvent).count() == 2
        assert session.query(TradeDecisionRecord).filter_by(status='closed').count() == 1
    engine.dispose()


def test_worker_malformed_input_halts_and_exits(tmp_path):
    db, feed = tmp_path/'paper.db', tmp_path/'feed.jsonl'
    feed.write_text('{malformed}\n')
    result = run_worker(db, feed, enable=True)
    assert result.returncode == 1
    assert json.loads(result.stderr)['status'] == 'failed'
    feed.write_text(json.dumps(dict(event_id='entry',sequence=1,prices={'TST':9.5},reference_prices={'TST':10}))+'\n')
    retry = run_worker(db, feed)
    assert retry.returncode == 2
    assert json.loads(retry.stdout)['reason'] == 'halted'


def test_two_real_worker_processes_commit_one_event(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    db, feed = tmp_path/'paper.db', tmp_path/'feed.jsonl'
    feed.write_text(json.dumps(dict(event_id='entry',sequence=1,prices={'TST':9.5},reference_prices={'TST':10}))+'\n')
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_worker, db, feed, True) for _ in range(2)]
        results = [f.result() for f in futures]
    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    assert sum(bool(json.loads(r.stdout).get('duplicate')) for r in results) == 1
    engine = create_engine(f'sqlite:///{db}')
    with Session(engine) as session:
        assert session.query(PaperEvent).count() == 1
        assert session.query(TradeDecisionRecord).filter_by(status='open').count() == 1
    engine.dispose()
