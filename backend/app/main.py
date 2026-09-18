from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.db.session import Base, engine, get_db, initialize_schema
from app.models import models  # noqa: F401 ensures models are registered
from app.core.config import settings
from app.runtime.paper import paper_status
from app.analytics.performance import account_performance
from app.brokers.robinhood_oauth import (BrokerOAuthConfigurationError, connection_status,
    finish_connection, start_connection)
from app.brokers.robinhood_mcp import RobinhoodMcpError, discover_capabilities
from app.security.dashboard import require_dashboard_access

initialize_schema(engine)

app = FastAPI(title="Project 100", version="0.1.0-phase1")


@app.get("/paper/status", dependencies=[Depends(require_dashboard_access)])
def get_paper_status(db: Session = Depends(get_db)):
    return paper_status(db)


@app.get("/paper/performance", dependencies=[Depends(require_dashboard_access)])
def get_paper_performance(db: Session = Depends(get_db)):
    return account_performance(db)


@app.get("/paper/activity", dependencies=[Depends(require_dashboard_access)])
def get_paper_activity(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    """Recent append-only paper-runtime actions for the operator dashboard."""
    events = (db.query(models.AuditLogEntry)
              .filter(models.AuditLogEntry.event_type.in_([
                  "paper_event_committed", "paper_trade_closed", "state_change",
                  "kill_switch", "risk_veto", "error",
              ]))
              .order_by(models.AuditLogEntry.timestamp.desc(), models.AuditLogEntry.id.desc())
              .limit(limit).all())
    return {"mode": "paper", "simulated": True, "events": [
        {"id": event.id, "timestamp": event.timestamp, "type": event.event_type,
         "actor": event.actor, "payload": event.payload}
        for event in events
    ]}


@app.get("/brokers/robinhood/status", dependencies=[Depends(require_dashboard_access)])
def robinhood_status(db: Session = Depends(get_db)):
    """Connection state without exposing credentials or account data."""
    status = connection_status(db)
    return {
        **status,
        "setup_url": "https://robinhood.com/us/en/support/articles/agentic-trading-overview/",
        "account_requirement": "A dedicated Robinhood Agentic Trading account is required.",
    }


@app.get("/brokers/robinhood/connect", dependencies=[Depends(require_dashboard_access)])
def robinhood_connect(db: Session = Depends(get_db)):
    """Begin the user-authorized OAuth flow. This endpoint never invokes MCP tools."""
    try:
        return RedirectResponse(start_connection(db, settings.BROKER_OAUTH_REDIRECT_URL), status_code=302)
    except BrokerOAuthConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/brokers/robinhood/callback")
def robinhood_callback(state: str, code: str, db: Session = Depends(get_db)):
    try:
        result = finish_connection(db, state, code, settings.BROKER_OAUTH_REDIRECT_URL,
                                   settings.BROKER_TOKEN_ENCRYPTION_KEY)
        return JSONResponse(result)
    except BrokerOAuthConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/brokers/robinhood/capabilities", dependencies=[Depends(require_dashboard_access)])
def robinhood_capabilities(db: Session = Depends(get_db)):
    """Discover broker-advertised tools only; this endpoint cannot call one."""
    try:
        return discover_capabilities(db, settings.BROKER_TOKEN_ENCRYPTION_KEY)
    except (BrokerOAuthConfigurationError, RobinhoodMcpError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/dashboard", response_class=HTMLResponse, dependencies=[Depends(require_dashboard_access)])
def dashboard():
    """Dependency-free operations dashboard that refreshes once per second."""
    return HTMLResponse("""<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Project 100 Dashboard</title>
<style>body{font:15px system-ui,sans-serif;background:#09111f;color:#e9efff;margin:0;padding:24px}main{max-width:1160px;margin:auto}h1{margin:0 0 4px}.sub{color:#9fb0cc}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:18px 0}.card{background:#121d30;border:1px solid #263a59;border-radius:10px;padding:14px}.label{color:#9fb0cc;font-size:12px;text-transform:uppercase}.value{font-size:23px;font-weight:650;margin-top:4px}.good{color:#61d7a4}.warn{color:#ffd27b}.bad{color:#ff8c99}table{width:100%;border-collapse:collapse;background:#121d30;border-radius:10px;overflow:hidden}th,td{text-align:left;padding:10px;border-bottom:1px solid #263a59;vertical-align:top}th{color:#9fb0cc;font-size:12px}code{white-space:pre-wrap;color:#c8d7f3}a{color:#8cc8ff}</style></head><body><main>
<h1>Project 100</h1><div class=\"sub\">Operational dashboard &middot; paper simulation only &middot; refreshes every second</div>
<div class=\"grid\" id=\"cards\"></div><h2>Broker connection</h2><div class=\"card\" id=\"broker\">Loading&hellip;</div>
<h2>Recent actions</h2><table><thead><tr><th>Time</th><th>Action</th><th>Details</th></tr></thead><tbody id=\"activity\"></tbody></table>
</main><script>
const money=n=>typeof n==='number'?new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(n):'—';
const pct=n=>typeof n==='number'?(n*100).toFixed(2)+'%':'—';
const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
async function refresh(){try{const [status,performance,activity,broker]=await Promise.all(['/paper/status','/paper/performance','/paper/activity','/brokers/robinhood/status'].map(u=>fetch(u).then(r=>r.json())));const state=status.ready?'ready for fresh simulation data':status.state==='paper'?'waiting for fresh simulation data':status.status||'not started';const tone=status.ready?'good':state.includes('waiting')?'warn':'bad';document.querySelector('#cards').innerHTML=[['Runtime state',state,tone],['Equity',money(status.equity),''],['Cash',money(status.cash),''],['Open positions',Object.keys(status.positions||{}).length,''],['Realized P&L',money(status.realized_pnl),''],['Max drawdown',pct(status.max_drawdown),''],['Data age',status.data_age_seconds==null?'—':status.data_age_seconds.toFixed(1)+' sec',''],['Closed trades',performance.overall?.sample_size??0,'']].map(([l,v,c])=>`<div class=\"card\"><div class=\"label\">${l}</div><div class=\"value ${c}\">${esc(v)}</div></div>`).join('');document.querySelector('#broker').innerHTML=`<strong class=\"${broker.connected?'good':'warn'}\">${broker.connected?'Connected':'Not connected'}</strong><p>${esc(broker.reason)}</p><a href=\"${esc(broker.setup_url)}\" target=\"_blank\" rel=\"noreferrer\">Open official Robinhood setup</a>`;document.querySelector('#activity').innerHTML=(activity.events||[]).map(e=>`<tr><td>${esc(new Date(e.timestamp+'Z').toLocaleString())}</td><td>${esc(e.type)}</td><td><code>${esc(JSON.stringify(e.payload))}</code></td></tr>`).join('')||'<tr><td colspan=\"3\">No recorded paper activity yet.</td></tr>'}catch(e){document.querySelector('#broker').textContent='Dashboard refresh failed: '+e.message}}
refresh();setInterval(refresh,1000);</script></body></html>""")


@app.get("/ready")
def readiness(db: Session = Depends(get_db)):
    status = paper_status(db)
    return JSONResponse(status, status_code=200 if status["ready"] else 503)


@app.get("/health")
def health():
    return {"status": "ok", "trading_mode": settings.TRADING_MODE, "autonomy_level": settings.AUTONOMY_LEVEL}


@app.get("/system/state", dependencies=[Depends(require_dashboard_access)])
def get_state(db: Session = Depends(get_db)):
    rec = db.get(models.SystemStateRecord, "current")
    if not rec:
        rec = models.SystemStateRecord(id="current", state="off", reason="initial")
        db.add(rec)
        db.commit()
        db.refresh(rec)
    return {"state": rec.state, "reason": rec.reason, "updated_at": rec.updated_at}


@app.get("/config/risk", dependencies=[Depends(require_dashboard_access)])
def get_risk_config():
    """Read-only view of active risk configuration (no secrets)."""
    return {
        "MAX_RISK_PER_TRADE": settings.MAX_RISK_PER_TRADE,
        "MAX_DAILY_LOSS": settings.MAX_DAILY_LOSS,
        "MAX_WEEKLY_DRAWDOWN": settings.MAX_WEEKLY_DRAWDOWN,
        "MAX_TOTAL_DRAWDOWN": settings.MAX_TOTAL_DRAWDOWN,
        "MAX_POSITIONS": settings.MAX_POSITIONS,
        "ALLOW_MARGIN": settings.ALLOW_MARGIN,
        "ALLOW_OPTIONS": settings.ALLOW_OPTIONS,
        "ALLOW_SHORTS": settings.ALLOW_SHORTS,
        "ALLOW_LEVERAGE": settings.ALLOW_LEVERAGE,
        "AUTO_EXECUTION": settings.AUTO_EXECUTION,
    }
