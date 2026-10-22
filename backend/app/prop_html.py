PROP_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Prop Challenge · Veloikos</title>
<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#0a0d14"><link rel="apple-touch-icon" href="/static/icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<style>
:root{--bg:#0a0d14;--p1:#10141e;--p2:#151a26;--p3:#1b2130;--line:#222a3a;--ink:#e7ebf3;--sub:#8590a6;--dim:#5b6479;--up:#22c55e;--down:#ef4444;--acc:#3b82f6;--warn:#f59e0b;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);font:14px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
button{font:inherit;color:inherit;cursor:pointer;background:none;border:0}a{color:var(--acc);text-decoration:none}
.up{color:var(--up)}.down{color:var(--down)}.muted{color:var(--sub)}.mono{font-family:var(--mono)}
/* top bar */
.top{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:10px;padding:max(8px,env(safe-area-inset-top)) 12px 8px;background:#0c1018;border-bottom:1px solid var(--line)}
.brand{font:800 13px var(--mono);letter-spacing:.14em}.brand span{color:var(--acc)}
.acct{display:flex;align-items:center;gap:8px;min-width:0;padding:5px 10px;border:1px solid var(--line);border-radius:6px;background:var(--p1)}
.acct b{font:600 12px var(--mono);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:46vw}
.acct select{min-width:0;max-width:52vw;background:transparent;color:var(--ink);border:0;font:600 12px var(--mono);outline:0}
.acct select option{background:var(--p1)}
.pill{font:700 10px var(--mono);letter-spacing:.08em;padding:3px 7px;border-radius:4px;background:var(--p3);color:var(--sub);white-space:nowrap}
.pill.live{background:rgba(34,197,94,.16);color:var(--up)}.pill.dry{background:rgba(245,158,11,.16);color:var(--warn)}.pill.off{background:rgba(239,68,68,.16);color:var(--down)}
.beat{margin-left:auto;display:flex;align-items:center;gap:6px;font:11px var(--mono);color:var(--sub);white-space:nowrap}
.dot{width:7px;height:7px;border-radius:50%;background:var(--dim)}.dot.on{background:var(--up);box-shadow:0 0 0 3px rgba(34,197,94,.18)}
.icon{width:32px;height:32px;display:grid;place-items:center;border-radius:6px;color:var(--sub)}.icon:hover{background:var(--p2)}
/* metrics strip */
.strip{display:flex;gap:1px;overflow-x:auto;background:var(--line);border-bottom:1px solid var(--line);scrollbar-width:none}.strip::-webkit-scrollbar{display:none}
.m{flex:1 0 auto;min-width:118px;padding:9px 12px;background:var(--p1)}
.m small{display:block;font:600 10px var(--mono);letter-spacing:.07em;text-transform:uppercase;color:var(--dim)}
.m b{display:block;margin-top:3px;font:700 15px var(--mono);white-space:nowrap}
.m i{display:block;height:3px;margin-top:6px;border-radius:2px;background:var(--p3);overflow:hidden}.m i em{display:block;height:100%;background:var(--acc)}
/* banner */
.banner{display:none;gap:10px;align-items:flex-start;padding:10px 12px;background:rgba(245,158,11,.08);border-bottom:1px solid rgba(245,158,11,.25);font-size:13px}
.banner.show{display:flex}.banner b{color:var(--warn)}
/* layout */
.grid{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:1px;background:var(--line)}
.pane{background:var(--bg);min-width:0}
.ph{display:flex;align-items:center;gap:10px;padding:8px 12px;border-bottom:1px solid var(--line);background:var(--p1)}
.sym{font:800 15px var(--mono)}.tf{font:600 11px var(--mono);padding:2px 6px;border-radius:4px;background:var(--p3);color:var(--sub)}
.last{margin-left:auto;text-align:right;font:700 15px var(--mono)}.last small{display:block;font-size:11px;font-weight:600}
.chart{position:relative;height:min(52vh,460px);min-height:260px}canvas{display:block;width:100%;height:100%;touch-action:pan-y}
.ohlc{position:absolute;left:10px;top:6px;font:11px var(--mono);color:var(--sub);pointer-events:none}
.msg{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;text-align:center;padding:24px;color:var(--sub)}
/* side panel */
.side{display:flex;flex-direction:column}
.box{padding:12px;border-bottom:1px solid var(--line)}
.lbl{font:600 10px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--dim)}
.posrow{display:flex;align-items:center;gap:10px;margin-top:10px}
.sidepill{font:800 15px var(--mono);padding:6px 12px;border-radius:5px;background:var(--p3);color:var(--sub)}
.sidepill.long{background:rgba(34,197,94,.16);color:var(--up)}.sidepill.short{background:rgba(239,68,68,.16);color:var(--down)}
.kv{display:grid;grid-template-columns:1fr auto;gap:6px 10px;margin-top:10px;font-size:13px}.kv span{color:var(--sub)}.kv b{font:600 13px var(--mono);text-align:right}
.big{font:800 22px var(--mono)}
.botstate{display:flex;align-items:center;gap:8px;margin-top:8px;font-weight:600}
.rule{margin-top:10px}.rule .row{display:flex;justify-content:space-between;font:12px var(--mono);color:var(--sub)}
.bar{height:6px;border-radius:3px;background:var(--p3);margin-top:5px;overflow:hidden}.bar em{display:block;height:100%}
/* bottom tabs */
.tabs{display:flex;gap:2px;padding:0 8px;background:var(--p1);border-top:1px solid var(--line);border-bottom:1px solid var(--line);overflow-x:auto}
.tab{padding:10px 12px;font:600 12px var(--mono);color:var(--sub);border-bottom:2px solid transparent;white-space:nowrap}
.tab.on{color:var(--ink);border-color:var(--acc)}.tab sup{font-size:10px;color:var(--acc);margin-left:3px}
.tbl{width:100%;border-collapse:collapse;font:12px var(--mono)}.tbl th{position:sticky;top:0;text-align:left;font-weight:600;color:var(--dim);padding:8px 12px;background:var(--bg);border-bottom:1px solid var(--line);text-transform:uppercase;font-size:10px;letter-spacing:.06em}
.tbl td{padding:9px 12px;border-bottom:1px solid #161c28;white-space:nowrap}.tbl td.t{white-space:normal;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:13px}
.k{font:700 10px var(--mono);text-transform:uppercase;padding:2px 6px;border-radius:3px;background:var(--p3)}
.k.buy{color:var(--up);background:rgba(34,197,94,.12)}.k.sell{color:var(--down);background:rgba(239,68,68,.12)}.k.halt,.k.error{color:var(--warn)}.k.pass{color:var(--acc)}
.empty{padding:22px 12px;color:var(--sub);text-align:center}
.panel{max-height:46vh;overflow:auto}
/* settings sheet */
.sheet{position:fixed;inset:0;z-index:40;display:none;background:rgba(0,0,0,.6)}.sheet.show{display:flex;align-items:flex-end;justify-content:center}
.sheet>div{width:100%;max-width:520px;max-height:85vh;overflow:auto;background:var(--p1);border:1px solid var(--line);border-radius:12px 12px 0 0;padding:16px 16px max(16px,env(safe-area-inset-bottom))}
.sheet h3{margin:0 0 6px;font-size:16px}.sheet p{color:var(--sub);font-size:13px}
.btn{background:var(--acc);border-radius:6px;padding:10px 14px;font-weight:700;color:#fff}.btn.ghost{background:var(--p3);color:var(--ink)}
code{display:block;margin:10px 0;padding:10px;border-radius:6px;background:#05070b;font:13px var(--mono);word-break:break-all;color:var(--warn)}
@media(max-width:820px){.grid{grid-template-columns:1fr}.side{display:grid;grid-template-columns:1fr 1fr}.side .box.full{grid-column:1/-1}.chart{height:44vh}}
@media(max-width:480px){.side{grid-template-columns:1fr}.brand{display:none}}
</style></head><body>
<header class="top">
  <a href="/dashboard" class="icon" aria-label="Main dashboard">&#8592;</a>
  <span class="brand">VELO<span>IKOS</span></span>
  <div class="acct"><span id="mode" class="pill">…</span><b id="acct">Prop Challenge</b><select id="acctSel" hidden aria-label="Account"></select></div>
  <span class="beat"><span id="dot" class="dot"></span><span id="beat"></span></span>
  <button id="gear" class="icon" type="button" aria-label="Settings">&#9881;</button>
</header>
<nav class="strip">
  <div class="m"><small>Balance</small><b id="mBal">—</b></div>
  <div class="m"><small>Realized P&amp;L</small><b id="mR">—</b></div>
  <div class="m"><small>Unrealized</small><b id="mU">—</b></div>
  <div class="m"><small>Profit target</small><b id="mT">—</b><i><em id="mTb" style="width:0"></em></i></div>
  <div class="m"><small>Trailing loss limit</small><b id="mL">—</b></div>
  <div class="m"><small>Daily loss used</small><b id="mD">—</b><i><em id="mDb" style="width:0;background:var(--down)"></em></i></div>
</nav>
<div id="banner" class="banner"><span>&#9888;</span><div id="bannerTxt"></div></div>
<main class="grid">
  <section class="pane">
    <div class="ph"><span class="sym" id="sym">MNQ</span><span class="tf">5m</span><span class="muted" style="font-size:12px">Micro Nasdaq-100</span>
      <div class="last"><span id="lastPx">—</span><small id="chg" class="muted">—</small></div></div>
    <div class="chart"><canvas id="cv"></canvas><div id="ohlc" class="ohlc"></div><div id="cmsg" class="msg">The chart fills in when the bot reports today's 5-minute bars (weekdays from 9:30 AM ET).</div></div>
  </section>
  <aside class="pane side">
    <div class="box"><span class="lbl">Position</span>
      <div class="posrow"><span id="sidePill" class="sidepill">FLAT</span><span id="pPnl" class="big muted">$0.00</span></div>
      <div class="kv"><span>Contracts</span><b id="pQty">0</b><span>Avg price</span><b id="pAvg">—</b><span>Last price</span><b id="pLast">—</b></div></div>
    <div class="box"><span class="lbl">Bot</span>
      <div class="botstate"><span id="dot2" class="dot"></span><span id="botTxt">Waiting for the bot</span></div>
      <div class="kv"><span>Strategy</span><b>NOISE · MNQ</b><span>Schedule</span><b>Mon–Fri 9:20–4:05 ET</b><span>Flat by</span><b>3:55 PM ET</b></div>
      <p id="guard" class="muted" style="font-size:12px;margin:10px 0 0"></p></div>
    <div class="box full"><span class="lbl" id="rulesHd">Challenge rules · 50K</span>
      <div class="rule"><div class="row"><span>Profit target</span><span id="rT">$0 / $3,000</span></div><div class="bar"><em id="rTb" style="width:0;background:var(--up)"></em></div></div>
      <div class="rule"><div class="row"><span>Room above loss limit</span><span id="rL">—</span></div><div class="bar"><em id="rLb" style="width:0;background:var(--acc)"></em></div></div>
      <div class="rule"><div class="row"><span id="rDl">Daily loss (bot stop)</span><span id="rD">$0</span></div><div class="bar"><em id="rDb" style="width:0;background:var(--down)"></em></div></div></div>
  </aside>
</main>
<div class="tabs" role="tablist">
  <button class="tab on" data-t="pos" type="button">Positions</button>
  <button class="tab" data-t="trades" type="button">Trades<sup id="nT"></sup></button>
  <button class="tab" data-t="act" type="button">Activity<sup id="nA"></sup></button>
  <button class="tab" data-t="stats" type="button">Stats</button>
</div>
<section class="panel" id="panel"></section>
<div id="sheet" class="sheet"><div>
  <h3>Connect your Mac</h3>
  <p>The bot places orders from your Mac (Topstep rule) and reports here. Pair once; a new code disconnects the old one.</p>
  <button id="pairBtn" class="btn" type="button">Get pairing code</button> <button id="closeSheet" class="btn ghost" type="button">Close</button>
  <div id="pairOut"></div>
  <h3 style="margin-top:18px">Go live</h3>
  <p>Real orders are switched on from the Mac only. In Terminal run <span class="mono">bash ~/p100-prop/go-live.sh</span> and type YES. <span class="mono">go-live.sh off</span> switches back to dry run.</p>
</div></div>
<script>
const q=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num=v=>{let n=Number(v);return v!=null&&v!==''&&Number.isFinite(n)?n:null};
const usd=v=>num(v)==null?'—':num(v).toLocaleString('en-US',{style:'currency',currency:'USD'});
const sgn=v=>num(v)==null?'—':(num(v)>=0?'+':'−')+Math.abs(num(v)).toLocaleString('en-US',{style:'currency',currency:'USD'});
const cls=v=>num(v)==null||num(v)===0?'muted':num(v)>0?'up':'down';
const tm=t=>new Date(t).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});
const pct=(a,b)=>Math.max(0,Math.min(100,b?a/b*100:0));
let S=null,tab='pos',hover=null,sel=(()=>{try{return localStorage.getItem('propAcct')||''}catch(e){return ''}})();
function view(){const L=S.latest||{},A=L.accounts||[];if(!A.length)return L;let a=A.find(x=>x.account===sel)||A[0];sel=a.account;
  return Object.assign({},L,{account:a.account,orders:a.orders,contract:a.contract||L.contract,status:a.status||{}})}
function myEvents(){const A=(S.latest||{}).accounts||[];return A.length>1?(S.events||[]).filter(e=>!e.account||e.account===sel):(S.events||[])}
function nextStart(){const f=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',weekday:'short',hour:'numeric',minute:'numeric',hour12:false});
  const p=Object.fromEntries(f.formatToParts(new Date()).map(x=>[x.type,x.value]));const days=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];let d=days.indexOf(p.weekday),mins=(+p.hour%24)*60+(+p.minute);
  if(d>=1&&d<=5&&mins<9*60+20)return 'today at 9:20 AM ET';if(d>=1&&d<=5&&mins<16*60+5)return 'now (it should be running)';
  let n=d;do{n=(n+1)%7}while(n===0||n===6);return (n===(d+1)%7?'tomorrow':days[n])+' at 9:20 AM ET'}
async function load(){try{let r=await fetch('/prop/state',{credentials:'same-origin'});if(r.status===401||r.redirected){location.href='/login';return}S=await r.json();render()}catch(e){q('#beat').textContent='reconnecting…'}}
function render(){const L=view(),st=L.status||{},cs=st.state||{},A=(S.latest||{}).accounts||[];
  const TARGET=num(st.target)??num(cs.target),DAILY=num(cs.daily_stop)||800,MLL=num(cs.mll)||2000,funded=st.kind?st.kind!=='combine':cs.kind?cs.kind!=='combine':false;
  const so=q('#acctSel');if(A.length>1){so.hidden=false;q('#acct').hidden=true;const opts=A.map(a=>'<option'+(a.account===sel?' selected':'')+'>'+esc(a.account)+'</option>').join('');if(so.dataset.o!==opts){so.innerHTML=opts;so.dataset.o=opts}}else{so.hidden=true;q('#acct').hidden=false}
  q('#rulesHd').textContent=(funded?'Funded account rules · ':'Challenge rules · ')+(num(st.size_k)||50)+'K';
  const start=num(cs.start_balance)||50000,bal=num(st.balance),pos=num(st.position)||0,upl=pos?(num(st.open_pnl)||0):0,eq=bal==null?null:bal+upl;
  const dayStart=num(cs.day_start_balance),floor=num(st.floor)??num(cs.floor),real=bal!=null&&dayStart!=null?bal-dayStart:null,today=eq!=null&&dayStart!=null?eq-dayStart:null;
  // mode + heartbeat
  const mode=q('#mode');if(!S.paired){mode.textContent='NOT PAIRED';mode.className='pill off'}else if(!S.online){mode.textContent='OFFLINE';mode.className='pill off'}else if(L.orders){mode.textContent='LIVE';mode.className='pill live'}else{mode.textContent='DRY RUN';mode.className='pill dry'}
  q('#acct').textContent=L.account||'Prop Challenge';const a=S.heartbeat_age_s;
  q('#beat').textContent=a==null?'no report yet':a<90?a+'s ago':(a<3600?Math.round(a/60)+'m':a<172800?Math.round(a/3600)+'h':Math.round(a/86400)+'d')+' ago';
  q('#dot').className='dot'+(S.online?' on':'');q('#dot2').className=q('#dot').className;
  q('#botTxt').textContent=!S.paired?'Not paired':!S.online?'Offline · next start '+nextStart():L.orders?'Running · placing real orders':'Running · dry run (no orders)';
  const b=q('#banner');if(S.paired&&!S.online){b.className='banner show';q('#bannerTxt').innerHTML='<b>Bot offline.</b> It runs from your Mac on weekdays 9:20 AM–4:05 PM ET. Next start: <b>'+esc(nextStart())+'</b>. Keep the Mac on, plugged in and awake.'}
  else if(!S.paired){b.className='banner show';q('#bannerTxt').innerHTML='<b>Not paired.</b> Tap ⚙ to get a pairing code for your Mac.'}else b.className='banner';
  // metrics strip
  q('#mBal').textContent=usd(eq);q('#mR').innerHTML='<span class="'+cls(real)+'">'+sgn(real)+'</span>';q('#mU').innerHTML='<span class="'+cls(pos?upl:null)+'">'+(pos?sgn(upl):'—')+'</span>';
  const prog=eq==null?0:eq-start;q('#mT').innerHTML=funded?'<span class="muted">Funded · payouts</span>':cs.passed?'<span class="up">PASSED</span>':usd(Math.max(0,(TARGET||3000)-prog))+' <span class="muted" style="font-size:11px">to go</span>';q('#mTb').style.width=funded?'0':pct(prog,TARGET||3000)+'%';
  q('#mL').textContent=usd(floor);const used=today!=null&&today<0?-today:0;q('#mD').innerHTML='<span class="'+(used?'down':'muted')+'">'+usd(used)+'</span> <span class="muted" style="font-size:11px">/ '+usd(DAILY).replace('.00','')+'</span>';q('#mDb').style.width=pct(used,DAILY)+'%';
  // rules
  q('#rT').textContent=funded?'Profit '+sgn(prog):usd(Math.max(0,prog))+' / '+usd(TARGET||3000).replace('.00','')+(TARGET>(num(cs.target)||TARGET)?' (raised by consistency rule)':'');q('#rTb').style.width=pct(prog,funded?1e9:TARGET||3000)+'%';
  const room=eq!=null&&floor!=null?eq-floor:null;q('#rL').textContent=room==null?'—':usd(room);q('#rLb').style.width=pct(room??0,MLL)+'%';q('#rLb').style.background=room!=null&&room<600?'var(--down)':'var(--acc)';
  q('#rD').textContent=usd(used)+' / '+usd(DAILY).replace('.00','');q('#rDb').style.width=pct(used,DAILY)+'%';
  q('#guard').textContent=cs.passed?'Challenge passed — request the funded account on Topstep.':st.allowed===false&&st.note?'Stopped: '+st.note:'';
  // position
  const sp=q('#sidePill');sp.textContent=pos>0?'LONG':pos<0?'SHORT':'FLAT';sp.className='sidepill'+(pos>0?' long':pos<0?' short':'');
  q('#pPnl').textContent=pos?sgn(upl):'$0.00';q('#pPnl').className='big '+cls(pos?upl:null);q('#pQty').textContent=Math.abs(pos);
  q('#pAvg').textContent=pos&&num(st.avg)!=null?num(st.avg).toFixed(2):'—';q('#pLast').textContent=num(st.price)!=null?num(st.price).toFixed(2):'—';
  const c=(L.contract||'').split('.');q('#sym').textContent=c.length>3?c[3]+c[4].slice(0,1)+c[4].slice(-1):'MNQ';
  renderPanel();draw();}
function evsToday(){const d=new Date().toDateString();return myEvents().filter(e=>new Date(e.time).toDateString()===d)}
function renderPanel(){if(!S)return;const L=view(),st=L.status||{},pos=num(st.position)||0,all=myEvents(),trades=all.filter(e=>['buy','sell','flat'].includes(e.kind));
  q('#nT').textContent=trades.length||'';q('#nA').textContent=all.length||'';let h='';
  if(tab==='pos'){h=pos?'<table class="tbl"><tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Avg</th><th>Last</th><th>P&amp;L</th></tr><tr><td>'+esc(q('#sym').textContent)+'</td><td class="'+(pos>0?'up':'down')+'">'+(pos>0?'Long':'Short')+'</td><td>'+Math.abs(pos)+'</td><td>'+(num(st.avg)!=null?num(st.avg).toFixed(2):'—')+'</td><td>'+(num(st.price)!=null?num(st.price).toFixed(2):'—')+'</td><td class="'+cls(st.open_pnl)+'">'+sgn(st.open_pnl)+'</td></tr></table>':'<div class="empty">No open positions.</div>'}
  else if(tab==='trades'){h=trades.length?'<table class="tbl"><tr><th>Time</th><th>Side</th><th>Qty</th><th>Price</th><th>P&amp;L</th></tr>'+trades.slice(0,60).map(e=>'<tr><td>'+esc(tm(e.time))+'</td><td><span class="k '+esc(e.kind)+'">'+esc(e.kind)+'</span></td><td>'+esc(e.size??'')+'</td><td>'+(num(e.price)!=null?num(e.price).toFixed(2):'')+'</td><td class="'+cls(e.pnl)+'">'+(num(e.pnl)!=null?sgn(e.pnl):'')+'</td></tr>').join('')+'</table>':'<div class="empty">No trades yet.</div>'}
  else if(tab==='act'){h=all.length?'<table class="tbl"><tr><th>Time</th><th>Type</th><th>Detail</th></tr>'+all.slice(0,80).map(e=>'<tr><td>'+esc(new Date(e.time).toLocaleDateString([],{month:'short',day:'numeric'})+' '+tm(e.time))+'</td><td><span class="k '+esc(e.kind)+'">'+esc(e.kind)+'</span></td><td class="t">'+esc(e.text)+'</td></tr>').join('')+'</table>':'<div class="empty">No activity yet.</div>'}
  else{const t=evsToday(),cl=t.filter(e=>num(e.pnl)!=null).map(e=>num(e.pnl)),w=cl.filter(x=>x>0);const tot=cl.reduce((a,b)=>a+b,0);
    h='<table class="tbl"><tr><th>Today</th><th></th></tr><tr><td>Trades</td><td>'+t.filter(e=>['buy','sell'].includes(e.kind)).length+'</td></tr><tr><td>Closed P&amp;L</td><td class="'+cls(tot)+'">'+(cl.length?sgn(tot):'—')+'</td></tr><tr><td>Win rate</td><td>'+(cl.length?Math.round(w.length/cl.length*100)+'% ('+w.length+'/'+cl.length+')':'—')+'</td></tr><tr><td>Best trade</td><td class="up">'+(cl.length?sgn(Math.max(...cl)):'—')+'</td></tr><tr><td>Worst trade</td><td class="down">'+(cl.length?sgn(Math.min(...cl)):'—')+'</td></tr></table>'}
  q('#panel').innerHTML=h}
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===t));tab=t.dataset.t;renderPanel()});
const cv=q('#cv'),ctx=cv.getContext('2d');
function draw(){if(!S)return;const L=view(),st=L.status||{},bars=L.bars||[],marks=myEvents().filter(e=>num(e.price)!=null&&['buy','sell','flat'].includes(e.kind));
  const dpr=devicePixelRatio||1,W=cv.clientWidth,H=cv.clientHeight;cv.width=W*dpr;cv.height=H*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);
  q('#cmsg').style.display=bars.length?'none':'flex';if(!bars.length){q('#lastPx').textContent='—';q('#chg').textContent='—';q('#ohlc').textContent='';return}
  const ax=64,pw=W-ax,ph=H-22,n=bars.length;let lo=Math.min(...bars.map(b=>b[3])),hi=Math.max(...bars.map(b=>b[2]));const avg=num(st.avg),pos=num(st.position)||0;
  if(pos&&avg!=null){lo=Math.min(lo,avg);hi=Math.max(hi,avg)}const pad=(hi-lo)*.08||1;lo-=pad;hi+=pad;
  const Y=v=>24+(hi-v)/(hi-lo)*(ph-32),step=pw/Math.max(n,30),bw=Math.max(1,Math.min(10,step*.68)),X=i=>i*step+step/2;
  ctx.font='11px ui-monospace,Menlo,monospace';ctx.strokeStyle='#161c28';ctx.fillStyle='#5b6479';
  for(let k=0;k<=5;k++){const v=lo+(hi-lo)*k/5,y=Math.round(Y(v))+.5;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(pw,y);ctx.stroke();ctx.fillText(v.toFixed(2),pw+6,y+4)}
  const tix=[0,Math.floor(n/3),Math.floor(2*n/3),n-1];tix.forEach(i=>{const x=Math.round(X(i))+.5;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,ph);ctx.stroke();ctx.fillText(tm(bars[i][0]),Math.max(0,Math.min(pw-48,x-22)),H-6)});
  bars.forEach((b,i)=>{const up=b[4]>=b[1],col=up?'#22c55e':'#ef4444',x=Math.round(X(i))+.5;ctx.strokeStyle=col;ctx.beginPath();ctx.moveTo(x,Y(b[2]));ctx.lineTo(x,Y(b[3]));ctx.stroke();
    const t=Y(Math.max(b[1],b[4])),bt=Y(Math.min(b[1],b[4]));ctx.fillStyle=col;ctx.fillRect(x-bw/2,t,bw,Math.max(1,bt-t))});
  if(pos&&avg!=null){const y=Math.round(Y(avg))+.5;ctx.strokeStyle='#3b82f6';ctx.setLineDash([6,4]);ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(pw,y);ctx.stroke();ctx.setLineDash([]);
    const lt=(pos>0?'LONG ':'SHORT ')+Math.abs(pos)+' @ '+avg.toFixed(2);ctx.fillStyle='#3b82f6';ctx.fillRect(4,y-9,ctx.measureText(lt).width+10,18);ctx.fillStyle='#fff';ctx.fillText(lt,9,y+4)}
  const t0=new Date(bars[0][0]).getTime();marks.forEach(m=>{const t=new Date(m.time).getTime(),i=Math.floor((t-t0)/300000)-1;if(i<0||i>=n)return;const x=X(i),y=Y(num(m.price)),buy=m.kind==='buy';
    ctx.fillStyle=buy?'#22c55e':m.kind==='sell'?'#ef4444':'#8590a6';ctx.beginPath();if(buy){ctx.moveTo(x,y+5);ctx.lineTo(x-6,y+15);ctx.lineTo(x+6,y+15)}else{ctx.moveTo(x,y-5);ctx.lineTo(x-6,y-15);ctx.lineTo(x+6,y-15)}ctx.fill()});
  const last=bars[n-1][4],open=bars[0][1],ly=Math.round(Y(last))+.5,upd=last>=open;ctx.strokeStyle=upd?'#22c55e':'#ef4444';ctx.setLineDash([2,3]);ctx.beginPath();ctx.moveTo(0,ly);ctx.lineTo(pw,ly);ctx.stroke();ctx.setLineDash([]);
  ctx.fillStyle=upd?'#22c55e':'#ef4444';ctx.fillRect(pw+1,ly-9,ax-2,18);ctx.fillStyle='#fff';ctx.fillText(last.toFixed(2),pw+6,ly+4);
  q('#lastPx').textContent=last.toFixed(2);q('#chg').textContent=(last-open>=0?'+':'')+(last-open).toFixed(2)+' ('+((last-open)/open*100).toFixed(2)+'%)';q('#chg').className=upd?'up':'down';
  let hb=hover!=null&&hover>=0&&hover<n?hover:n-1;const b=bars[hb];q('#ohlc').innerHTML=esc(tm(b[0]))+'  O <b>'+b[1].toFixed(2)+'</b>  H <b>'+b[2].toFixed(2)+'</b>  L <b>'+b[3].toFixed(2)+'</b>  C <b>'+b[4].toFixed(2)+'</b>';
  if(hover!=null&&hover>=0&&hover<n){const x=Math.round(X(hover))+.5;ctx.strokeStyle='#3b4560';ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,ph);ctx.stroke();ctx.setLineDash([])}
  cv._step=step;cv._n=n}
function setHover(clientX){const r=cv.getBoundingClientRect();if(!cv._step)return;const i=Math.floor((clientX-r.left)/cv._step);hover=i>=0&&i<cv._n?i:null;draw()}
cv.addEventListener('mousemove',e=>setHover(e.clientX));cv.addEventListener('mouseleave',()=>{hover=null;draw()});
cv.addEventListener('touchmove',e=>setHover(e.touches[0].clientX),{passive:true});cv.addEventListener('touchend',()=>{hover=null;draw()});
q('#acctSel').onchange=e=>{sel=e.target.value;try{localStorage.setItem('propAcct',sel)}catch(x){}render()};
q('#gear').onclick=()=>q('#sheet').classList.add('show');q('#closeSheet').onclick=()=>q('#sheet').classList.remove('show');q('#sheet').onclick=e=>{if(e.target.id==='sheet')q('#sheet').classList.remove('show')};
q('#pairBtn').onclick=async()=>{if(S&&S.paired&&!confirm('A new code disconnects the Mac until you run the new command. Continue?'))return;
  try{const r=await fetch('/prop/pair',{method:'POST',credentials:'same-origin'});const d=await r.json();q('#pairOut').innerHTML='<p>On your Mac, open Terminal and run:</p><code>bash ~/p100-prop/pair.sh '+esc(d.token)+'</code><p style="font-size:12px">This code is shown once.</p>'}catch(e){q('#pairOut').textContent='Could not create a code — try again.'}};
new ResizeObserver(()=>draw()).observe(cv);load();setInterval(load,5000);
</script></body></html>'''
