"""Market-data GETs only, using the existing non-submitting paper adapter."""
import json,hashlib
from sqlalchemy.orm import Session
from app.db.session import engine
from app.brokers.alpaca_connection import load_read_only_adapter
from app.core.config import Settings
from app.research.weekly_global_etf_rotation_v1 import UNIVERSE
cfg=Settings()
with Session(engine) as db:
    adapter,paper=load_read_only_adapter(db,cfg.BROKER_TOKEN_ENCRYPTION_KEY,paper=True)
    assert paper and not adapter.allow_order_submission
    payload={'feed':'sip','start':'2016-01-01','end':'2026-09-23','data':{}}
    for adjustment in ('raw','split'):
        data={s:[] for s in UNIVERSE}
        params={'symbols':','.join(UNIVERSE),'timeframe':'1Day','start':'2016-01-01',
                'end':'2026-09-23','adjustment':adjustment,'feed':'sip','limit':10000}
        for page in adapter._stock_bar_pages('/v2/stocks/bars',params):
            for symbol,rows in page.get('bars',{}).items():
                if symbol in data:
                    data[symbol].extend({'timestamp':r['t'],'open':r['o'],'high':r['h'],
                         'low':r['l'],'close':r['c'],'volume':r['v']} for r in rows)
        payload['data'][adjustment]=data
    payload['calendar']=adapter._request('GET','/v2/calendar',params={'start':'2016-01-01','end':'2026-09-22'})
    print(json.dumps(payload))
