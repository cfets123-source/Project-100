from app.core.config import Settings
from app.services.live_readiness import report

def test_live_readiness_fails_closed_until_all_proofs_exist():
 r=report(Settings(), {'read_only_ready':True,'paper':True}, True, True)
 assert not r['ready'] and 'live broker credential' in r['blockers'][0]
