"""Frozen cross-market historical screen. Pure functions; no broker or DB access."""
from __future__ import annotations
from dataclasses import dataclass
from math import floor,isfinite
from app.research.monthly_etf_time_series_momentum_v4 import settlement_sessions

CANDIDATES = {
 'broad_equity_trend': ('SPY',),
 'cross_asset_rotation': ('SPY','QQQ','IWM','EFA','EEM','TLT','IEF','GLD','DBC'),
 'direct_stock_rotation': ('AAPL','MSFT','JPM','XOM','JNJ'),
 'crypto_rotation': ('BTC','ETH'),
}

@dataclass
class ScreenResult:
    equity: list[dict]
    trades: list[dict]
    cash_days: int
    skipped_entries: int


def select_symbol(signal, dates, index, symbols, lookback, broad=False):
    if index < max(199,lookback):
        return None
    ranked=[]
    for symbol in symbols:
        close=signal[symbol][dates[index]]['close']
        average=sum(signal[symbol][d]['close'] for d in dates[index-199:index+1])/200
        momentum=close/signal[symbol][dates[index-lookback]]['close']-1
        if close>average and (broad or momentum>0):
            ranked.append((momentum,symbol))
    return sorted(ranked,key=lambda x:(-x[0],x[1]))[0][1] if ranked else None


def evaluate(raw,signal,*,dates,start,end,candidate,one_way_cost,splits=None,benchmark=False):
    if candidate not in CANDIDATES or not isfinite(one_way_cost) or not 0<=one_way_cost<.05:
        raise ValueError('invalid candidate or cost')
    if start>=end or sum(d<start for d in dates)<200:
        raise ValueError('invalid window or insufficient warmup')
    symbols=CANDIDATES[candidate]; crypto=candidate=='crypto_rotation'
    if benchmark: symbols=('BTC',) if crypto else ('SPY',)
    for source in (raw,signal):
        for s in symbols:
            if any(d not in source[s] for d in dates):raise ValueError('missing market session')
    cash=100.;position=None;pending=None;purchase_index=None
    equity=[];trades=[];cash_days=skipped=0
    splits=splits or {}
    for i,day in enumerate(dates):
        if day<start:continue
        if day>=end:break
        if position:
            position['qty']*=splits.get((position['symbol'],day),1.)
        if benchmark and not equity:
            pending=symbols[0];purchase_index=i
        elif not benchmark and i and dates[i-1][:7]!=day[:7]:
            # Signal from completed prior session; never from today's price.
            if equity:
                pending=select_symbol(signal,dates,i-1,symbols,180 if crypto else 126,
                                      broad=candidate=='broad_equity_trend')
                purchase_index=i+(0 if crypto else settlement_sessions(day))
                if position:
                    symbol=position['symbol'];price=raw[symbol][day]['open']
                    proceeds=position['qty']*price*(1-one_way_cost)
                    cash+=proceeds
                    trades.append({**position,'exit_day':day,'exit_price':price,
                                   'net_proceeds':proceeds,'pnl':proceeds-position['entry_cost']})
                    position=None
        if i==purchase_index and pending and position is None:
            opening=raw[pending][day]['open'];budget=.95*cash
            precision=1e8 if crypto else 1e9
            qty=floor(budget/(opening*(1+one_way_cost))*precision)/precision
            # Minimum notional is a research approximation. Historical asset
            # increments and fractional availability are not fully reconstructed.
            if qty*opening>=1:
                cost=qty*opening*(1+one_way_cost);cash-=cost
                position={'symbol':pending,'qty':qty,'entry_day':day,'entry_price':opening,'entry_cost':cost}
            else:skipped+=1
            pending=None
        marked=cash;liquidation=cash
        if position:
            value=position['qty']*raw[position['symbol']][day]['close']
            marked+=value;liquidation+=value*(1-one_way_cost)
        else:cash_days+=1
        assert cash>=-1e-8 and isfinite(marked) and marked>=0
        equity.append({'day':day,'marked':marked,'liquidation':liquidation,
                       'cash':cash,'symbol':position['symbol'] if position else None})
    return ScreenResult(equity,trades,cash_days,skipped)
