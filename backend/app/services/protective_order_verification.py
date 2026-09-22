"""Read-only verification that every external-paper position has a protective stop."""
def verify_protective_orders(adapter):
    positions = adapter.get_positions()
    orders = adapter.get_orders()
    active_statuses = {'new','pending_new','accepted','pending','open','partially_filled'}
    open_stops = {str(o.get('symbol')) for o in orders
                  if str(o.get('status')) in active_statuses
                  and str(o.get('type')) in {'stop','stop_limit','trailing_stop'}}
    pending_exits = {str(o.get('symbol')) for o in orders
                     if str(o.get('status')) in active_statuses and str(o.get('side')) == 'sell'
                     and str(o.get('type')) not in {'stop','stop_limit','trailing_stop'}}
    uncovered = [str(p.get('symbol')) for p in positions if float(p.get('qty') or 0) != 0 and str(p.get('symbol')) not in open_stops]
    return {'protected': not uncovered, 'uncovered_positions': uncovered,
            'open_protective_symbols': sorted(open_stops),
            'pending_exit_symbols': sorted(pending_exits)}
