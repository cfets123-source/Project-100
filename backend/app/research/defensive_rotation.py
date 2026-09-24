"""Fixed monthly equity/defensive rotation, research only."""
from app.research.monthly_etf_rotation import MOMENTUM_DAYS, TREND_DAYS, ROUND_TRIP_COST
STRATEGY_VERSION="defensive-etf-rotation-v1"; RISK_ON=("SPY","QQQ","IWM"); DEFENSIVE=("GLD","TLT")
def monthly_returns(data, split):
 ref=data["SPY"]; dates=[x["timestamp"] for x in ref]; ends=[i for i in range(1,len(ref)-1) if dates[i][:7]!=dates[i+1][:7] and i>=TREND_DAYS]; out=[]
 for a,b in zip(ends,ends[1:]):
  if dates[a]<split: continue
  pool=RISK_ON if any(float(data[s][a]['close'])>sum(float(x['close']) for x in data[s][a-TREND_DAYS+1:a+1])/TREND_DAYS for s in RISK_ON) else DEFENSIVE
  c=[]
  for s in pool:
   z=data[s]; close=float(z[a]['close']); trend=sum(float(x['close']) for x in z[a-TREND_DAYS+1:a+1])/TREND_DAYS
   if close>trend: c.append((close/float(z[a-MOMENTUM_DAYS]['close'])-1,-pool.index(s),s))
  if c:
   s=max(c)[2]; z=data[s]; out.append(float(z[b+1]['open'])/float(z[a+1]['open'])-1-ROUND_TRIP_COST)
 return out
