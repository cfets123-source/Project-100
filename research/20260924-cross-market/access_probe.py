import json
from datetime import datetime,timezone
from sqlalchemy.orm import Session
from app.db.session import engine
from app.core.config import Settings
from app.models.models import BrokerConnection
from app.brokers.alpaca_connection import load_read_only_adapter
cfg=Settings()
result={'observed_at':datetime.now(timezone.utc).isoformat()}
with Session(engine) as db:
    result['stored_broker_types']=[r.broker for r in db.query(BrokerConnection).all()]
    adapter,paper=load_read_only_adapter(db,cfg.BROKER_TOKEN_ENCRYPTION_KEY,paper=False)
    assert not paper and not adapter.allow_order_submission
    result['live_capabilities']=adapter.get_account_capabilities()
    result['balances']=adapter.get_balances()
    result['assets']={}
    for symbol in ('SPY','QQQ','IWM','EFA','EEM','TLT','IEF','GLD','DBC','AAPL','MSFT','JPM','XOM','JNJ','BTC/USD','ETH/USD'):
        asset=adapter._request('GET','/v2/assets/'+symbol)
        result['assets'][symbol]={k:asset.get(k) for k in ('symbol','class','tradable','fractionable','status','min_order_size','min_trade_increment')}
    # OPRA is read-only; distinguish unavailable entitlement from missing quotes.
    try:
        chain=adapter._request('GET','/v1beta1/options/snapshots/SPY',data_api=True,params={'feed':'opra','limit':1})
        result['opra_probe']={'accessible':True,'snapshots':len(chain.get('snapshots',{}))}
    except Exception as exc:
        result['opra_probe']={'accessible':False,'error_type':type(exc).__name__,'message':str(exc)[:200]}
print(json.dumps(result))
