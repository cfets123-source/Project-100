"""
Persisted OFF/RESEARCH/PAPER/SHADOW/LIVE/SAFE/HALTED state machine.

THREAT MODEL: this enforces transitions and gates broker-mutation eligibility for
any code that goes through StateManager / ExecutionGateway. It cannot stop a
future developer from writing a new code path that ignores this class entirely —
that is a code-review/architecture-boundary responsibility (see
docs/THREAT_MODEL.md), not a runtime guarantee this module can make on its own.
"""
import datetime as dt
from sqlalchemy.orm import Session
from app.models.models import SystemStateRecord
from app.audit.logger import log_and_commit
from app.core.config import settings

OFF, RESEARCH, PAPER, SHADOW, LIVE, SAFE, HALTED = (
    "off", "research", "paper", "shadow", "live", "safe", "halted",
)

# Routine, reversible transitions. HALTED is deliberately unreachable here —
# the ONLY way out of HALTED is reset(), which requires an explicit human actor.
ALLOWED_TRANSITIONS = {
    OFF: {RESEARCH, PAPER, SHADOW},
    RESEARCH: {OFF, PAPER, SHADOW},
    PAPER: {OFF, RESEARCH, SHADOW},
    SHADOW: {OFF, RESEARCH, PAPER, LIVE},   # promotion to LIVE still gated by settings.LIVE_TRADING_ENABLED
    LIVE: {SHADOW, PAPER},                    # normal step-down; SAFE/HALTED handled via emergency paths below
    SAFE: {OFF, RESEARCH, PAPER, SHADOW},     # resume-from-SAFE is allowed for routine causes (see resume_from_safe)
    HALTED: set(),                             # no ordinary transition escapes HALTED
}


class InvalidTransitionError(Exception):
    pass


class StateManager:
    def __init__(self, db: Session, cfg=settings):
        self.db = db
        self.cfg = cfg

    def get_record(self) -> SystemStateRecord:
        rec = self.db.get(SystemStateRecord, "current")
        if rec is None:
            rec = SystemStateRecord(id="current", state=OFF, reason="initial")
            self.db.add(rec)
            self.db.commit()
            self.db.refresh(rec)
        return rec

    def get_state(self) -> str:
        return self.get_record().state

    def transition(self, new_state: str, reason: str, actor: str = "system") -> SystemStateRecord:
        rec = self.get_record()
        current = rec.state
        if new_state not in ALLOWED_TRANSITIONS.get(current, set()):
            raise InvalidTransitionError(f"{current} -> {new_state} is not permitted")
        rec.state = new_state
        rec.reason = reason
        rec.updated_at = dt.datetime.utcnow()
        self.db.commit()
        log_and_commit(self.db, "state_change", {"from": current, "to": new_state, "reason": reason}, actor=actor)
        return rec

    # --- Kill switch: emergency, reachable from ANY state, bypasses ALLOWED_TRANSITIONS ---
    def activate_kill_switch(self, reason: str, actor: str = "system") -> SystemStateRecord:
        rec = self.get_record()
        previous = rec.state
        rec.state = HALTED
        rec.reason = f"KILL_SWITCH: {reason} (was {previous})"
        rec.updated_at = dt.datetime.utcnow()
        self.db.commit()
        log_and_commit(self.db, "kill_switch_activated", {"previous_state": previous, "reason": reason}, actor=actor)
        return rec

    def reset(self, actor: str, confirm: bool) -> SystemStateRecord:
        """Explicit human reset out of HALTED. confirm=True must be supplied by the
        caller (API layer) only after an explicit user action — never automatic."""
        rec = self.get_record()
        if rec.state != HALTED:
            raise InvalidTransitionError("reset() is only valid from HALTED")
        if not confirm or actor == "system":
            raise InvalidTransitionError("reset requires explicit human confirmation")
        rec.state = OFF
        rec.reason = f"manual_reset_by_{actor}"
        rec.updated_at = dt.datetime.utcnow()
        self.db.commit()
        log_and_commit(self.db, "kill_switch_reset", {"actor": actor}, actor=actor)
        return rec

    def enter_safe_mode(self, reason: str, actor: str = "system") -> SystemStateRecord:
        rec = self.get_record()
        previous = rec.state
        if previous == HALTED:
            log_and_commit(self.db, "safe_mode_ignored_while_halted", {"reason": reason}, actor=actor)
            return rec
        rec.state = SAFE
        rec.reason = reason
        rec.updated_at = dt.datetime.utcnow()
        self.db.commit()
        log_and_commit(self.db, "entered_safe_mode", {"previous_state": previous, "reason": reason}, actor=actor)
        return rec

    def resume_from_safe(self, new_state: str, reason: str, actor: str = "system") -> SystemStateRecord:
        """Routine, recoverable causes only (spec: 'serious safety shutdowns must
        NOT auto-resume' — those go to HALTED via activate_kill_switch, not SAFE)."""
        rec = self.get_record()
        if rec.state != SAFE:
            raise InvalidTransitionError("resume_from_safe is only valid from SAFE")
        return self.transition(new_state, reason, actor)

    # --- Broker-mutation eligibility gates, checked by ExecutionGateway ---
    def can_open_new_entries(self) -> tuple[bool, str]:
        state = self.get_state()
        if state not in (PAPER, SHADOW, LIVE):
            return False, f"new_entries_blocked_state_{state}"
        return True, ""

    def is_shadow(self) -> bool:
        return self.get_state() == SHADOW

    def is_paper(self) -> bool:
        return self.get_state() == PAPER

    def live_broker_mutation_allowed(self) -> tuple[bool, str]:
        """Hard-disable independent of AUTONOMY_LEVEL/state, per explicit instruction
        to keep live execution disabled throughout this development task."""
        if not self.cfg.LIVE_TRADING_ENABLED:
            return False, "live_trading_hard_disabled_in_config"
        if self.get_state() != LIVE:
            return False, "state_is_not_live"
        return True, ""
