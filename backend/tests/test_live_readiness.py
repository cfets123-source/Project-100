from app.core.config import Settings
from app.services.live_readiness import report

def test_live_readiness_fails_closed_until_all_proofs_exist():
 r=report(Settings(), {'read_only_ready':True,'paper':True}, True, True)
 assert not r['ready'] and 'live broker credential' in r['blockers'][0]

def test_live_readiness_rejects_halted_state_even_with_old_paper_proof():
 r=report(Settings(), {'read_only_ready':True,'paper':False}, True, True,
          current_state='halted')
 assert r['ready'] is False
 assert r['current_state'] == 'halted'
 assert any('kill switch' in blocker for blocker in r['blockers'])
