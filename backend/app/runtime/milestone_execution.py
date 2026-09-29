"""Execute a lifecycle liquidation with the restricted exposure adapter.

No entry strategy is selected here. Every cycle reconciles broker facts again.
Outstanding buys and uncertain cancels prevent a sell of a guessed quantity.
"""
from app.brokers.base import OrderRequest
from app.brokers.reduce_only import ReduceOnlyAdapter, TERMINAL


def liquidate_for_milestone(adapter: ReduceOnlyAdapter):
    if not isinstance(adapter, ReduceOnlyAdapter):
        raise RuntimeError('milestone liquidation requires restricted position adapter')
    orders = adapter.get_orders()
    active = [o for o in orders if o.get('status') not in TERMINAL]
    if any(o.get('side') != 'sell' for o in active):
        return {'submitted': [], 'reason': 'outstanding_entry_requires_reconciliation'}
    # If a non-stop exit is already working, let it reconcile instead of
    # canceling and replacing it on each poll.
    if any(o.get('type') not in {'stop','stop_limit','trailing_stop'} for o in active):
        return {'submitted': [], 'reason': 'exit_pending'}
    for order in active:
        adapter.cancel_order(str(order['id']))
        confirmed = adapter.get_order_status(str(order['id']))
        if confirmed.get('status') not in TERMINAL:
            return {'submitted': [], 'reason': 'stop_cancel_unconfirmed'}
    submitted=[]
    for position in adapter.get_positions():
        qty=float(position.get('qty') or 0)
        if qty <= 0: continue
        result=adapter.place_order(OrderRequest(symbol=str(position['symbol']),side='sell',quantity=qty))
        submitted.append({'symbol':position['symbol'],'order_id':result.order_id,'status':result.status})
    return {'submitted':submitted,'reason':'liquidation_submitted' if submitted else 'flat_reconcile_next_cycle'}
