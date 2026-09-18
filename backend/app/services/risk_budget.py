"""
Aggregate reservation of risk-dollars, notional (buying power), and sector
exposure across ALL pending+open positions for an account — so two proposals
that are each individually valid under RiskEngine can still be jointly rejected
if they would together breach account-level limits.

CONCURRENCY LIMITATION (documented, not hidden): this is a sequential
check-then-insert within one Python process/session. Against sqlite in tests
this is deterministic. Against a real multi-worker deployment on Postgres this
requires `SELECT ... FOR UPDATE` (or SERIALIZABLE isolation) around the
check+insert to be race-free across processes — not implemented here.
"""
from dataclasses import dataclass
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.transactions import persist
from app.models.models import RiskReservation
from app.core.config import Settings


@dataclass
class ReservationResult:
    approved: bool
    reason: str = ""
    reservation_id: str | None = None


def _active_totals(db: Session, account_id: str, sector: str | None):
    risk_sum = db.query(func.coalesce(func.sum(RiskReservation.risk_dollars), 0.0)).filter(
        RiskReservation.account_id == account_id, RiskReservation.status == "active").scalar()
    notional_sum = db.query(func.coalesce(func.sum(RiskReservation.notional), 0.0)).filter(
        RiskReservation.account_id == account_id, RiskReservation.status == "active").scalar()
    sector_sum = 0.0
    if sector:
        sector_sum = db.query(func.coalesce(func.sum(RiskReservation.notional), 0.0)).filter(
            RiskReservation.account_id == account_id, RiskReservation.status == "active",
            RiskReservation.sector == sector).scalar()
    return risk_sum, notional_sum, sector_sum


def reserve(db: Session, account_id: str, decision_id: str, risk_dollars: float,
            notional: float, account_equity: float, buying_power: float,
            sector: str | None, cfg: Settings) -> ReservationResult:
    existing_risk, existing_notional, existing_sector_notional = _active_totals(db, account_id, sector)

    aggregate_risk_cap = min(cfg.MAX_POSITIONS * cfg.MAX_RISK_PER_TRADE, cfg.MAX_DAILY_LOSS) * account_equity
    if existing_risk + risk_dollars > aggregate_risk_cap + 1e-9:
        return ReservationResult(approved=False, reason="aggregate_risk_limit_exceeded")

    if existing_notional + notional > buying_power + 1e-9:
        return ReservationResult(approved=False, reason="insufficient_buying_power_aggregate")

    if sector:
        sector_cap = cfg.MAX_SECTOR_CONCENTRATION * account_equity
        if existing_sector_notional + notional > sector_cap + 1e-9:
            return ReservationResult(approved=False, reason="sector_concentration_limit_aggregate")

    row = RiskReservation(account_id=account_id, decision_id=decision_id, risk_dollars=risk_dollars,
                           notional=notional, sector=sector, status="active")
    db.add(row)
    persist(db)
    db.refresh(row)
    return ReservationResult(approved=True, reservation_id=row.id)


def release(db: Session, reservation_id: str) -> None:
    row = db.get(RiskReservation, reservation_id)
    if row:
        row.status = "released"
        persist(db)
