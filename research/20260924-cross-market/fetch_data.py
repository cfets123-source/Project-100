"""Historical GET requests only; no order or account mutations."""
import json,time
from datetime import datetime,timedelta,timezone
import httpx
from sqlalchemy.orm import Session
from app.db.session import engine
from app.brokers.alpaca_connection import load_read_only_adapter
from app.core.config import Settings
SYMBOLS=('SPY','QQQ','IWM','EFA','EEM','TLT','IEF','GLD','DBC','AAPL','MSFT','JPM','XOM','JNJ')
cfg=Settings();p={'securities':{},'crypto':{},'sources':{'equities':'Alpaca SIP','crypto':'Coinbase Exchange'}}
with Session(engine) as db:
    a,paper=load_read_only_adapter(db,cfg.BROKER_TOKEN_ENCRYPTION_KEY,paper=True)
    assert paper and not a.allow_order_submission
    for adjustment in ('raw','split'):
        data={s:[] for s in SYMBOLS}
        params={'symbols':','.join(SYMBOLS),'timeframe':'1Day','start':'2016-01-01','end':'2026-09-23','adjustment':adjustment,'feed':'sip','limit':10000}
        for page in a._stock_bar_pages('/v2/stocks/bars',params):
            for s,rows in page.get('bars',{}).items():
                if s in data:data[s].extend(dict(timestamp=r['t'],open=r['o'],high=r['h'],low=r['l'],close=r['c'],volume=r['v']) for r in rows if r['t'][:10]<'2026-09-23')
        p['securities'][adjustment]=data
    p['calendar']=a._request('GET','/v2/calendar',params={'start':'2016-01-01','end':'2026-09-22'})
with httpx.Client(timeout=30) as client:
    for coin in ('BTC','ETH'):
        rows={};cursor=datetime(2017,1,1,tzinfo=timezone.utc);end=datetime(2026,9,23,tzinfo=timezone.utc)
        while cursor<end:
            stop=min(cursor+timedelta(days=290),end)
            response=client.get(f'https://api.exchange.coinbase.com/products/{coin}-USD/candles',params={'granularity':86400,'start':cursor.isoformat(),'end':stop.isoformat()})
            response.raise_for_status()
            for stamp,low,high,opening,close,volume in response.json():
                day=datetime.fromtimestamp(stamp,timezone.utc).date().isoformat()
                if '2017-01-01'<=day<'2026-09-23':rows[day]=dict(timestamp=day,open=opening,high=high,low=low,close=close,volume=volume)
            cursor=stop;time.sleep(.12)
        p['crypto'][coin]=[rows[d] for d in sorted(rows)]
print(json.dumps(p))
