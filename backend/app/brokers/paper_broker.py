import time
import uuid
import datetime as dt
from app.brokers.base import BrokerAdapter, Quote, OrderRequest, OrderResult


class PaperBrokerAdapter(BrokerAdapter):
    """Simulated broker. Emulates orders/fills/slippage/spread/commissions/market hours.
    Must never touch real money or real broker endpoints."""

    def __init__(self, starting_cash: float, quote_source, commission_per_order: float = 0.0,
                 slippage_bps: float = 5.0):
        self.cash = starting_cash
        self.starting_cash = starting_cash
        self.positions: dict[str, dict] = {}   # symbol -> {qty, avg_price}
        self.orders: dict[str, dict] = {}
        self.quote_source = quote_source        # callable(symbols) -> list[Quote]
        self.commission_per_order = commission_per_order
        self.slippage_bps = slippage_bps

    def authenticate(self) -> bool:
        return True

    def get_accounts(self) -> list[dict]:
        return [{"account_id": "paper-1", "type": "paper"}]

    def get_balances(self) -> dict:
        equity = self.cash + sum(
            p["qty"] * self._last_price(sym) for sym, p in self.positions.items()
        )
        return {"cash": self.cash, "equity": equity}

    def get_buying_power(self) -> float:
        return self.cash

    def get_positions(self) -> list[dict]:
        return [{"symbol": s, **p} for s, p in self.positions.items()]

    def get_quotes(self, symbols: list[str]) -> list[Quote]:
        return self.quote_source(symbols)

    def get_orders(self) -> list[dict]:
        return list(self.orders.values())

    def _last_price(self, symbol: str) -> float:
        q = self.quote_source([symbol])[0]
        return q.last

    def _is_market_open(self) -> bool:
        now = dt.datetime.utcnow()
        # Simplified: Mon-Fri 13:30-20:00 UTC ~= 9:30-16:00 ET (no holiday calendar yet)
        if now.weekday() >= 5:
            return False
        minutes = now.hour * 60 + now.minute
        return 13 * 60 + 30 <= minutes <= 20 * 60

    def preview_order(self, order: OrderRequest) -> dict:
        q = self.quote_source([order.symbol])[0]
        px = q.ask if order.side == "buy" else q.bid
        est_cost = px * order.quantity + self.commission_per_order
        return {"symbol": order.symbol, "estimated_price": px, "estimated_cost": est_cost,
                "market_open": self._is_market_open()}

    def place_order(self, order: OrderRequest) -> OrderResult:
        order_id = str(uuid.uuid4())
        if not self._is_market_open():
            result = OrderResult(order_id=order_id, status="rejected", raw={"reason": "market_closed"})
            self.orders[order_id] = {"order": order, "result": result, "ts": time.time()}
            return result

        q = self.quote_source([order.symbol])[0]
        base_px = q.ask if order.side == "buy" else q.bid
        slip = base_px * (self.slippage_bps / 10_000.0)
        fill_price = base_px + slip if order.side == "buy" else base_px - slip

        cost = fill_price * order.quantity + self.commission_per_order
        if order.side == "buy":
            if cost > self.cash:
                result = OrderResult(order_id=order_id, status="rejected", raw={"reason": "insufficient_buying_power"})
                self.orders[order_id] = {"order": order, "result": result, "ts": time.time()}
                return result
            self.cash -= cost
            pos = self.positions.setdefault(order.symbol, {"qty": 0.0, "avg_price": 0.0})
            new_qty = pos["qty"] + order.quantity
            pos["avg_price"] = (pos["avg_price"] * pos["qty"] + fill_price * order.quantity) / new_qty
            pos["qty"] = new_qty
        else:
            pos = self.positions.get(order.symbol)
            if not pos or pos["qty"] < order.quantity:
                result = OrderResult(order_id=order_id, status="rejected", raw={"reason": "insufficient_position"})
                self.orders[order_id] = {"order": order, "result": result, "ts": time.time()}
                return result
            pos["qty"] -= order.quantity
            self.cash += fill_price * order.quantity - self.commission_per_order
            if pos["qty"] == 0:
                del self.positions[order.symbol]

        result = OrderResult(order_id=order_id, status="filled", filled_qty=order.quantity, fill_price=fill_price)
        self.orders[order_id] = {"order": order, "result": result, "ts": time.time()}
        return result

    def cancel_order(self, order_id: str) -> bool:
        entry = self.orders.get(order_id)
        if entry and entry["result"].status not in ("filled", "canceled"):
            entry["result"].status = "canceled"
            return True
        return False

    def get_order_status(self, order_id: str) -> dict:
        entry = self.orders.get(order_id)
        return entry["result"].__dict__ if entry else {}
