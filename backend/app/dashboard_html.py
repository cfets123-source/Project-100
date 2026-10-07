DASHBOARD_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Veloikos Trading</title>
<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#0b0e11"><link rel="apple-touch-icon" href="/static/icon-192.png"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><meta name="apple-mobile-web-app-title" content="Veloikos">
<style>
:root{--bg:#0b0e11;--panel:#12161b;--panel2:#171c22;--line:#232a32;--ink:#eaecef;--sub:#8b949e;--up:#0ecb81;--down:#f6465d;--gold:#f0b90b;--blue:#4c9aff}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,sans-serif;-webkit-font-smoothing:antialiased}
button{font:inherit;color:inherit}
.top{display:flex;align-items:center;gap:22px;height:56px;padding:0 18px;background:var(--panel);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:10}
.brand{display:flex;align-items:center;gap:9px;font-weight:700;font-size:17px;white-space:nowrap}.brand img{height:26px}
.pill{font-size:11px;font-weight:700;letter-spacing:.6px;padding:4px 9px;border-radius:4px;background:#2b3139;color:var(--sub);white-space:nowrap}
.pill.live{background:rgba(14,203,129,.15);color:var(--up)}.pill.halt{background:rgba(246,70,93,.15);color:var(--down)}.pill.paper{background:rgba(76,154,255,.15);color:var(--blue)}
.kpis{display:flex;gap:26px;margin-left:auto;overflow-x:auto}.kpi{white-space:nowrap}.kpi>span{display:block;font-size:11px;color:var(--sub)}.kpi b{font-size:15px;font-variant-numeric:tabular-nums}
.up{color:var(--up)}.down{color:var(--down)}.muted{color:var(--sub)}
.wrap{max-width:1600px;margin:0 auto;padding:14px;display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:14px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;min-width:0}
.chart-head{display:flex;align-items:center;gap:18px;padding:12px 14px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.sym{font-size:20px;font-weight:700}.px{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums}.chg{font-size:13px;font-weight:600}
.ptabs{display:flex;gap:6px;overflow-x:auto;padding:8px 14px;border-bottom:1px solid var(--line)}.ptabs:empty{display:none}.pchip{flex:0 0 auto;display:flex;gap:8px;align-items:center;padding:5px 10px;border-radius:6px;border:1px solid var(--line);background:var(--bg);color:var(--ink);cursor:pointer;font-size:13px;font-variant-numeric:tabular-nums}.pchip.on{border-color:var(--gold);background:var(--panel2)}.pchip small{color:var(--sub);font-size:11px}.prow{display:grid;grid-template-columns:auto 1fr auto;gap:4px 10px;padding:8px 0;border-bottom:1px solid var(--line);cursor:pointer}.prow:last-child{border:0}.prow:hover{background:var(--panel2)}.prow .range,.prow .range-lbl{grid-column:1/-1}
.tfs{display:flex;gap:2px;margin-left:auto;background:var(--bg);border-radius:6px;padding:2px}
.tf{background:none;border:0;padding:5px 11px;border-radius:5px;cursor:pointer;color:var(--sub);font-size:13px}.tf.on{background:#2b3139;color:var(--ink)}
.ohlc{padding:6px 14px;font-size:12px;color:var(--sub);font-variant-numeric:tabular-nums;min-height:28px}.ohlc b{color:var(--ink);font-weight:600;margin-right:10px}
.chart-box{position:relative;height:460px}canvas{display:block;width:100%;height:100%}
.chart-msg{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--sub)}
.side h3,.card h3{margin:0;font-size:13px;font-weight:600;padding:12px 14px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between}
.wl{max-height:520px;overflow-y:auto}
.wrow{display:grid;grid-template-columns:1fr auto auto;gap:12px;width:100%;padding:9px 14px;background:none;border:0;border-left:2px solid transparent;cursor:pointer;text-align:left;font-variant-numeric:tabular-nums}
.wrow:hover{background:var(--panel2)}.wrow.on{background:var(--panel2);border-left-color:var(--gold)}.wrow small{display:block;font-size:11px;color:var(--sub)}
.cards{grid-column:1/-1;display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}.tape{display:flex;gap:0;overflow-x:auto;background:var(--panel);border-bottom:1px solid var(--line);scrollbar-width:none}.tape::-webkit-scrollbar{display:none}.tk{flex:0 0 auto;display:flex;gap:8px;align-items:baseline;padding:8px 16px;border:0;border-right:1px solid var(--line);background:none;cursor:pointer;font-variant-numeric:tabular-nums;font-size:13px}.tk:hover{background:var(--panel2)}.tk b{font-weight:600}.acct{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid var(--line)}.acct:last-child{border:0}.acct small{display:block;color:var(--sub);font-size:11px}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;background:#5e6673}.dot.on{background:var(--up)}.dot.warn{background:var(--gold)}.dot.off{background:#5e6673}.acct a{color:var(--gold);font-size:12px;white-space:nowrap}
.body{padding:14px}.big{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums}
.kv{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}.kv:last-child{border:0}.kv span{color:var(--sub)}
.range{position:relative;height:8px;border-radius:4px;margin:16px 0 6px;background:linear-gradient(90deg,var(--down),#2b3139 45%,var(--up))}
.range i{position:absolute;top:-4px;width:3px;height:16px;background:var(--ink);border-radius:2px;transform:translateX(-50%)}
.range-lbl{display:flex;justify-content:space-between;font-size:11px;color:var(--sub)}
.bar{height:8px;background:#2b3139;border-radius:4px;overflow:hidden;margin:14px 0 6px}.bar i{display:block;height:100%;background:var(--gold)}
.rule{display:flex;gap:9px;padding:6px 0;font-size:13px}.rule b{color:var(--gold);min-width:16px}
.status{margin-top:12px;padding:9px 11px;border-radius:6px;background:var(--panel2);font-size:13px}
.tabs{grid-column:1/-1}.tabbar{display:flex;gap:4px;padding:0 10px;border-bottom:1px solid var(--line)}
.tab{background:none;border:0;border-bottom:2px solid transparent;padding:11px 10px;cursor:pointer;color:var(--sub);font-weight:600}.tab.on{color:var(--ink);border-bottom-color:var(--gold)}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}th,td{text-align:left;padding:9px 14px;border-bottom:1px solid var(--line);white-space:nowrap}th{font-size:11px;color:var(--sub);font-weight:600}
.tblwrap{overflow-x:auto;max-height:320px;overflow-y:auto}.empty{padding:18px 14px;color:var(--sub)}
.foot{grid-column:1/-1;display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:var(--sub);padding:2px 4px 20px}.foot a{color:var(--sub)}
.tip{grid-column:1/-1;display:none;padding:10px 14px;border-radius:8px;background:rgba(240,185,11,.10);color:#f3d27a;border:1px solid rgba(240,185,11,.35);font-size:14px}.tip.show{display:block}.abtn{cursor:pointer;border:1px solid var(--line);background:transparent;color:var(--ink)}
.banner{grid-column:1/-1;display:none;padding:10px 14px;border-radius:8px;background:rgba(246,70,93,.12);color:#ffb3bd;border:1px solid rgba(246,70,93,.35)}.banner.show{display:block}
@media(max-width:1000px){.wrap{grid-template-columns:1fr}.cards{grid-template-columns:1fr}.chart-box{height:340px}.top{gap:10px;padding:8px 12px;height:auto;flex-wrap:wrap;padding-top:max(8px,env(safe-area-inset-top))}.top .kpis{width:100%;margin-left:0}.kpis{gap:16px}.wl{max-height:none;display:flex;overflow-x:auto}.wrow{width:170px;min-width:170px;flex:0 0 auto;grid-template-columns:1fr auto;row-gap:2px}.wrow>span:last-child{grid-column:2}.brand{font-size:15px}}
/* ---------- terminal skin ---------- */
:root{--bg:#07090b;--panel:#0d1014;--panel2:#12161b;--line:#1d232b;--ink:#e6e8ea;--sub:#7d8590;--accent:#ff7a1a;--mono:ui-monospace,SFMono-Regular,"JetBrains Mono",Menlo,Consolas,monospace}
.panel{border-radius:4px;border-color:var(--line)}
.kpi>span,.panel h3,.tab,th,.pill,.range-lbl,.ohlc,.stage-name{font-family:var(--mono);text-transform:uppercase;letter-spacing:.08em;font-size:11px}
.kpi b,.px,.sym,td,.wrow span,.tk span,.big,.kv b,.pchip span{font-family:var(--mono);font-variant-numeric:tabular-nums}
.tab.on{color:var(--accent)!important;border-bottom-color:var(--accent)!important}.wrow.on{border-left-color:var(--accent)}.pchip.on{border-color:var(--accent)}
.tf.on{background:rgba(255,122,26,.14);color:var(--accent)}.top{background:#090c0f}
.pipe{grid-column:1/-1;padding:12px 14px}.pipe h3{display:flex;justify-content:space-between;margin:0 0 10px;color:var(--sub)}
.prow2{display:grid;grid-template-columns:190px minmax(0,1fr);gap:12px;align-items:center;padding:9px 0;border-top:1px solid var(--line)}
.prow2:first-of-type{border-top:0}.pname b{display:block;font-size:14px}.pname small{color:var(--sub);font-size:11px}
.stages{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:4px}
.stage{padding:6px 7px;border:1px solid var(--line);border-radius:3px;background:var(--bg);min-width:0;cursor:default}
.stage .stage-name{display:block;font-size:10px;color:var(--sub);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.stage i{display:block;height:3px;margin-top:6px;border-radius:2px;background:#232a32}
.stage.done i{background:var(--up)}.stage.current{border-color:var(--accent);box-shadow:inset 0 0 0 1px rgba(255,122,26,.25)}.stage.current i{background:var(--accent)}
.stage.current .stage-name{color:var(--accent)}.stage.done .stage-name{color:var(--ink)}
.rv{padding:12px 14px;display:grid;gap:12px}.rv-card{border:1px solid var(--line);border-radius:4px;padding:10px 12px}
.flag{font-family:var(--mono);font-size:12px;padding:3px 0}.flag.alert{color:var(--down)}.flag.warn{color:#f3d27a}.flag.info{color:var(--up)}
@media(max-width:1000px){#pipeTs{display:none}.prow2{grid-template-columns:1fr}.stages{overflow-x:auto;grid-template-columns:repeat(7,minmax(92px,1fr))}}
</style></head><body>
<header class="top"><div class="brand"><img src="/static/veloikos-mark.png" alt="">Veloikos Trading</div><span id="mode" class="pill">Checking execution state</span><button id="alerts" class="pill abtn" type="button">Turn on alerts</button>
<div class="kpis"><div class="kpi"><span>Equity</span><b id="kEq">—</b></div><div class="kpi"><span>Open P&amp;L</span><b id="kPl">—</b></div><div class="kpi"><span>Cash</span><b id="kCash">—</b></div><div class="kpi"><span>Open positions</span><b id="kPos">—</b></div><div class="kpi"><span>Market</span><b id="kMkt">—</b></div></div></header>
<div id="tape" class="tape"><span class="tk muted">Loading live markets…</span></div>
<div class="wrap">
<div id="banner" class="banner"></div><div id="tip" class="tip"></div>
<section class="panel"><div class="chart-head"><span id="cSym" class="sym">TQQQ</span><span id="cPx" class="px">—</span><span id="cChg" class="chg muted"></span><span id="cFeed" class="muted" style="font-size:12px"></span>
<div class="tfs"><button class="tf" data-tf="1Min">1m</button><button class="tf on" data-tf="5Min">5m</button><button class="tf" data-tf="15Min">15m</button><button class="tf" data-tf="1Day">1D</button></div></div>
<div id="posTabs" class="ptabs"></div><div id="ohlc" class="ohlc">Hover the chart for open, high, low and close.</div>
<div class="chart-box"><canvas id="cv"></canvas><div id="cMsg" class="chart-msg">Loading candles…</div></div></section>
<aside class="panel side"><h3>Watchlist <span class="muted" id="wlSrc"></span></h3><div id="wl" class="wl"><div class="empty">Loading prices…</div></div></aside>
<section class="panel pipe"><h3><span>Strategy pipeline</span><span id="pipeTs" class="muted"></span></h3><div id="pipe"><div class="empty">Loading pipeline…</div></div></section>
<div class="cards">
<article class="panel card"><h3>Open positions <span id="posTag" class="muted"></span></h3><div id="pos" class="body"><div class="muted">Loading broker position…</div></div></article>
<article class="panel card"><h3>Milestone</h3><div id="ms" class="body"><div class="muted">Loading…</div></div></article>
<article class="panel card"><h3>Strategy <span class="muted">Allocator v1</span></h3><div class="body">
<div class="rule"><b>1</b><span><strong>Core (50%):</strong> TQQQ while QQQ is above its 200-day average; broker stop −25% / target +50%.</span></div>
<div class="rule"><b>2</b><span><strong>Satellites (50%):</strong> up to 5 fractional positions from the scanner (breakout / trend, all US markets). The worker sells at the <span class="down">stop</span>, the <span class="up">target</span> or the time limit.</span></div>
<div class="rule"><b>3</b><span>All cash and deposits are invested automatically. No new buys below $50 or after a 50% drop from the peak.</span></div>
<div id="stratStatus" class="status muted">Checking…</div></div></article>
<article class="panel card"><h3>Accounts</h3><div id="accts" class="body"><div class="muted">Checking connections…</div></div></article>
</div>
<section class="panel tabs"><div class="tabbar"><button class="tab on" data-t="orders">Open orders</button><button class="tab" data-t="trades">Trade history</button><button class="tab" data-t="log">Activity</button><button class="tab" data-t="scan">Market scanner</button><button class="tab" data-t="plan">Milestone plan</button><button class="tab" data-t="review">Nightly review</button></div>
<div id="t-orders" class="tblwrap"></div><div id="t-review" class="tblwrap" hidden style="max-height:none"><div class="empty">Loading review…</div></div><div id="t-trades" class="tblwrap" hidden></div><div id="t-log" class="tblwrap" hidden></div><div id="t-scan" class="tblwrap" hidden style="max-height:520px"><div class="empty">Loading scanner…</div></div><div id="t-plan" class="tblwrap" hidden style="max-height:none"><div class="body" style="display:flex;gap:14px;flex-wrap:wrap;align-items:end"><label class="muted" style="font-size:12px">Deposit<br><input id="pAmt" type="number" min="0" step="25" value="100" style="width:110px;padding:7px;background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:6px"></label><label class="muted" style="font-size:12px">How often<br><select id="pFreq" style="padding:7px;background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:6px"><option value="26">Every 2 weeks</option><option value="12">Monthly</option><option value="0">No deposits</option></select></label><span id="pNote" class="muted" style="font-size:12px"></span></div><div id="pOut"></div></div></section>
<footer class="foot"><span id="observer">Account observer: checking…</span><span>Read-only view · this page cannot place orders</span></footer>
</div>
<script>
const q=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num=v=>{let n=Number(v);return Number.isFinite(n)?n:null};
const money=v=>{let n=num(v);return n==null?'—':n.toLocaleString('en-US',{style:'currency',currency:'USD'})};
const signed=v=>{let n=num(v);return n==null?'—':(n>=0?'+':'−')+Math.abs(n).toLocaleString('en-US',{style:'currency',currency:'USD'})};
const pct=v=>{let n=num(v);return n==null?'':(n>=0?'+':'−')+Math.abs(n).toFixed(2)+'%'};
const cls=v=>num(v)==null?'muted':(num(v)>=0?'up':'down');
async function api(u){let r=await fetch(u,{credentials:'same-origin'});if(r.status===401||r.redirected&&r.url.includes('/login')){location.href='/login';throw Error('auth')}if(!r.ok)throw Error(u+' '+r.status);return r.json()}
let sym='TQQQ',tf='5Min',bars=[],quote={},ticker=[],orders=[],positions=[],lots=[],hover=null;
const PIN=['TQQQ','QQQ','SPY'];
/* ---------- installable app + trade alerts ---------- */
const STANDALONE=matchMedia('(display-mode: standalone)').matches||navigator.standalone===true,IOS=/iphone|ipad|ipod/i.test(navigator.userAgent);
let swReg=null;if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').then(r=>{swReg=r;alertsLabel()}).catch(()=>{});
function tip(t){let el=q('#tip');el.innerHTML=t;el.classList.toggle('show',!!t)}
async function alertsLabel(){let b=q('#alerts'),on=false;try{on=!!(swReg&&Notification.permission==='granted'&&await swReg.pushManager.getSubscription())}catch(_){}b.textContent=on?'Alerts on · test':'Turn on alerts';b.classList.toggle('live',on);b.dataset.on=on?'1':''}
function u8(t){let s=atob((t+'='.repeat((4-t.length%4)%4)).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from(s,c=>c.charCodeAt(0))}
async function post(u,body){let r=await fetch(u,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):'{}'});if(!r.ok)throw Error(u+' '+r.status);return r.json()}
q('#alerts').onclick=async()=>{let b=q('#alerts');try{
if(IOS&&!STANDALONE){tip('<b>iPhone:</b> tap the Share button, choose <b>Add to Home Screen</b>, open <b>Veloikos</b> from your home screen, then tap <b>Turn on alerts</b> there.');return}
if(!swReg||!('PushManager' in window)){tip('This browser cannot receive alerts. Use Chrome or Safari, or install the app to your home screen.');return}
if(b.dataset.on){let r=await post('/push/test');tip(r.sent?'Test alert sent to '+r.sent+' device'+(r.sent>1?'s':'')+'.':'No device received the test — turn alerts off and on in your phone settings.');return}
if(await Notification.requestPermission()!=='granted'){tip('Notifications are blocked. Allow them for this site in your phone or browser settings, then tap again.');return}
let k=await api('/push/public-key'),sub=await swReg.pushManager.getSubscription()||await swReg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:u8(k.public_key)});
await post('/push/subscribe',sub.toJSON());let r=await post('/push/test');tip(r.sent?'Alerts are on. You will get a notification for every buy, sell, stop-out and failure.':'Subscribed, but the test did not arrive yet.');alertsLabel()}
catch(e){if(e.message!=='auth')tip('Could not turn on alerts: '+esc(e.message))}};

/* ---------- execution state ---------- */
async function loadState(){let m=q('#mode'),b=q('#banner');try{let d=await api('/system/state'),s=String(d.state||'unknown');m.textContent=s==='live'?'LIVE':s.toUpperCase();m.className='pill '+(s==='live'?'live':s==='halted'?'halt':s==='paper'?'paper':'');b.classList.toggle('show',s==='halted');b.textContent=s==='halted'?'Trading is halted: '+(d.reason||'safety stop')+'. Open positions keep their broker stop and target.':''}catch(e){if(e.message!=='auth'){m.textContent='STATUS UNAVAILABLE';m.className='pill halt'}}}

/* ---------- account, position, milestone, tables ---------- */
function flatOrders(list){let out=[];(list||[]).forEach(o=>{out.push(o);(o.legs||[]).forEach(l=>out.push(l))});let live=new Set(['new','accepted','pending_new','pending','open','partially_filled','held']);return out.filter(o=>live.has(String(o.status)))}
function levels(symbol){let os=orders.filter(o=>o.symbol===symbol&&o.side==='sell');let stop=os.find(o=>/stop/.test(o.type||o.order_type||'')),tgt=os.find(o=>(o.type||o.order_type)==='limit');let lot=lots.find(l=>l.status==='open'&&l.symbol.replace('/','')===String(symbol).replace('/',''));let s=num(stop?.stop_price),t=num(tgt?.limit_price),w=false;if(s==null&&lot){s=num(lot.stop_price);w=true}if(t==null&&lot){t=num(lot.target_price);w=true}return{stop:s,target:t,worker:w,lot}}
async function loadAccount(){try{let [d,m,t,a,L]=await Promise.all([api('/brokers/alpaca/live-portfolio'),api('/live/milestones').catch(()=>({})),api('/live/trades?limit=50').catch(()=>({trades:[]})),api('/live/activity?limit=40').catch(()=>({events:[]})),api('/allocator/lots?mode=live').catch(()=>({lots:[]}))]);
let b=d.balances||{};positions=d.positions||[];orders=flatOrders(d.active_orders);lots=L.lots||[];acct={cash:num(b.cash),equity:num(b.equity)};positions.forEach(applyLive);
kpis();q('#kPos').textContent=positions.length;
q('#kMkt').innerHTML=d.market_clock?(d.market_clock.is_open?'<span class="up">Open</span>':'<span class="muted">Closed</span>'):'—';
renderPosition();renderChips();renderMilestone(m,num(b.equity));if(num(b.equity)&&planEquity==null){planEquity=num(b.equity);runPlan()}renderOrders();renderTrades(t.trades||[],lots);renderLog(a.events||[]);if(bars.length)draw();openStream()}
catch(e){if(e.message!=='auth'){q('#pos').innerHTML='<div class="muted">Broker account unavailable — retrying. This does not mean the account is empty.</div>'}}}
function pick2(s){sym=s;hover=null;drawWatch();renderChips();renderPosition();loadChart();openStream()}
/* ---------- real-time stream (server relays Alpaca IEX trades; no keys in the browser) ---------- */
let es=null,esKey='',live={},acct={},streamStatus='connecting',lastTick=0,dirty=false,lastSlow=0;
const TFMS={'1Min':6e4,'5Min':3e5,'15Min':9e5};
function kpis(){let mv=0,ok=true,pl=0;positions.forEach(p=>{let v=num(p.market_value);if(v==null)ok=false;else mv+=v;pl+=num(p.unrealized_pl)||0});
let eq=ok&&acct.cash!=null&&positions.length?acct.cash+mv:acct.equity;q('#kEq').textContent=money(eq);q('#kCash').textContent=money(acct.cash);
q('#kPl').innerHTML='<span class="'+cls(positions.length?pl:null)+'">'+(positions.length?signed(pl):'—')+'</span>'}
function applyLive(p){let L=live[p.symbol];if(!L||Date.now()-L.at>20000)return;let qn=num(p.qty),e=num(p.avg_entry_price);p.current_price=L.p;if(qn!=null){p.market_value=qn*L.p;if(e!=null){p.unrealized_pl=(L.p-e)*qn;p.unrealized_plpc=e?L.p/e-1:null}}}
function streamSyms(){let cr=new Set(positions.filter(p=>p.asset_class==='crypto').map(p=>p.symbol));return [...new Set([sym,...positions.map(p=>p.symbol)])].filter(x=>x&&!x.includes('/')&&!cr.has(x)).sort()}
function openStream(){if(!window.EventSource)return;let k=streamSyms().join(',');if(es&&k===esKey)return;esKey=k;if(es)es.close();
es=new EventSource('/terminal/stream?symbols='+encodeURIComponent(k));es.onmessage=e=>{let d;try{d=JSON.parse(e.data)}catch(_){return}
if(d.type==='status'){streamStatus=d.status;if(d.last)Object.values(d.last).forEach(x=>onTick(x,true));feedLabel();return}onTick(d)};es.onerror=()=>{streamStatus='reconnecting';feedLabel()}}
function onTick(d,old){if(d.type!=='trade'||!d.symbol)return;let p=+d.price;if(!(p>0))return;let ts=d.time?new Date(d.time):new Date();
live[d.symbol]={p,at:old?Date.now()-30000:Date.now()};if(!old)lastTick=Date.now();positions.forEach(x=>{if(x.symbol===d.symbol)applyLive(x)});
if(d.symbol===sym&&!old&&bars.length){let L=bars[bars.length-1],ms=TFMS[tf];if(ms){let bucket=Math.floor(ts.getTime()/ms)*ms;if(bucket>L.t.getTime()){bars.push({t:new Date(bucket),o:p,h:p,l:p,c:p,v:+d.size||0});if(bars.length>120)bars.shift()}else if(bucket===L.t.getTime()){L.c=p;L.h=Math.max(L.h,p);L.l=Math.min(L.l,p);L.v+=+d.size||0}}else{L.c=p;L.h=Math.max(L.h,p);L.l=Math.min(L.l,p)}}
if(d.symbol===sym)q('#cPx').textContent=money(p);dirty=true}
function frame(){if(dirty){dirty=false;if(!hover)draw();kpis();renderChips();let now=Date.now();if(now-lastSlow>1000){lastSlow=now;renderPosition()}}requestAnimationFrame(frame)}requestAnimationFrame(frame);
function feedLabel(){let el=q('#cFeed');if(!el)return;let age=lastTick?Math.round((Date.now()-lastTick)/1000):null;
el.innerHTML=streamStatus==='live'?'<span class="up">● Live</span> · Alpaca IEX'+(age!=null?' · last trade '+(age<60?age+'s':Math.round(age/60)+'m')+' ago':' · waiting for trades'):'<span class="muted">● '+esc(streamStatus==='reconnecting'?'Stream reconnecting — updating every 15s':'Connecting live stream…')+'</span>'}
setInterval(feedLabel,1000);
function renderChips(){let el=q('#posTabs');el.innerHTML=positions.map(p=>{let plp=num(p.unrealized_plpc);return '<button class="pchip'+(p.symbol===sym?' on':'')+'" data-s="'+esc(p.symbol)+'"><b>'+esc(p.symbol)+'</b><span>'+money(p.market_value)+'</span><span class="'+cls(plp)+'">'+(plp!=null?pct(plp*100):'')+'</span></button>'}).join('');el.querySelectorAll('.pchip').forEach(b=>b.onclick=()=>pick2(b.dataset.s))}
function renderPosition(){let el=q('#pos'),st=q('#stratStatus');if(!positions.length){q('#posTag').textContent='';el.innerHTML='<div class="big">Flat</div><div class="muted">No open position. The strategy waits for its entry signal.</div>';st.textContent='Flat — waiting for the next entry signal (checked every minute while the market is open).';return}
let tot=positions.reduce((s,p)=>s+(num(p.unrealized_pl)||0),0);q('#posTag').textContent=positions.length+' open';
el.innerHTML='<div class="big '+cls(tot)+'">'+signed(tot)+' <span style="font-size:13px" class="muted">open P&amp;L</span></div>'+positions.map(p=>{let cur=num(p.current_price),pl=num(p.unrealized_pl),plp=num(p.unrealized_plpc),lv=levels(p.symbol),range='';
if(lv.stop!=null&&lv.target!=null&&cur!=null){let x=Math.max(0,Math.min(100,(cur-lv.stop)/(lv.target-lv.stop)*100));range='<div class="range"><i style="left:'+x+'%"></i></div><div class="range-lbl"><span>Stop '+money(lv.stop)+'</span><span>'+(lv.worker?'worker-watched':'broker bracket')+'</span><span>Target '+money(lv.target)+'</span></div>'}
let role=lv.lot?(lv.lot.sleeve==='core'?'Core':'Satellite · '+lv.lot.rule):'';
return '<div class="prow'+(p.symbol===sym?' on':'')+'" data-s="'+esc(p.symbol)+'"><b>'+esc(p.symbol)+'</b><span class="muted" style="font-size:12px">'+esc(role)+' · '+esc(num(p.qty)?.toFixed(4).replace(/\.?0+$/,''))+' sh @ '+money(p.avg_entry_price)+'</span><span class="'+cls(pl)+'">'+signed(pl)+' '+(plp!=null?pct(plp*100):'')+'</span>'+range+'</div>'}).join('');
el.querySelectorAll('.prow').forEach(r=>r.onclick=()=>{pick2(r.dataset.s);window.scrollTo({top:0,behavior:'smooth'})});
let unprot=positions.filter(p=>levels(p.symbol).stop==null).map(p=>p.symbol);
st.innerHTML=unprot.length?'<span class="down">●</span> No stop found for '+esc(unprot.join(', '))+'.':'<span class="up">●</span> '+positions.length+' positions, every one has a stop and a target. No action needed.'}
function renderMilestone(m,eq){let prev=num((m.achieved||[]).slice(-1)[0]?.target)||num(m.starting_capital)||100,tgt=num(m.next_target),el=q('#ms');if(eq==null){el.innerHTML='<div class="muted">Equity unavailable.</div>';return}
let p=tgt?Math.max(0,Math.min(100,(eq-prev)/(tgt-prev)*100)):100;el.innerHTML='<div class="big">'+money(eq)+'</div><div class="muted">Stage '+money(prev)+' → '+(tgt?money(tgt):'complete')+'</div><div class="bar"><i style="width:'+p+'%"></i></div><div class="range-lbl"><span>'+p.toFixed(0)+'% of this stage</span><span>'+(tgt?money(tgt-eq)+' to go':'')+'</span></div>'+
'<div style="margin-top:10px" class="muted">Path: $100 → $200 → $1k → $3k → $5k → $10k → … → $1M</div>'}
function renderOrders(){let el=q('#t-orders');let soft=lots.filter(l=>l.status==='open'&&!l.broker_bracket).flatMap(l=>[{symbol:l.symbol,side:'sell',type:'worker_stop',stop_price:l.stop_price,qty:+Number(l.quantity).toFixed(4),status:'watching',time_in_force:'worker'},{symbol:l.symbol,side:'sell',type:'worker_target',limit_price:l.target_price,qty:+Number(l.quantity).toFixed(4),status:'watching',time_in_force:'worker'}]);let all=[...orders,...soft];if(!all.length){el.innerHTML='<div class="empty">No open orders.</div>';return}
el.innerHTML='<table><tr><th>Symbol</th><th>Side</th><th>Type</th><th>Qty</th><th>Price</th><th>Status</th><th>Duration</th></tr>'+all.map(o=>{let t=o.type||o.order_type,price=t==='limit'||t==='worker_target'?o.limit_price:/stop/.test(t)?o.stop_price:null,label=t==='worker_stop'?'Stop (worker)':t==='worker_target'?'Target (worker)':t==='limit'&&o.side==='sell'?'Target (limit)':/stop/.test(t)?'Stop':t;return '<tr><td><b>'+esc(o.symbol)+'</b></td><td class="'+(o.side==='buy'?'up':'down')+'">'+esc(o.side)+'</td><td>'+esc(label)+'</td><td>'+esc(o.qty)+'</td><td>'+money(price)+'</td><td>'+esc(o.status==='held'?'armed (OCO)':o.status)+'</td><td>'+esc(String(o.time_in_force||'').toUpperCase())+'</td></tr>'}).join('')+'</table>'}
function renderTrades(ts,L){let el=q('#t-trades');ts=[...(L||[]).filter(l=>l.confirmed||l.status==='closed').map(l=>({timestamp:l.closed_on||l.opened_on,symbol:l.symbol,quantity:+Number(l.quantity).toFixed(4),entry_price:l.entry_price,stop_price:l.stop_price,target_price:l.target_price,exit_price:l.exit_price,pnl:l.pnl})),...ts.filter(x=>!(L||[]).some(l=>l.symbol===x.symbol&&l.sleeve==='core'&&x.exit_price==null))];if(!ts.length){el.innerHTML='<div class="empty">No live trades recorded yet.</div>';return}
el.innerHTML='<table><tr><th>Date</th><th>Symbol</th><th>Qty</th><th>Entry</th><th>Stop</th><th>Target</th><th>Exit</th><th>Result</th></tr>'+ts.map(x=>'<tr><td>'+esc(when(x.timestamp,true))+'</td><td><b>'+esc(x.symbol)+'</b></td><td>'+esc(x.quantity)+'</td><td>'+money(x.entry_price)+'</td><td>'+money(x.stop_price)+'</td><td>'+money(x.target_price)+'</td><td>'+(x.exit_price!=null?money(x.exit_price):'<span class="muted">open</span>')+'</td><td class="'+cls(x.pnl)+'">'+(x.pnl==null?'—':signed(x.pnl))+'</td></tr>').join('')+'</table>'}
const EVT={alpaca_live_worker_cycle_completed:'Order decision',alpaca_live_worker_no_qualifying_signal:'No entry signal',alpaca_live_trade_closed:'Trade closed',risk_decision:'Risk check',alpaca_live_worker_rate_limited:'Broker busy — retried'};
function renderLog(ev){let el=q('#t-log');if(!ev.length){el.innerHTML='<div class="empty">No activity yet.</div>';return}
el.innerHTML='<table><tr><th>Time</th><th>Event</th><th>Detail</th></tr>'+ev.map(e=>{let p=e.payload||{},t=EVT[e.type]||String(e.type||'').replace(/^alpaca_live_(worker_)?/,'').replaceAll('_',' '),d=[p.symbol,p.submitted===true?'submitted':p.submitted===false?'not submitted':null,p.reason&&p.reason!=='pending_new'?String(p.reason).replaceAll('_',' '):null,p.approved===true?'approved':p.approved===false?'rejected':null].filter(Boolean).join(' · ');return '<tr><td class="muted">'+esc(when(e.timestamp))+'</td><td>'+esc(t)+'</td><td class="muted">'+esc(d||'—')+'</td></tr>'}).join('')+'</table>'}
function when(ts,dateOnly){if(!ts)return '';let s=String(ts);let d=new Date(/Z$|[+-]\d\d:\d\d$/.test(s)?s:s+'Z');return dateOnly?d.toLocaleDateString([],{month:'short',day:'numeric'}):d.toLocaleString([],{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})}
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===b));['orders','trades','log','scan','plan','review'].forEach(k=>q('#t-'+k).hidden=k!==b.dataset.t)});

/* ---------- strategy pipeline + nightly review ---------- */
async function loadPipeline(){try{let d=await api('/pipeline');q('#pipeTs').textContent='Scan → Backtest → Stress → Paper → Approval → Live → Review';
q('#pipe').innerHTML=(d.strategies||[]).map(s=>'<div class="prow2"><div class="pname"><b>'+esc(s.name)+'</b><small>'+esc(s.venue)+' · '+esc(s.detail)+'</small></div><div class="stages">'+
s.stages.map(g=>'<div class="stage '+g.status+'" title="'+esc(g.note)+'"><span class="stage-name">'+esc(g.name)+'</span><i></i></div>').join('')+'</div></div>').join('')}
catch(e){if(e.message!=='auth')q('#pipe').innerHTML='<div class="empty">Pipeline unavailable — retrying.</div>'}}
async function loadReview(){let el=q('#t-review');try{let r=await api('/review/latest');
el.innerHTML='<div class="rv"><div class="muted" style="font-family:var(--mono);font-size:12px">'+(r.preview?'PREVIEW · first stored review runs tonight after 8:05 PM ET':'REVIEW · '+esc(r.day))+' · '+(r.issues?'<span class="down">'+r.issues+' issue'+(r.issues>1?'s':'')+'</span>':'<span class="up">all clear</span>')+'</div>'+
(r.accounts||[]).map(a=>'<div class="rv-card"><div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap"><b>'+esc(a.label)+'</b><span style="font-family:var(--mono)">'+money(a.equity)+(a.change!=null?' <span class="'+cls(a.change)+'">'+pct(a.change*100)+'</span>':'')+'</span></div>'+
'<div class="muted" style="font-size:12px;margin:4px 0 6px">'+a.trades.length+' trade'+(a.trades.length==1?'':'s')+' in 24h · '+a.open_positions.length+' open · realized today '+signed(a.realized_today)+'</div>'+
(a.trades.map(t=>'<div class="flag">'+esc(String(t.event).replace(/^(allocator|binance)_/,'').replace('_',' '))+' '+esc(t.symbol||'')+(t.reason?' · '+esc(t.reason):'')+(t.usd?' · '+money(t.usd):'')+'</div>').join(''))+
(a.flags.length?a.flags.map(f=>'<div class="flag '+f.level+'">'+(f.level==='alert'?'▲ ':f.level==='warn'?'● ':'✓ ')+esc(f.text)+'</div>').join(''):'<div class="flag info">✓ No issues</div>')+'</div>').join('')+'</div>'}
catch(e){if(e.message!=='auth')el.innerHTML='<div class="empty">Review unavailable — retrying.</div>'}}

/* ---------- watchlist ---------- */
async function loadTicker(){try{let d=await api('/terminal/ticker');let all=d.items||[];ticker=all.filter(x=>!String(x.symbol).includes('/'));q('#wlSrc').textContent=d.source||'';drawWatch();drawTape(all)}catch(e){if(e.message!=='auth')q('#wl').innerHTML='<div class="empty">Prices unavailable — retrying.</div>'}}
function drawWatch(){let held=positions.map(p=>p.symbol);let rank=s=>{let h=held.indexOf(s);if(h>=0)return h;let i=PIN.indexOf(s);return i<0?99:50+i};held.forEach(h=>{if(!ticker.find(x=>x.symbol===h)){let p=positions.find(x=>x.symbol===h);ticker.push({symbol:h,price:num(p.current_price),change_pct:num(p.change_today)!=null?num(p.change_today)*100:null})}});let items=[...ticker].sort((a,b)=>rank(a.symbol)-rank(b.symbol)||String(a.symbol).localeCompare(b.symbol));
if(!items.find(x=>x.symbol===sym))items.unshift({symbol:sym});
q('#wl').innerHTML=items.map(x=>'<button class="wrow'+(x.symbol===sym?' on':'')+'" data-s="'+esc(x.symbol)+'"><span><b>'+esc(x.symbol)+'</b>'+(held.includes(x.symbol)?'<small class="up">Holding</small>':PIN.includes(x.symbol)?'<small>'+(x.symbol==='QQQ'?'Trend signal':'Market')+'</small>':'')+'</span><span>'+money(x.price)+'</span><span class="'+cls(x.change_pct)+'">'+pct(x.change_pct)+'</span></button>').join('');
document.querySelectorAll('.wrow').forEach(b=>b.onclick=()=>pick2(b.dataset.s));let t=ticker.find(x=>x.symbol===sym);if(t){q('#cChg').className='chg '+cls(t.change_pct);q('#cChg').textContent=pct(t.change_pct)}}

/* ---------- chart (canvas, device-pixel sharp) ---------- */
document.querySelectorAll('.tf').forEach(b=>b.onclick=()=>{tf=b.dataset.tf;document.querySelectorAll('.tf').forEach(x=>x.classList.toggle('on',x===b));hover=null;loadChart()});
async function loadChart(){let s=sym,f=tf;q('#cSym').textContent=s;try{let d=await api('/terminal/market?symbol='+encodeURIComponent(s)+'&timeframe='+f);if(s!==sym||f!==tf)return;bars=(d.bars||[]).map(b=>({t:new Date(b.timestamp),o:+b.open,h:+b.high,l:+b.low,c:+b.close,v:+b.volume||0}));quote=d.quote||{};
let last=num(quote.last)??(bars.length?bars[bars.length-1].c:null);q('#cPx').textContent=money(last);let age=num(quote.age_seconds);feedLabel();
q('#cMsg').style.display=bars.length?'none':'flex';q('#cMsg').textContent='No candles available';drawWatch();draw()}catch(e){if(e.message==='auth')return;q('#cMsg').style.display='flex';q('#cMsg').textContent='Market data unavailable — retrying';bars=[];draw()}}
const cv=q('#cv'),ctx=cv.getContext('2d');
function draw(){let dpr=window.devicePixelRatio||1,W=cv.clientWidth,H=cv.clientHeight;if(!W||!H)return;cv.width=Math.round(W*dpr);cv.height=Math.round(H*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);if(!bars.length)return;
let axisW=70,axisH=24,pw=W-axisW,ph=H-axisH,volH=Math.round(ph*.16),priceH=ph-volH-8;
let p=positions.find(x=>x.symbol===sym),lv=p?levels(sym):{},lines=[];if(p){lines.push(['Entry',num(p.avg_entry_price),'#f0b90b']);if(lv.stop!=null)lines.push(['Stop',lv.stop,'#f6465d']);if(lv.target!=null)lines.push(['Target',lv.target,'#0ecb81'])}
let lo=Math.min(...bars.map(b=>b.l)),hi=Math.max(...bars.map(b=>b.h));lines.forEach(l=>{if(l[0]==='Entry'&&l[1]!=null){lo=Math.min(lo,l[1]);hi=Math.max(hi,l[1])}});let pad=(hi-lo)*.06||1;lo-=pad;hi+=pad;
let Y=v=>8+(hi-v)/(hi-lo)*(priceH-8),n=bars.length,step=pw/n,bw=Math.max(1,Math.min(14,step*.7)),X=i=>i*step+step/2,vmax=Math.max(...bars.map(b=>b.v))||1;
ctx.font='11px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif';ctx.textBaseline='middle';
/* grid + price axis */let ticks=6,raw=(hi-lo)/ticks,mag=Math.pow(10,Math.floor(Math.log10(raw))),stepP=[1,2,2.5,5,10].map(k=>k*mag).find(k=>k>=raw)||raw;ctx.strokeStyle='#1e252d';ctx.lineWidth=1;ctx.fillStyle='#8b949e';
for(let v=Math.ceil(lo/stepP)*stepP;v<=hi;v+=stepP){let y=Math.round(Y(v))+.5;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(pw,y);ctx.stroke();ctx.fillText(v.toFixed(2),pw+8,y)}
/* time axis */let labelEvery=Math.max(1,Math.ceil(n/Math.max(2,Math.floor(pw/90))));ctx.textAlign='center';for(let i=Math.ceil(labelEvery/2);i<n;i+=labelEvery){let x=Math.round(X(i))+.5;if(x<30||x>pw-30)continue;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,ph);ctx.stroke();let t=bars[i].t;ctx.fillText(tf==='1Day'?t.toLocaleDateString([],{month:'short',day:'numeric'}):t.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'}),x,ph+12)}ctx.textAlign='left';
/* volume */bars.forEach((b,i)=>{let h=b.v/vmax*volH;ctx.fillStyle=b.c>=b.o?'rgba(14,203,129,.35)':'rgba(246,70,93,.35)';ctx.fillRect(Math.round(X(i)-bw/2),ph-h,Math.max(1,Math.round(bw)),h)});
/* candles */bars.forEach((b,i)=>{let up=b.c>=b.o,col=up?'#0ecb81':'#f6465d',x=Math.round(X(i))+.5;ctx.strokeStyle=col;ctx.beginPath();ctx.moveTo(x,Math.round(Y(b.h)));ctx.lineTo(x,Math.round(Y(b.l)));ctx.stroke();let top=Math.round(Y(Math.max(b.o,b.c))),bot=Math.round(Y(Math.min(b.o,b.c)));ctx.fillStyle=col;ctx.fillRect(Math.round(X(i)-bw/2),top,Math.max(1,Math.round(bw)),Math.max(1,bot-top))});
/* position lines */let tag=(v,col,text)=>{let y=Math.round(Y(v))+.5;ctx.fillStyle=col;ctx.fillRect(pw+1,y-9,axisW-2,18);ctx.fillStyle='#0b0e11';ctx.font='600 11px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif';ctx.fillText(text,pw+6,y);ctx.font='11px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif'};
lines.forEach(([name,v,col])=>{if(v==null)return;if(v>hi||v<lo){let up=v>hi,y=up?18:priceH-10;ctx.fillStyle=col;ctx.fillText((up?'▲ ':'▼ ')+name+' '+v.toFixed(2)+(up?' (above chart)':' (below chart)'),8,y);return}let y=Math.round(Y(v))+.5;ctx.setLineDash([6,4]);ctx.strokeStyle=col;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(pw,y);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=col;ctx.fillText(name,6,y-9);tag(v,col,v.toFixed(2))});
/* last price */let last=bars[n-1].c,ly=Math.round(Y(last))+.5,lc=last>=bars[n-1].o?'#0ecb81':'#f6465d';ctx.strokeStyle=lc;ctx.setLineDash([2,3]);ctx.beginPath();ctx.moveTo(0,ly);ctx.lineTo(pw,ly);ctx.stroke();ctx.setLineDash([]);tag(last,lc,last.toFixed(2));
/* crosshair */if(hover!=null&&bars[hover.i]){let x=Math.round(X(hover.i))+.5,y=Math.max(8,Math.min(priceH,hover.y))+.5;ctx.strokeStyle='#5e6673';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,ph);ctx.moveTo(0,y);ctx.lineTo(pw,y);ctx.stroke();ctx.setLineDash([]);let v=hi-(y-8)/(priceH-8)*(hi-lo);tag(v,'#5e6673',v.toFixed(2));ohlc(hover.i)}else ohlc(n-1)}
function ohlc(i){let b=bars[i];if(!b)return;let ch=b.c-b.o,t=tf==='1Day'?b.t.toLocaleDateString():b.t.toLocaleString([],{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});q('#ohlc').innerHTML='<b>'+esc(t)+'</b>O <b>'+b.o.toFixed(2)+'</b>H <b>'+b.h.toFixed(2)+'</b>L <b>'+b.l.toFixed(2)+'</b>C <b class="'+(ch>=0?'up':'down')+'">'+b.c.toFixed(2)+'</b>Vol <b>'+Math.round(b.v).toLocaleString('en-US')+'</b>'}
function pick(e){if(!bars.length)return;let r=cv.getBoundingClientRect(),pw=r.width-70,x=e.clientX-r.left;if(x>pw){hover=null;draw();return}hover={i:Math.max(0,Math.min(bars.length-1,Math.floor(x/(pw/bars.length)))),y:e.clientY-r.top};draw()}
cv.addEventListener('pointermove',pick);cv.addEventListener('pointerdown',pick);cv.addEventListener('pointerleave',()=>{hover=null;draw()});
new ResizeObserver(()=>draw()).observe(cv);


function drawTape(items){q('#tape').innerHTML=items.map(x=>'<button class="tk" data-s="'+esc(x.symbol)+'"><b>'+esc(x.symbol)+'</b><span>'+money(x.price)+'</span><span class="'+cls(x.change_pct)+'">'+pct(x.change_pct)+'</span></button>').join('')||'<span class="tk muted">Markets unavailable</span>';
document.querySelectorAll('.tk[data-s]').forEach(b=>{if(b.dataset.s.includes('/'))return;b.onclick=()=>{sym=b.dataset.s;hover=null;drawWatch();loadChart();window.scrollTo({top:0,behavior:'smooth'})}})}
let deepCache={at:0,rh:null,bn:null};
async function loadAccounts(){const get=u=>api(u).catch(()=>null);let [alp,rh,bn,et]=await Promise.all([get('/brokers/alpaca/live-portfolio'),get('/brokers/robinhood/status'),get('/brokers/binance-us/status'),get('/brokers/etrade/status')]);
/* status endpoints only say a key is stored; run the read-only broker checks (at most every 10 min) to prove the link works */
if(Date.now()-deepCache.at>600000){deepCache.at=Date.now();deepCache.rh=rh?.application_authorized?await get('/brokers/robinhood/readiness'):null;deepCache.bn=bn?.credentials_saved?await get('/brokers/binance-us/readiness'):null}
let rhOk=rh?.read_only_ready||deepCache.rh?.read_only_ready,bnOk=deepCache.bn?.read_only_ready;
let row=(name,state,detail,link)=>'<div class="acct"><div><span class="dot '+state+'"></span><b>'+name+'</b><small>'+esc(detail)+'</small></div>'+(link||'')+'</div>';
let h='';h+=row('Alpaca',alp?'on':'off',alp?'Live account · trading active ('+money(alp.balances?.equity)+')':'Not reachable');
h+=row('Robinhood Agentic',rhOk?'on':rh?.application_authorized?'warn':'off',rhOk?'Connected · read-only':rh?.application_authorized?'Linked, but the broker check failed — reconnect':'Not linked',rhOk?'':'<a href="/brokers/robinhood/connect-manual" target="_blank">'+(rh?.application_authorized?'Reconnect':'Connect')+'</a>');
let usd=(deepCache.bn?.balances||[]).find(b=>b.asset==='USD');
h+=row('Binance.US',bnOk?'on':bn?.credentials_saved?'warn':'off',bnOk?'Connected · read-only'+(usd?' ('+money(Number(usd.free||0)+Number(usd.locked||0))+')':''):bn?.credentials_saved?'Key saved, but the broker check failed — re-enter key':'No API key saved','<a href="/brokers/binance-us/connect">'+(bnOk?'Manage':'Connect')+'</a>');
h+=row('E*TRADE',et?.application_authorized_today?'on':et?.api_key_configured?'warn':'off',et?.application_authorized_today?'Connected today · read-only':et?.api_key_configured?'Sign-in needed today (E*TRADE expires daily)':'API key not set up yet',et?.api_key_configured?'<a href="/brokers/etrade/connect">'+(et?.application_authorized_today?'Reconnect':'Connect')+'</a>':'');
q('#accts').innerHTML=h}

const RULE_TXT={trend:'Trend start',pullback:'Dip in uptrend',breakout:'20-day breakout'};
async function loadScanner(){let el=q('#t-scan');try{let d=await api('/scanner/signals'),sg=d.signals||[],sc=d.scoreboard||[];
let st=x=>x.status==='closed'?'<span class="'+cls(x.result_pct)+'">'+pct(x.result_pct*100)+' · '+esc(String(x.exit_reason||'').replaceAll('_',' '))+'</span>':x.status==='open'?'<span class="'+cls(x.mark_pct)+'">open '+pct((x.mark_pct||0)*100)+'</span>':'<span class="muted">waiting for next open</span>';
let h='<div class="empty" style="padding:12px 14px">Watch-only: scans ~140 US stocks/ETFs + BTC, ETH, SOL after each close and tracks what every signal would have done. Nothing here places orders. Rules: '+Object.entries(d.rules||{}).map(([k,r])=>'<b>'+esc(RULE_TXT[k]||k)+'</b> (stop −'+Math.round(r.stop*100)+'%, target +'+Math.round(r.target*100)+'%)').join(' · ')+'</div>';
h+='<table><tr><th>Scoreboard (closed signals)</th><th>Market group</th><th>Signals</th><th>Win rate</th><th>Avg result</th></tr>'+(sc.length?sc.map(r=>'<tr><td>'+esc(RULE_TXT[r.rule]||r.rule)+'</td><td>'+esc(r.group)+'</td><td>'+r.closed+'</td><td>'+Math.round(r.win_rate*100)+'%</td><td class="'+cls(r.avg_result)+'">'+pct(r.avg_result*100)+'</td></tr>').join(''):'<tr><td colspan="5" class="muted">No closed signals yet — results build up over the coming weeks.</td></tr>')+'</table>';
h+='<table><tr><th>Date</th><th>Symbol</th><th>Signal</th><th>Group</th><th>Price</th><th>6-mo momentum</th><th>Outcome</th></tr>'+(sg.length?sg.slice(0,150).map(x=>'<tr><td class="muted">'+esc(x.signal_date)+'</td><td><b>'+esc(x.symbol)+'</b></td><td>'+esc(RULE_TXT[x.rule]||x.rule)+'</td><td class="muted">'+esc(x.group)+'</td><td>'+money(x.signal_close)+'</td><td class="'+cls(x.momentum_6m)+'">'+(x.momentum_6m==null?'—':pct(x.momentum_6m*100))+'</td><td>'+st(x)+'</td></tr>').join(''):'<tr><td colspan="7" class="muted">First scan runs after today\'s close (4:30 PM ET).</td></tr>')+'</table>';
el.innerHTML=h}catch(e){if(e.message!=='auth')el.innerHTML='<div class="empty">Scanner not running yet.</div>'}}

/* ---------- milestone plan: block-bootstrap of Stage Runner's 2011-2026 monthly returns ---------- */
const SR_MONTHLY=[0.09141, -0.02352, 0.08577, -0.04307, -0.07011, 0.04427, -0.31655, -0.19254, -0.02842, -0.10145, -0.0283, 0.26857, 0.20139, 0.14088, -0.04305, -0.20447, 0.097, 0.0228, 0.16093, 0.0192, -0.15633, -0.07004, -0.01932, 0.07649, 0.00592, 0.08741, 0.06939, 0.10707, -0.08023, 0.20339, -0.01693, 0.14911, 0.14696, 0.10336, 0.0679, -0.06357, 0.15402, -0.08366, -0.02034, 0.13505, 0.09458, 0.03049, 0.15468, -0.00664, 0.08509, 0.14738, -0.0751, -0.06947, 0.22739, -0.07457, 0.05156, 0.06353, -0.07649, 0.1335, -0.38963, -0.14116, 0.37229, 0.01312, -0.05766, -0.33378, 0.0, 0.06017, -0.09561, 0.12839, -0.07828, 0.22519, 0.02991, 0.05801, -0.04612, 0.01101, 0.02597, 0.12765, 0.13389, 0.05641, 0.08072, 0.11434, -0.07487, 0.12564, 0.0504, -0.01057, 0.13742, 0.05502, 0.01182, 0.29464, -0.18216, -0.13421, -0.00424, 0.16998, 0.02183, 0.07564, 0.17603, -0.01604, -0.32586, -0.20132, -0.25038, 0.0, 0.03101, 0.1105, 0.16643, -0.24013, 0.22999, 0.062, -0.0779, 0.01885, 0.12429, 0.13615, 0.11373, 0.08192, -0.0376, -0.35746, 0.24683, 0.18633, 0.17436, 0.22253, 0.35365, -0.18877, -0.10275, 0.34542, 0.15049, 0.01821, -0.01382, 0.02287, 0.17971, -0.04709, 0.19407, 0.08359, 0.09403, -0.1667, 0.24556, 0.05369, 0.01737, -0.35696, -0.25038, -0.05722, -0.20488, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.02409, -0.03405, 0.28444, -0.00035, 0.1291, 0.18359, 0.10512, -0.06334, -0.15774, -0.07973, 0.33832, 0.16076, 0.00883, 0.14666, 0.02356, -0.14327, 0.18563, 0.18507, -0.11636, 0.00483, 0.05995, -0.04194, 0.15032, -0.00622, 0.04537, -0.09429, -0.23293, -0.19778, 0.04942, 0.18903, 0.06277, 0.01304, 0.16743, 0.12882, -0.06546, -0.03186, 0.02428, -0.08296, -0.15693, 0.52447, 0.29267, -0.03989, -0.20222, 0.11297, 0.07326];
const PLAN_M=[200,1000,3000,5000,10000,50000,100000,300000,500000,1000000];
let planEquity=null;
function rng(seed){return()=>{seed=(seed*1664525+1013904223)%4294967296;return seed/4294967296}}
function runPlan(){let start=planEquity||100,amt=Math.max(0,+q('#pAmt').value||0),f=+q('#pFreq').value,dep=f?amt*f/12:0,N=2000,H=240,r=rng(42),hits=PLAN_M.map(()=>[]),depAt=PLAN_M.map(()=>[]);
for(let n=0;n<N;n++){let e=start,t=0,got=0;while(t<H&&got<PLAN_M.length){let k=Math.floor(r()*(SR_MONTHLY.length-3));for(let j=0;j<3&&t<H;j++){e=e*(1+SR_MONTHLY[k+j])+dep;t++;while(got<PLAN_M.length&&e>=PLAN_M[got]){hits[got].push(t);depAt[got].push(dep*t);got++}}}}
const yrs=m=>m<12?m+' mo':(m/12).toFixed(1)+' yrs',med=a=>{a=[...a].sort((x,y)=>x-y);return a[Math.floor(a.length/2)]},pc=(a,p)=>{a=[...a].sort((x,y)=>x-y);return a[Math.floor(a.length*p)]};
q('#pNote').textContent='Starting from '+money(start)+(dep?' · adding '+money(dep)+'/month':'')+' · based on Stage Runner\'s 2011–2026 history, 2,000 simulated paths';
q('#pOut').innerHTML='<table><tr><th>Account reaches</th><th>Typical time</th><th>Likely range</th><th>Chance within 20 yrs</th><th>Your deposits by then</th></tr>'+PLAN_M.map((m,i)=>{let h=hits[i];if(!h.length)return '<tr><td><b>'+money(m)+'</b></td><td colspan="4" class="muted">Not reached in 20 years</td></tr>';return '<tr><td><b>'+money(m)+'</b></td><td>'+yrs(med(h))+'</td><td class="muted">'+yrs(pc(h,.25))+' – '+yrs(pc(h,.75))+'</td><td>'+Math.round(100*h.length/N)+'%</td><td class="muted">'+(dep?money(med(depAt[i])):'—')+'</td></tr>'}).join('')+'</table><div class="empty">Past results don\'t guarantee future ones: 2011–2026 was a strong period for the Nasdaq, and TQQQ has had drops of up to 82%. Balances include deposits; the stage cap is raised as the account grows.</div>'}
q('#pAmt').oninput=runPlan;q('#pFreq').onchange=runPlan;
async function loadObserver(){try{let o=await api('/live/observer');q('#observer').textContent='Account observer: '+(o.healthy?'active, updated '+Math.round(o.age_seconds)+'s ago':o.observed?'needs attention':'not running')}catch(e){}}
loadState();loadAccount();loadTicker();loadChart();loadObserver();loadAccounts();loadPipeline();setInterval(loadPipeline,120000);loadReview();setInterval(loadReview,600000);setInterval(loadAccounts,60000);loadScanner();setInterval(loadScanner,300000);runPlan();
setInterval(loadState,10000);setInterval(loadAccount,10000);setInterval(loadTicker,30000);setInterval(()=>{if(!hover)loadChart()},tf==='1Day'?60000:15000);setInterval(loadObserver,30000);
</script></body></html>'''
