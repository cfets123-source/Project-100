"""Authenticate inside the server process; print only bounded verification facts."""
import json
import httpx
from app.core.config import Settings
cfg=Settings()
with httpx.Client(base_url='http://127.0.0.1:8000',auth=(cfg.DASHBOARD_USERNAME,cfg.DASHBOARD_PASSWORD),timeout=25) as client:
    health=client.get('/health');health.raise_for_status()
    dashboard=client.get('/dashboard');dashboard.raise_for_status()
    milestones=client.get('/live/milestones');milestones.raise_for_status()
    observer=client.get('/live/observer');observer.raise_for_status()
    state=client.get('/system/state');state.raise_for_status()
    body=milestones.json();obs=observer.json()
    output={'health_http_status':health.status_code,'dashboard_http_status':dashboard.status_code,
            'stage_dashboard_verified':'Stage-by-stage trading' in dashboard.text and 'Sell &amp; reconcile' in dashboard.text,
            'observer':obs,'milestones':{k:body.get(k) for k in ('broker_verified','phase','next_target','equity','performance_equity')},
            'state':state.json(),'api_live_flag':cfg.LIVE_TRADING_ENABLED,
            'api_position_management_flag':cfg.LIVE_POSITION_MANAGEMENT_ENABLED}
    print(json.dumps(output))
    assert output['stage_dashboard_verified']
    assert not cfg.LIVE_TRADING_ENABLED and not cfg.LIVE_POSITION_MANAGEMENT_ENABLED
    assert obs.get('healthy') and obs.get('read_only') and obs.get('order_execution_enabled') is False
    assert body.get('broker_verified')
