"""Binance.US account connection and market data. No order/transfer methods."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx
from app.brokers.robinhood_oauth import _fernet, BrokerOAuthConfigurationError
from app.models.models import BrokerConnection

BROKER = 'binance_us_spot'
BASE_URL = 'https://api.binance.us'
SYMBOLS = ('BTCUSD', 'ETHUSD')
PUBLIC = {'/api/v3/time', '/api/v3/exchangeInfo', '/api/v3/ticker/bookTicker'}
PRIVATE = {'/api/v3/account', '/api/v3/openOrders', '/sapi/v1/asset/query/trading-fee'}


class BinanceError(RuntimeError):
    pass


def amount(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            raise ValueError
        return number
    except (InvalidOperation, ValueError):
        raise BinanceError('Binance.US returned an invalid numeric value') from None


class BinanceUSReader:
    def __init__(self, api_key='', api_secret=''):
        self._key, self._secret = api_key, api_secret

    def get(self, path, params=None):
        if path not in PUBLIC | PRIVATE:
            raise BinanceError('Unsupported Binance.US read endpoint')
        params = dict(params or {})
        headers = {}
        if path in PRIVATE:
            if not self._key or not self._secret:
                raise BinanceError('Binance.US credentials are required')
            server = self.get('/api/v3/time')
            try:
                params.update(timestamp=int(server['serverTime']), recvWindow=5000)
            except (KeyError, TypeError, ValueError):
                raise BinanceError('Binance.US time service is unavailable') from None
            query = urlencode(params)
            params['signature'] = hmac.new(self._secret.encode(), query.encode(), hashlib.sha256).hexdigest()
            headers['X-MBX-APIKEY'] = self._key
        try:
            response = httpx.get(BASE_URL + path, params=params, headers=headers, timeout=12, follow_redirects=False)
            if response.status_code != 200:
                messages = {401: 'API key rejected', 403: 'API access denied; check key permissions and IP restrictions',
                            429: 'Rate limit reached; retry later', 451: 'Service unavailable from this region'}
                raise BinanceError('Binance.US: ' + messages.get(response.status_code, 'request failed; check key, permissions, IP restriction and service status'))
            data = response.json()
            if not isinstance(data, (dict, list)):
                raise BinanceError('Binance.US returned an invalid response')
            return data
        except (httpx.HTTPError, ValueError):
            # Never expose an exception URL, signed query, response body or key.
            raise BinanceError('Binance.US could not be reached or returned invalid data') from None

    def account(self):
        data = self.get('/api/v3/account')
        if not isinstance(data, dict) or not data.get('uid') or not isinstance(data.get('balances'), list):
            raise BinanceError('Binance.US account identity or balances are unavailable')
        balances = []
        seen = set()
        for row in data['balances']:
            if not isinstance(row, dict) or not isinstance(row.get('asset'), str) or row['asset'] in seen:
                raise BinanceError('Binance.US returned invalid balances')
            seen.add(row['asset'])
            free, locked = amount(row.get('free')), amount(row.get('locked'))
            if free + locked > 0 or row['asset'] == 'USD':
                balances.append({'asset': row['asset'], 'free': str(free), 'locked': str(locked)})
        return {'uid': str(data['uid']), 'balances': balances, 'broker_can_trade': data.get('canTrade') is True}

    def markets(self):
        rows = []
        for symbol in SYMBOLS:
            info = self.get('/api/v3/exchangeInfo', {'symbol': symbol})
            book = self.get('/api/v3/ticker/bookTicker', {'symbol': symbol})
            try:
                asset = info['symbols'][0]
                if asset['symbol'] != symbol or book['symbol'] != symbol:
                    raise ValueError
                bid, ask = amount(book['bidPrice']), amount(book['askPrice'])
                if bid <= 0 or ask < bid:
                    raise ValueError
                filters = {f['filterType']: f for f in asset['filters']}
                minimum = filters.get('NOTIONAL', filters.get('MIN_NOTIONAL', {}))['minNotional']
                rows.append({'symbol': symbol, 'status': asset['status'],
                             'spot_allowed': asset.get('isSpotTradingAllowed') is True,
                             'maker_only_supported': 'LIMIT_MAKER' in asset['orderTypes'],
                             'bid': str(bid), 'ask': str(ask),
                             'spread_bps': str((ask-bid)/((ask+bid)/2)*10000),
                             'min_notional': str(amount(minimum)),
                             'quantity_step': str(amount(filters['LOT_SIZE']['stepSize'])),
                             'observed_at': datetime.now(timezone.utc).isoformat()})
            except (KeyError, IndexError, TypeError, ValueError):
                raise BinanceError('Binance.US market data is incomplete') from None
        return {'source': 'Binance.US', 'markets': rows, 'execution_enabled': False}


def connect(db, api_key, api_secret, encryption_key):
    cipher = _fernet(encryption_key)
    account = BinanceUSReader(api_key, api_secret).account()
    existing = db.get(BrokerConnection, BROKER)
    if existing:
        stored = _decode(existing, encryption_key)
        if stored['uid'] != account['uid']:
            raise BinanceError('This key belongs to a different account; account replacement requires a separate migration')
    encrypted = cipher.encrypt(json.dumps({'api_key': api_key, 'api_secret': api_secret, 'uid': account['uid']}).encode()).decode()
    if existing is None:
        existing = BrokerConnection(broker=BROKER, client_id='encrypted-api-key', encrypted_refresh_token=encrypted, status='authorized')
        db.add(existing)
    else:
        existing.encrypted_refresh_token = encrypted
        existing.connected_at = datetime.utcnow()
        existing.status = 'authorized'
    db.commit()
    return {'connected': True, 'account_last4': account['uid'][-4:], 'execution_enabled': False}


def _decode(record, encryption_key):
    try:
        data = json.loads(_fernet(encryption_key).decrypt(record.encrypted_refresh_token.encode()))
        if not all(isinstance(data.get(k), str) and data[k] for k in ('api_key', 'api_secret', 'uid')):
            raise ValueError
        return data
    except Exception:
        raise BrokerOAuthConfigurationError('Stored Binance.US credentials cannot be read') from None


def status(db):
    row = db.get(BrokerConnection, BROKER)
    return {'broker': BROKER, 'credentials_saved': bool(row and row.status == 'authorized'),
            'read_only_ready': False, 'execution_enabled': False}


def readiness(db, encryption_key):
    row = db.get(BrokerConnection, BROKER)
    if not row or row.status != 'authorized':
        raise BinanceError('Connect your Binance.US API key first')
    stored = _decode(row, encryption_key)
    reader = BinanceUSReader(stored['api_key'], stored['api_secret'])
    account = reader.account()
    if account['uid'] != stored['uid']:
        raise BinanceError('Binance.US account identity changed')
    orders = reader.get('/api/v3/openOrders')
    if not isinstance(orders, list):
        raise BinanceError('Binance.US open orders are unavailable')
    fees = reader.get('/sapi/v1/asset/query/trading-fee')
    if not isinstance(fees, list):
        raise BinanceError('Binance.US account fees are unavailable')
    selected = []
    for symbol in SYMBOLS:
        matches = [r for r in fees if isinstance(r, dict) and r.get('symbol') == symbol]
        if len(matches) != 1:
            raise BinanceError('Binance.US omitted a requested account fee')
        row = matches[0]
        selected.append({'symbol': symbol, 'maker': str(amount(row.get('makerCommission'))),
                         'taker': str(amount(row.get('takerCommission')))})
    return {'broker': BROKER, 'connected': True, 'read_only_ready': True,
            'execution_enabled': False, 'account_last4': account['uid'][-4:],
            'broker_can_trade': account['broker_can_trade'], 'balances': account['balances'],
            'open_orders': len(orders), 'fees': selected,
            'verified_at': datetime.now(timezone.utc).isoformat()}
