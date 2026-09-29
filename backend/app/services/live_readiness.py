"""Read-only readiness evidence, explicitly separate from runtime observation."""
def report(cfg, broker_report, market_open: bool, external_paper_lifecycle_verified: bool,
           current_state: str | None = None):
    blockers=[]
    if current_state == 'halted': blockers.append('kill switch is active; reconcile positions and orders before manual reset')
    if not broker_report.get('read_only_ready'): blockers.append('live broker read-only verification incomplete')
    if broker_report.get('paper', True): blockers.append('live broker credential is not connected')
    if not external_paper_lifecycle_verified: blockers.append('external paper lifecycle not verified')
    # The API process's flag is not proof about a separate execution worker.
    return {'ready': not blockers, 'phase': 'blocked' if blockers else 'connection_checks_passed',
            'market_open': market_open, 'blockers': blockers, 'current_state': current_state,
            'local_process_live_flag': bool(cfg.LIVE_TRADING_ENABLED),
            'live_execution_enabled': None, 'worker_runtime_verified': False,
            'scope': 'connection_and_recorded_lifecycle_only',
            'remaining_release_checks': ['exact_strategy_execution_evidence',
                                         'fresh_account_risk_reconciliation',
                                         'deployed_worker_and_operator_activation']}
