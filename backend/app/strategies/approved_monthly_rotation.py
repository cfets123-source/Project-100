"""Paper-only adapter for the approved monthly strategy version."""
from app.research.defensive_rotation import STRATEGY_VERSION

class ApprovedMonthlyRotation:
    name=STRATEGY_VERSION+'-vol-targeted'
    def signal(self, adapter, symbol: str):
        from datetime import datetime, timezone
        today=datetime.now(timezone.utc)
        import os
        if today.day > 5 and os.getenv('PAPER_BOOTSTRAP_DECISION') != 'true': return None
        bars=adapter.get_daily_bars(symbol, '2025-01-01T00:00:00Z', today.strftime('%Y-%m-%dT00:00:00Z'))
        if len(bars)<201: return None
        close=float(bars[-1]['close']); trend=sum(float(x['close']) for x in bars[-200:])/200
        momentum=close/float(bars[-127]['close'])-1
        if close <= trend or momentum <= 0: return None
        suffix=os.getenv('PAPER_BOOTSTRAP_RUN_ID','')
        if suffix:
            import time
            suffix=f'{suffix}:{time.time_ns()}'
        return {'symbol':symbol,'direction':'long','strategy':self.name,'decision_id':f'{self.name}:{today:%Y-%m}:{symbol}:{suffix}','entry_price':close,'stop_price':round(close*.92,2),'target_price':round(close*1.16,2),'thesis':'monthly trend-qualified paper rotation','ai_confidence':None,'score':momentum}

    def portfolio_signal(self, adapter, symbols):
        """Return one best qualified signal or cash; fixed tie break by symbol."""
        candidates=[self.signal(adapter,s) for s in sorted(symbols)]
        candidates=[x for x in candidates if x]
        if not candidates: return None
        best=max(candidates,key=lambda x:(x['score'],x['symbol']))
        best.pop('score',None)
        return best
