from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from app.db.session import Base, engine, get_db
from app.models import models  # noqa: F401 ensures models are registered
from app.core.config import settings

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Project 100", version="0.1.0-phase1")


@app.get("/health")
def health():
    return {"status": "ok", "trading_mode": settings.TRADING_MODE, "autonomy_level": settings.AUTONOMY_LEVEL}


@app.get("/system/state")
def get_state(db: Session = Depends(get_db)):
    rec = db.get(models.SystemStateRecord, "current")
    if not rec:
        rec = models.SystemStateRecord(id="current", state="off", reason="initial")
        db.add(rec)
        db.commit()
        db.refresh(rec)
    return {"state": rec.state, "reason": rec.reason, "updated_at": rec.updated_at}


@app.get("/config/risk")
def get_risk_config():
    """Read-only view of active risk configuration (no secrets)."""
    return {
        "MAX_RISK_PER_TRADE": settings.MAX_RISK_PER_TRADE,
        "MAX_DAILY_LOSS": settings.MAX_DAILY_LOSS,
        "MAX_WEEKLY_DRAWDOWN": settings.MAX_WEEKLY_DRAWDOWN,
        "MAX_TOTAL_DRAWDOWN": settings.MAX_TOTAL_DRAWDOWN,
        "MAX_POSITIONS": settings.MAX_POSITIONS,
        "ALLOW_MARGIN": settings.ALLOW_MARGIN,
        "ALLOW_OPTIONS": settings.ALLOW_OPTIONS,
        "ALLOW_SHORTS": settings.ALLOW_SHORTS,
        "ALLOW_LEVERAGE": settings.ALLOW_LEVERAGE,
        "AUTO_EXECUTION": settings.AUTO_EXECUTION,
    }
