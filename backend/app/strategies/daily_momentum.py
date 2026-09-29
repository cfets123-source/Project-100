"""Daily active strategy candidate; research and paper only until validated."""
from __future__ import annotations
import uuid

STRATEGY_VERSION="daily-liquid-momentum-v1"
UNIVERSE=("SOFI","F","PLTR","TQQQ","SQQQ")

class DailyLiquidMomentum:
    name=STRATEGY_VERSION
    def signal(self, symbol, bars):
        if len(bars)<21: return None
        close=float(bars[-1]['close']); high=max(float(x['high']) for x in bars[-21:-1])
        volume=float(bars[-1]['volume']); avg=sum(float(x['volume']) for x in bars[-21:-1])/20
        if close<=high or volume<avg*1.5: return None
        return {'symbol':symbol,'direction':'long','strategy':self.name,'decision_id':str(uuid.uuid4()),'entry_price':close,'stop_price':round(close*.96,2),'target_price':round(close*1.08,2),'thesis':'daily liquid breakout with volume confirmation','ai_confidence':None}
