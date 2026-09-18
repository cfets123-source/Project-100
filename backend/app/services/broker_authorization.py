"""Shared mutation policy. This is an application guard, not process isolation.

Real protective-order execution remains unavailable until a real adapter can
prove account binding, position ownership and durable order reconciliation.
"""
from app.brokers.paper_broker import PaperBrokerAdapter
from app.services.state_machine import PAPER, LIVE, SAFE


def mutation_allowed(state_manager, broker, *, defensive=False):
    state = state_manager.get_state()
    if defensive:
        # SAFE does not grant new broker permissions. Only the configured paper
        # environment can manage its simulated positions in this implementation.
        if state not in (PAPER, SAFE):
            return False, f"defensive_order_blocked_state_{state}"
        if state_manager.cfg.TRADING_MODE != "paper":
            return False, "defensive_execution_environment_not_supported"
        if not isinstance(broker, PaperBrokerAdapter):
            return False, "defensive_real_broker_not_supported"
        return True, ""
    if state == PAPER:
        return (True, "") if isinstance(broker, PaperBrokerAdapter) else (False, "paper_requires_paper_broker")
    if state == LIVE:
        return state_manager.live_broker_mutation_allowed()
    return False, f"broker_mutation_blocked_state_{state}"
