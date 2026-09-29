"""Authenticated Binance.US onboarding, balances and public quotes."""
import json
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from app.brokers import binance_us
from app.brokers.robinhood_oauth import BrokerOAuthConfigurationError
from app.core.config import settings
from app.db.session import get_db
from app.security.dashboard import require_dashboard_access

router = APIRouter(prefix='/brokers/binance-us', dependencies=[Depends(require_dashboard_access)])


def reply(data):
    return JSONResponse(data, headers={'Cache-Control': 'no-store'})


@router.get('/status')
def status(db: Session = Depends(get_db)):
    return reply(binance_us.status(db))


@router.get('/markets')
def markets():
    try:
        return reply(binance_us.BinanceUSReader().markets())
    except binance_us.BinanceError as exc:
        raise HTTPException(503, str(exc)) from None


@router.get('/readiness')
def readiness(db: Session = Depends(get_db)):
    try:
        return reply(binance_us.readiness(db, settings.BROKER_TOKEN_ENCRYPTION_KEY))
    except (binance_us.BinanceError, BrokerOAuthConfigurationError) as exc:
        raise HTTPException(503, str(exc)) from None


@router.post('/connect')
async def connect(request: Request, db: Session = Depends(get_db)):
    # A custom header blocks cross-site form submissions; no CORS is enabled.
    origin = request.headers.get('origin')
    if (request.headers.get('x-veloikos-setup') != 'binance-us' or
        (origin and urlsplit(origin).netloc != request.headers.get('host'))):
        raise HTTPException(403, 'Use the Veloikos connection page')
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4096:
            raise HTTPException(400, 'Credential request is too large')
    try:
        data = json.loads(body)
        key, secret = data['api_key'], data['api_secret']
        if not all(isinstance(v, str) and 16 <= len(v) <= 256 and v.isascii() and v.isalnum() for v in (key, secret)):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        # Never echo submitted credentials in validation errors.
        raise HTTPException(400, 'Enter a valid Binance.US API key and secret') from None
    try:
        return reply(binance_us.connect(db, key, secret, settings.BROKER_TOKEN_ENCRYPTION_KEY))
    except (binance_us.BinanceError, BrokerOAuthConfigurationError) as exc:
        raise HTTPException(400, str(exc)) from None


@router.get('/connect', response_class=HTMLResponse)
def page():
    return HTMLResponse(PAGE, headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
        'X-Frame-Options': 'DENY', 'Content-Security-Policy': "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'"})


PAGE = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Connect Binance.US · Veloikos</title><style>
body{background:#0c111b;color:#e6edf6;font:16px system-ui;margin:0;padding:28px}main{max-width:800px;margin:auto}a{color:#80c9ff}h1{font-size:32px}section{background:#141e2c;border:1px solid #314055;border-radius:16px;padding:24px;margin:20px 0}label{display:block;margin-top:16px}input{display:block;box-sizing:border-box;width:100%;padding:12px;background:#0c111b;color:white;border:1px solid #536378;border-radius:8px;margin:8px 0}button{background:#afd6ff;color:#081626;border:0;border-radius:8px;padding:12px 18px;cursor:pointer;margin:10px 8px 0 0}button:disabled{opacity:.5}p{line-height:1.6}.muted{color:#adbdcf}#result,#marketResult{white-space:pre-wrap;line-height:1.7;overflow-wrap:anywhere}li{margin:12px 0}
</style><main><a href="/dashboard">← Veloikos dashboard</a><h1>Connect Binance.US</h1><p>Connect your crypto account to view balances, open-order count and your actual trading fees. Trading is not activated by connecting.</p>
<section><h2>1. Prepare your API key</h2><ol><li>Sign in and complete account verification at <a href="https://www.binance.us/" target="_blank" rel="noopener noreferrer">Binance.US</a>.</li><li>In your profile, open <b>API Management</b> and create an Exchange API key named <b>Veloikos</b>.</li><li>For this connection check, enable <b>Read</b> only. Keep withdrawals disabled. Restrict access to your Veloikos server IP: <b>104.248.229.235</b>.</li></ol><p class="muted">Enter credentials below, not in chat. They are encrypted on the Veloikos server and never returned to the browser.</p></section>
<section><h2>2. Connect your account</h2><form id="setup" autocomplete="off"><label for="key">API key</label><input id="key" type="password" required autocomplete="off" maxlength="256"><label for="secret">API secret</label><input id="secret" type="password" required autocomplete="off" maxlength="256"><button id="save" type="submit">Verify and connect</button><button id="verify" type="button">Refresh account</button></form><p id="result" role="status" aria-live="polite">Checking connection…</p></section>
<section><h2>Binance.US market data</h2><p>BTC/USD and ETH/USD quotes and order minimums come directly from Binance.US. Quotes are snapshots; refresh before evaluating costs.</p><button id="refreshMarkets" type="button">Refresh quotes</button><p id="marketResult" role="status">Loading markets…</p><p class="muted">Maker orders may remain unfilled. Your account fee check above is separate from the public fee schedule.</p></section></main>
<script>
const el=id=>document.getElementById(id);async function api(path,options){const r=await fetch('/brokers/binance-us/'+path,{cache:'no-store',...options});const d=await r.json();if(!r.ok)throw new Error(typeof d.detail==='string'?d.detail:'Request failed');return d}
async function verify(){el('verify').disabled=true;el('result').textContent='Verifying account…';try{const d=await api('readiness');el('result').textContent='Connected · account ending '+d.account_last4+'\nVerified '+new Date(d.verified_at).toLocaleString()+'\n'+(d.balances.length?d.balances.map(b=>b.asset+': '+b.free+' available, '+b.locked+' locked').join('\n'):'No nonzero balances reported')+'\nOpen orders: '+d.open_orders+'\n'+d.fees.map(f=>f.symbol+': '+(Number(f.maker)*100).toFixed(4)+'% maker / '+(Number(f.taker)*100).toFixed(4)+'% taker').join('\n')+'\nTrading is not activated.'}catch(e){el('result').textContent=e.message}finally{el('verify').disabled=false}}
el('setup').addEventListener('submit',async e=>{e.preventDefault();el('save').disabled=true;const data={api_key:el('key').value.trim(),api_secret:el('secret').value.trim()};el('key').value='';el('secret').value='';el('result').textContent='Checking credentials…';try{await api('connect',{method:'POST',headers:{'Content-Type':'application/json','X-Veloikos-Setup':'binance-us'},body:JSON.stringify(data)});await verify()}catch(e){el('result').textContent=e.message}finally{el('save').disabled=false}});
async function markets(){el('refreshMarkets').disabled=true;try{const d=await api('markets');el('marketResult').textContent=d.markets.map(m=>m.symbol+' · '+m.status+'\nBid $'+m.bid+' / Ask $'+m.ask+'\nMinimum $'+m.min_notional+'; quantity step '+m.quantity_step+'\nObserved '+new Date(m.observed_at).toLocaleString()).join('\n\n')}catch(e){el('marketResult').textContent=e.message}finally{el('refreshMarkets').disabled=false}}
el('verify').onclick=verify;el('refreshMarkets').onclick=markets;api('status').then(d=>{if(d.credentials_saved)verify();else el('result').textContent='No Binance.US account connected yet.'}).catch(e=>el('result').textContent=e.message);markets();
</script></html>'''
