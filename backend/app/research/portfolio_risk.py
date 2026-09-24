"""Fixed portfolio-level risk overlay for research candidates."""
from __future__ import annotations

MAX_DRAWDOWN = .10
TARGET_VOLATILITY = .08

def volatility_targeted_returns(returns: list[float], window: int = 6) -> list[float]:
    """Scale monthly exposure from trailing realized volatility; halt at 10% DD.

    The scale is capped at one: this overlay never adds leverage.
    """
    equity = peak = 1.0
    output=[]
    for i, value in enumerate(returns):
        trailing=returns[max(0,i-window):i]
        if len(trailing) >= 2:
            mean=sum(trailing)/len(trailing)
            vol=(sum((x-mean)**2 for x in trailing)/(len(trailing)-1))**.5 * (12**.5)
            scale=min(1.0, TARGET_VOLATILITY / vol) if vol else 1.0
        else: scale=1.0
        applied=value*scale if equity >= peak*(1-MAX_DRAWDOWN) else 0.0
        equity*=1+applied; peak=max(peak,equity); output.append(applied)
    return output
