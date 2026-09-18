"""Metrics from closed, reconciled ledger rows; no projections or annualization."""
import math
import statistics
from app.models.models import TradeDecisionRecord, OrderIntent


def closed_trades(db, account_id):
    return db.query(TradeDecisionRecord).join(OrderIntent, OrderIntent.trade_id == TradeDecisionRecord.trade_id).filter(
        OrderIntent.account_id == account_id, TradeDecisionRecord.status == 'closed').order_by(
        TradeDecisionRecord.timestamp, TradeDecisionRecord.trade_id).all()


def summarize(trades):
    pnls, rs = [], []
    for trade in trades:
        if trade.pnl is None or trade.r_multiple is None or not math.isfinite(trade.pnl) or not math.isfinite(trade.r_multiple):
            raise ValueError('closed trade is missing finite realized P&L or R multiple')
        pnls.append(trade.pnl)
        rs.append(trade.r_multiple)
    n = len(pnls)
    gains = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    spread = statistics.stdev(rs) if n > 1 else 0
    return {'sample_size': n, 'wins': sum(p > 0 for p in pnls), 'losses': sum(p < 0 for p in pnls),
            'realized_pnl': sum(pnls), 'win_rate': sum(p > 0 for p in pnls)/n if n else None,
            'expectancy': statistics.mean(pnls) if n else None,
            'average_r': statistics.mean(rs) if n else None,
            'median_r': statistics.median(rs) if n else None,
            'profit_factor': gains/losses if losses else None,
            'trade_sharpe_like': statistics.mean(rs)/spread if spread > 0 else None,
            'metric_note': 'Unannualized closed-trade R mean / sample standard deviation; not portfolio Sharpe.'}


def account_performance(db, account_id='paper-1'):
    trades = closed_trades(db, account_id)
    strategies = {}
    for trade in trades:
        strategies.setdefault(trade.strategy, []).append(trade)
    return {'account_id': account_id, 'mode': 'paper', 'simulated': True,
            'overall': summarize(trades), 'strategies': {name: summarize(rows) for name, rows in strategies.items()}}
