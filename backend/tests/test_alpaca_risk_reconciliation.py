from datetime import datetime,timedelta,timezone
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import pytest
from app.db.session import Base
from app.services.alpaca_risk_reconciliation import collect_risk_observation, NY
from app.services.account_risk import RiskEvidenceUnavailable

def test_broker_cash_transfer_does_not_erase_drawdown():
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    now=datetime.now(timezone.utc);today=now.astimezone(NY).date()
    yesterday=now-timedelta(days=1)
    account={'id':'acct','created_at':(now-timedelta(days=10)).isoformat(),
             'equity':'140','cash':'140','last_equity':'100'}
    history={'timestamp':[int(yesterday.timestamp())],'equity':[100]}
    activities=[{'id':'original','activity_type':'CSD','date':str(today-timedelta(days=9)),'net_amount':'100'},
                {'id':'new','activity_type':'CSD','date':str(today),'net_amount':'50'}]
    adapter=MagicMock()
    def response(method,path,**kwargs):
        assert method=='GET'
        return history if path.endswith('/history') else activities if path.endswith('/activities') else account
    adapter._request.side_effect=response
    with Session(engine) as db:
        result=collect_risk_observation(db,adapter,'alpaca:live',now=now)
    assert result['adjusted_day_open']==150
    assert result['adjusted_all_time_peak']==150
    assert result['equity']==140
    assert result['net_external_flows']==150

def test_ambiguous_journal_cannot_be_counted_as_profit():
    now=datetime.now(timezone.utc)
    adapter=MagicMock()
    adapter._request.side_effect=[{'id':'acct','created_at':now.isoformat()},
                                  {'timestamp':[],'equity':[]},
                                  [{'id':'journal','activity_type':'JNLS'}]]
    with pytest.raises(RiskEvidenceUnavailable,match='explicit reconciliation'):
        collect_risk_observation(object(),adapter,'alpaca:live',now=now)
