"""Dashboard read-only allocator lots: live/paper isolation and worker-managed levels."""
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models import models


def test_allocator_lots_lists_live_positions_only():
    with TestClient(app) as client:
        db = SessionLocal()
        db.query(models.AllocatorLot).delete()
        for i, (mode, sym, status, exit_px) in enumerate([("live", "EWT", "open", None), ("live", "XLE", "closed", 86.0),
                                                           ("paper", "ROKU", "open", None)]):
            db.add(models.AllocatorLot(id=f"t{i}", mode=mode, sleeve="satellite", symbol=sym, rule="breakout",
                                       quantity=0.5, entry_price=80.0, stop_price=74.4, target_price=92.0,
                                       max_hold_days=30, broker_bracket=False, opened_on="2026-10-07",
                                       status=status, exit_price=exit_px, exit_reason="target" if exit_px else None))
        db.commit()
        db.close()
        body = client.get("/allocator/lots").json()
    lots = {l["symbol"]: l for l in body["lots"]}
    assert set(lots) == {"EWT", "XLE"} and lots["EWT"]["stop_price"] == 74.4
    assert lots["XLE"]["pnl"] == 3.0 and lots["EWT"]["pnl"] is None and not lots["EWT"]["broker_bracket"]
