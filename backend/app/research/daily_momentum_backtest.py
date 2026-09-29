"""No-lookahead evaluator for daily-liquid-momentum-v1."""
from app.strategies.daily_momentum import DailyLiquidMomentum

def returns(bars, symbol):
    out=[]; strategy=DailyLiquidMomentum(); open_trade=None
    for i in range(21,len(bars)-1):
        if open_trade:
            entry,stop,target=open_trade
            row=bars[i]
            if float(row['low'])<=stop: out.append(stop/entry-1-.001); open_trade=None
            elif float(row['high'])>=target: out.append(target/entry-1-.001); open_trade=None
            continue
        signal=strategy.signal(symbol,bars[:i+1])
        if signal:
            entry=float(bars[i+1]['open']); open_trade=(entry,entry*.96,entry*1.08)
    return out
