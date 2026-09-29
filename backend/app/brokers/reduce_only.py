"""Narrow position-management adapter; cannot submit entries or short a position.

Requires the same single-account process lock as the entry worker. An uncertain
POST stays unresolved even if the broker's next list response omits the order.
"""
from dataclasses import replace
import math
import uuid

from app.models.models import (DefensiveOrderIntent, TradeDecisionRecord,
                               ExternalLiveProtection, ExternalPaperProtection)

TERMINAL = {'filled', 'canceled', 'expired', 'rejected'}
READ_METHODS = {'get_accounts', 'get_balances', 'get_buying_power', 'get_positions',
                'get_orders', 'get_order_status', 'get_quotes', 'get_market_clock',
                'get_order_by_client_id'}


def reconcile_defensive_intents(db, broker, account_id):
    unresolved=[]
    for row in db.query(DefensiveOrderIntent).filter_by(account_id=account_id).all():
        if row.status in TERMINAL: continue
        try:
            order = (broker.get_order_status(row.broker_order_id) if row.broker_order_id
                     else broker.get_order_by_client_id(row.client_order_id))
            if (order.get('client_order_id') != row.client_order_id or order.get('symbol') != row.symbol
                    or order.get('side') != 'sell' or not order.get('id')):
                raise RuntimeError('defensive reconciliation identity mismatch')
            row.status = str(order.get('status'))
            row.broker_order_id = str(order['id'])
            row.filled_quantity = float(order.get('filled_qty') or 0)
            row.fill_price = float(order['filled_avg_price']) if order.get('filled_avg_price') else None
            db.commit()
        except Exception:
            unresolved.append(row.client_order_id)
    # Reconcile P&L only after every linked closing order is terminal and broker
    # flatness plus the exact original entry prove that all shares were sold.
    positions = {p.get('symbol') for p in broker.get_positions() if float(p.get('qty') or 0) != 0}
    rows = db.query(DefensiveOrderIntent).filter_by(account_id=account_id).all()
    for entry_id in {r.entry_order_id for r in rows if r.entry_order_id}:
        exits = [r for r in rows if r.entry_order_id == entry_id]
        if any(r.status not in TERMINAL or r.symbol in positions for r in exits): continue
        fills = [r for r in exits if r.filled_quantity > 0]
        if not fills or any(not r.fill_price for r in fills): continue
        entry = broker.get_order_status(entry_id)
        if entry.get('status') != 'filled' or entry.get('side') != 'buy': continue
        quantity = sum(r.filled_quantity for r in fills)
        if abs(quantity - float(entry.get('filled_qty') or 0)) > 1e-8: continue
        from app.runtime.alpaca_live_position_manager import _finish_trade
        synthetic_aggregate = {'id': ','.join(r.broker_order_id for r in fills),
                               'filled_qty': quantity,
                               'filled_avg_price': sum(r.fill_price*r.filled_quantity for r in fills)/quantity}
        _finish_trade(db, entry_id, synthetic_aggregate, 'supervised_exit', 'paper' if broker.paper else 'live')
    return unresolved


class ReduceOnlyAdapter:
    def __init__(self, db, broker, account_id):
        self.db, self._broker, self.account_id = db, broker, account_id
        self.paper = broker.paper
        self._verify_account()

    def _verify_account(self):
        accounts = self._broker.get_accounts()
        if len(accounts) != 1 or str(accounts[0].get('account_id')) != self.account_id:
            raise RuntimeError('position supervisor account mismatch')

    def __getattr__(self, name):
        if name in READ_METHODS:
            return getattr(self._broker, name)
        raise AttributeError(name)

    def _reconcile_pending(self, symbol):
        reconcile_defensive_intents(self.db, self._broker, self.account_id)
        rows = self.db.query(DefensiveOrderIntent).filter_by(
            account_id=self.account_id, symbol=symbol).all()
        if any(row.status not in TERMINAL for row in rows):
            raise RuntimeError('unresolved defensive submission; no retry')

    def place_order(self, order):
        self._verify_account()
        if (order.side != 'sell' or not math.isfinite(order.quantity) or order.quantity <= 0
                or order.order_class is not None):
            raise RuntimeError('position supervisor only permits simple positive-quantity sells')
        self._reconcile_pending(order.symbol)
        positions = [p for p in self._broker.get_positions() if p.get('symbol') == order.symbol]
        if len(positions) != 1:
            raise RuntimeError('position supervisor requires one existing long position')
        quantity = float(positions[0].get('qty') or 0)
        if not math.isfinite(quantity) or quantity <= 0 or order.quantity > quantity:
            raise RuntimeError('defensive order would exceed existing exposure')
        # Unknown statuses fail closed. A cancel acknowledgment is not flatness.
        for existing in self._broker.get_orders():
            if (existing.get('symbol') == order.symbol and existing.get('side') == 'sell'
                    and existing.get('status') not in TERMINAL):
                raise RuntimeError('existing or uncertain sell; no duplicate defensive order')
        client_id = 'def-' + uuid.uuid4().hex
        protection = ExternalPaperProtection if self.paper else ExternalLiveProtection
        linked = (self.db.query(TradeDecisionRecord)
                  .join(protection, protection.entry_order_id == TradeDecisionRecord.order_id)
                  .filter(TradeDecisionRecord.symbol == order.symbol,
                          TradeDecisionRecord.status == 'open').all())
        if len(linked) > 1:
            raise RuntimeError('ambiguous entry ownership for supervised exit')
        row = DefensiveOrderIntent(client_order_id=client_id, account_id=self.account_id,
                                   symbol=order.symbol, quantity=order.quantity, status='unknown',
                                   entry_order_id=linked[0].order_id if linked else None)
        self.db.add(row)
        self.db.commit()  # survive a crash after broker acceptance but before response
        result = self._broker.place_order(replace(order, client_order_id=client_id))
        row.broker_order_id = result.order_id or None
        row.status = result.status if result.order_id else 'unknown'
        row.filled_quantity = result.filled_qty
        row.fill_price = result.fill_price
        self.db.commit()
        return result

    def cancel_order(self, order_id):
        self._verify_account()
        order = self._broker.get_order_status(order_id)
        if str(order.get('id')) != str(order_id) or order.get('side') != 'sell':
            raise RuntimeError('position supervisor can cancel only identified sell orders')
        return self._broker.cancel_order(order_id)
