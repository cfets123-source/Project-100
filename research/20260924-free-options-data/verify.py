import json
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.db.session import engine
from app.core.config import Settings
from app.brokers.robinhood_adapter import load_agentic_read_only_adapter
from app.brokers.etrade_connection import status
cfg=Settings()
out={'observed_at':datetime.now(timezone.utc).isoformat(),'execution_enabled':False}
with Session(engine) as db:
    out['etrade']=status(db)
    try:
        adapter,account=load_agentic_read_only_adapter(db,cfg.BROKER_TOKEN_ENCRYPTION_KEY)
        out['robinhood_options_level']=account.get('user_option_level') or account.get('option_level')
        # One near-market contract for market-data diagnostics only, not a trade selection.
        equity=adapter.get_quotes(['SPY'])[0]
        strike=str(round(equity.last/5)*5)
        chains=adapter.get_option_chains('SPY')
        lower=(datetime.now(timezone.utc)+timedelta(days=7)).date().isoformat()
        choices=sorted((d,c['id']) for c in chains for d in c.get('expiration_dates',[]) if d>=lower)
        expiration,chain_id=choices[0]
        instruments=adapter.get_option_instruments(chain_id,expiration,strike,'call')
        chosen=[x for x in instruments if x.get('state')=='active'][:1]
        quotes=adapter.get_option_quotes(chosen)
        out['robinhood_quotes']=[{k:v for k,v in q.items() if k!='instrument_id'} for q in quotes]
    except Exception as exc:
        out['robinhood_error_type']=type(exc).__name__
print(json.dumps(out))
