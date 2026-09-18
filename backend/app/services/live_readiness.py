"""Conservative live-readiness report. This module never enables execution."""
def report(cfg, broker_report, market_open: bool, external_paper_lifecycle_verified: bool):
    blockers=[]
    if not broker_report.get('read_only_ready'): blockers.append('live broker read-only verification incomplete')
    if broker_report.get('paper', True): blockers.append('live broker credential is not connected')
    if not external_paper_lifecycle_verified: blockers.append('external paper lifecycle not verified')
    if cfg.LIVE_TRADING_ENABLED: blockers.append('live flag must remain off until final activation')
    return {'ready': not blockers, 'market_open': market_open, 'blockers': blockers,
            'live_execution_enabled': False}
