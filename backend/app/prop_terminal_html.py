PROP_TERMINAL_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>PresNa Capital · Terminal</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;800&family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#06070d"><link rel="apple-touch-icon" href="/static/icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<style>
:root{--bg:#06070d;--p:#0c0f1a;--p2:#11152280;--line:#1d2336;--ink:#e8ecf6;--sub:#8a93ad;--dim:#565f78;--up:#2ee59d;--down:#ff4d6d;
--cy:#36d6ff;--vi:#a26bff;--pk:#ff4fd8;--am:#ffb547;--mono:"JetBrains Mono",ui-monospace,Menlo,monospace;--sans:Inter,-apple-system,Segoe UI,sans-serif}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--ink);font:13px/1.45 var(--sans);-webkit-font-smoothing:antialiased}
body{background:radial-gradient(1200px 600px at 10% -10%,#1a1440 0,transparent 60%),radial-gradient(900px 500px at 110% 10%,#0b2a3a 0,transparent 60%),var(--bg);min-height:100vh}
button{font:inherit;color:inherit;cursor:pointer;border:0;background:none}a{color:var(--cy);text-decoration:none}
.mono{font-family:var(--mono)}.up{color:var(--up)}.down{color:var(--down)}.sub{color:var(--sub)}.dim{color:var(--dim)}
.wrap{max-width:1500px;margin:0 auto;padding:max(10px,env(safe-area-inset-top)) 14px 40px}
.panel{background:linear-gradient(180deg,#0e1220ee,#0a0d18ee);border:1px solid var(--line);border-radius:14px;padding:12px 14px;position:relative;overflow:hidden}
.panel h3{margin:0 0 8px;font:600 10px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--sub);display:flex;align-items:center;gap:8px}
.panel h3 .r{margin-left:auto;color:var(--dim);letter-spacing:.06em}
.chip{font:700 9px/1 var(--mono);letter-spacing:.1em;padding:4px 6px;border-radius:5px;border:1px solid currentColor;text-transform:uppercase}
/* header */
.hdr{display:grid;grid-template-columns:auto 1fr auto;gap:16px;align-items:center;padding:14px 16px;margin-bottom:12px}
.orb{width:58px;height:58px;border-radius:50%;background:radial-gradient(circle at 35% 30%,#fff,#c7b6ff 30%,#7b4dff 65%,#2b1673);box-shadow:0 0 30px #7b4dff88,inset 0 0 12px #fff6;display:grid;place-items:center;position:relative}
.orb i{width:5px;height:18px;background:#1b0f45;border-radius:2px;margin:0 2px;display:inline-block}
.orb.on{animation:breathe 3.2s ease-in-out infinite}@keyframes breathe{50%{box-shadow:0 0 52px #7b4dffcc,inset 0 0 12px #fff8}}
.ttl{font:800 26px/1.05 var(--mono);letter-spacing:-.02em;background:linear-gradient(90deg,#7fd6ff,#b28bff 60%,#ff7ad9);-webkit-background-clip:text;background-clip:text;color:transparent}
.ttl small{font:700 10px var(--mono);color:var(--vi);border:1px solid #6b4dff88;background:#2a1d5a66;padding:3px 7px;border-radius:6px;margin-left:8px;vertical-align:middle;-webkit-text-fill-color:#c9b6ff}
.status{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:6px;font:12px var(--mono);color:var(--sub)}
.led{width:8px;height:8px;border-radius:50%;background:var(--dim);display:inline-block;margin-right:6px}.led.on{background:var(--up);box-shadow:0 0 10px var(--up);animation:blink 1.6s infinite}
@keyframes blink{50%{opacity:.35}}
.mode{font:800 10px var(--mono);letter-spacing:.12em;padding:4px 8px;border-radius:6px;border:1px solid}
.mode.live{color:var(--up);border-color:#2ee59d66;background:#2ee59d14}.mode.dry{color:var(--am);border-color:#ffb54766}.mode.off{color:var(--down);border-color:#ff4d6d66}
.big{text-align:right}.big .v{font:800 34px/1 var(--mono);letter-spacing:-.03em}.big .l{font:10px var(--mono);color:var(--dim);letter-spacing:.12em;text-transform:uppercase;margin-top:4px}
.big .d{font:700 14px var(--mono);margin-top:4px}
.spark{height:26px;width:220px;display:block;margin-left:auto;margin-top:6px}
/* grid */
.grid{display:grid;grid-template-columns:300px 1fr 360px;gap:12px}
.col{display:flex;flex-direction:column;gap:12px;min-width:0}
/* agents */
.agent{border-radius:12px;padding:11px 12px;border:1px solid;position:relative}
.agent .t{display:flex;align-items:center;gap:8px;font:800 13px var(--mono);letter-spacing:.06em}
.agent .t .chip{margin-left:auto}.agent .s{color:var(--sub);font-size:12px;margin:3px 0 6px}
.agent .k{font:12px var(--mono);color:var(--ink)}.agent .k b{color:#fff}
.agent .bar{height:4px;border-radius:3px;background:#ffffff12;margin-top:7px;overflow:hidden}.agent .bar i{display:block;height:100%;border-radius:3px;transition:width .8s}
.a-scout{border-color:#36d6ff55;background:linear-gradient(135deg,#0b2733aa,#0b0f1aaa);color:var(--cy)}
.a-analyst{border-color:#a26bff55;background:linear-gradient(135deg,#1f1640aa,#0b0f1aaa);color:var(--vi)}
.a-risk{border-color:#ffb54755;background:linear-gradient(135deg,#2e2110aa,#0b0f1aaa);color:var(--am)}
.a-exec{border-color:#2ee59d55;background:linear-gradient(135deg,#0d2a20aa,#0b0f1aaa);color:var(--up)}
.a-log{border-color:#ff4fd855;background:linear-gradient(135deg,#2a1030aa,#0b0f1aaa);color:var(--pk)}
.a-you{border-color:#ffffff33;background:linear-gradient(135deg,#1a1d29aa,#0b0f1aaa);color:#fff}
.agent.glow{animation:aglow 1.2s ease-out}@keyframes aglow{0%{box-shadow:0 0 0 0 currentColor}100%{box-shadow:0 0 0 14px transparent}}
.closebtn{width:100%;margin-top:8px;padding:12px;border-radius:10px;background:linear-gradient(90deg,#ff4d6d,#ff7a59);color:#fff;font:800 13px var(--mono);letter-spacing:.06em;box-shadow:0 6px 24px #ff4d6d44}
.closebtn:disabled{opacity:.4;cursor:not-allowed;box-shadow:none}
/* flow */
.flow{height:150px;position:relative}
.flow canvas{position:absolute;inset:0;width:100%;height:100%}
.nodes{position:absolute;inset:0;display:flex;justify-content:space-between;align-items:center;padding:0 2%}
.node{text-align:center;width:17%;pointer-events:none}
.node .c{width:46px;height:46px;border-radius:50%;margin:0 auto 6px;display:grid;place-items:center;font-size:18px;border:2px solid;background:#0a0d18;box-shadow:0 0 18px currentColor inset}
.node .n{font:800 10px var(--mono);letter-spacing:.12em}.node .m{font:11px var(--mono);color:var(--sub)}
/* chart */
.chartbox{height:300px;position:relative}.chartbox canvas{width:100%;height:100%;display:block}
.legend{display:flex;gap:14px;flex-wrap:wrap;font:11px var(--mono);color:var(--sub);margin-top:6px}.legend i{display:inline-block;width:14px;height:2px;vertical-align:middle;margin-right:5px}
/* neural */
.neural{height:300px;position:relative}.neural canvas{position:absolute;inset:0;width:100%;height:100%}
.decide{position:absolute;right:10px;top:10px;text-align:right;font:11px var(--mono);color:var(--sub)}
.decide b{display:block;font:800 22px var(--mono);letter-spacing:.04em}
.caption{font:11px var(--mono);color:var(--dim);margin-top:6px}
/* accounts */
table{width:100%;border-collapse:collapse;font:12px var(--mono)}th{color:var(--dim);font-weight:600;text-align:left;padding:6px 6px;border-bottom:1px solid var(--line);font-size:10px;letter-spacing:.1em;text-transform:uppercase}
td{padding:8px 6px;border-bottom:1px solid #ffffff08;white-space:nowrap}tr.sel td{background:#ffffff08}tr{cursor:pointer}
.firm{font:800 10px var(--mono);padding:3px 6px;border-radius:5px;background:#fff;color:#06070d}
.mini{height:5px;width:90px;background:#ffffff12;border-radius:3px;overflow:hidden;display:inline-block;vertical-align:middle}.mini i{display:block;height:100%}
/* ring */
.ringwrap{display:grid;grid-template-columns:140px 1fr;gap:12px;align-items:center}
.ringwrap canvas{width:140px;height:140px}
.kv{display:grid;grid-template-columns:1fr auto;gap:4px 10px;font:12px var(--mono)}.kv span:nth-child(odd){color:var(--sub)}
/* log */
.log{font:11.5px/1.6 var(--mono);height:300px;overflow:hidden;position:relative}
.log .ln{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;animation:fadein .5s}.log .tm{color:var(--dim);margin-right:8px}
@keyframes fadein{from{opacity:0;transform:translateX(-6px)}}
.k-buy{color:var(--up)}.k-sell{color:var(--down)}.k-flat{color:var(--cy)}.k-halt,.k-error{color:var(--am)}.k-pass{color:#fff;background:#2ee59d33}.k-day{color:var(--vi)}.k-london{color:var(--dim)}
.cursor{display:inline-block;width:7px;height:13px;background:var(--up);vertical-align:middle;animation:blink 1s steps(1) infinite}
/* stats */
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.stat{background:#ffffff06;border:1px solid #ffffff0d;border-radius:10px;padding:9px}.stat .v{font:800 18px var(--mono)}.stat .l{font:10px var(--mono);color:var(--dim);letter-spacing:.1em;text-transform:uppercase}
.banner{display:none;margin-bottom:12px;padding:10px 14px;border-radius:12px;border:1px solid #ffb54755;background:#2e211066;color:#ffd9a0;font-size:13px}.banner.show{display:block}
.foot{margin-top:14px;font:11px var(--mono);color:var(--dim);display:flex;gap:16px;flex-wrap:wrap}
select{background:#0c0f1a;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:5px 8px;font:12px var(--mono)}
@media (max-width:1180px){.grid{grid-template-columns:1fr 1fr}.col.mid{grid-column:1/-1;order:-1}}
@media (max-width:760px){.grid{grid-template-columns:1fr}.hdr{grid-template-columns:auto 1fr}.big{grid-column:1/-1;text-align:left}.spark{margin-left:0;width:100%}.ttl{font-size:20px}.big .v{font-size:28px}
 .chartbox,.neural,.log{height:250px}.node .c{width:38px;height:38px;font-size:15px}.node .m{font-size:10px}.stats{grid-template-columns:repeat(3,1fr)}.ringwrap{grid-template-columns:110px 1fr}.ringwrap canvas{width:110px;height:110px}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
</style></head><body><div class="wrap">

<div class="banner" id="banner"></div>

<div class="panel hdr">
  <div class="orb" id="orb"><span><i></i><i></i></span></div>
  <div>
    <div class="ttl">PresNa Capital Terminal<small>NOISE · v3</small></div>
    <div class="status"><span><span class="led" id="led"></span><span id="mkt">connecting…</span></span>
      <span class="mode off" id="mode">—</span><span id="clock" class="dim"></span><span id="beat" class="dim"></span>
      <select id="acctSel" title="Account"></select></div>
  </div>
  <div class="big"><div class="v" id="tEq">—</div><div class="l">all accounts · equity</div>
    <div class="d" id="tToday">—</div><canvas class="spark" id="spark"></canvas><div class="l" style="margin-top:2px">MNQ price today</div></div>
</div>

<div class="grid">
 <div class="col">
  <div class="agent a-scout" id="agScout"><div class="t">◎ SCOUT<span class="chip" id="cScout">—</span></div>
    <div class="s">reads the market every 15 s</div><div class="k" id="kScout">—</div><div class="bar"><i id="bScout" style="background:var(--cy)"></i></div></div>
  <div class="agent a-analyst" id="agAnalyst"><div class="t">◆ ANALYST<span class="chip" id="cAnalyst">—</span></div>
    <div class="s">NOISE trend check, on the hour 10:00–3:00</div><div class="k" id="kAnalyst">—</div><div class="bar"><i id="bAnalyst" style="background:var(--vi)"></i></div></div>
  <div class="agent a-risk" id="agRisk"><div class="t">▲ RISK<span class="chip" id="cRisk">—</span></div>
    <div class="s">daily stop · loss limit · news windows</div><div class="k" id="kRisk">—</div><div class="bar"><i id="bRisk" style="background:var(--am)"></i></div></div>
  <div class="agent a-exec" id="agExec"><div class="t">⚡ EXECUTOR<span class="chip" id="cExec">—</span></div>
    <div class="s">same signal on every account · take-profit · flat by 3:55</div><div class="k" id="kExec">—</div></div>
  <div class="agent a-log" id="agLog"><div class="t">≡ LOGGER<span class="chip" id="cLog">WRITE</span></div>
    <div class="s">every decision written down</div><div class="k" id="kLog">—</div></div>
  <div class="agent a-you"><div class="t">◉ YOU<span class="chip" id="cYou">READING</span></div>
    <div class="s">one button: close the open trade now, keep trading</div>
    <button class="closebtn" id="closeNow">CLOSE TRADE NOW</button><div class="k" id="cmdTxt" style="margin-top:6px;color:var(--sub)"></div></div>
 </div>

 <div class="col mid">
  <div class="panel"><h3>Live flow · hard handoffs<span class="r" id="flowR"></span></h3>
   <div class="flow"><canvas id="flowCv"></canvas><div class="nodes">
    <div class="node" style="color:var(--cy)"><div class="c">◎</div><div class="n">SCOUT</div><div class="m" id="nScout">—</div></div>
    <div class="node" style="color:var(--vi)"><div class="c">◆</div><div class="n">ANALYST</div><div class="m" id="nAnalyst">—</div></div>
    <div class="node" style="color:var(--am)"><div class="c">▲</div><div class="n">RISK</div><div class="m" id="nRisk">—</div></div>
    <div class="node" style="color:var(--up)"><div class="c">⚡</div><div class="n">EXECUTOR</div><div class="m" id="nExec">—</div></div>
    <div class="node" style="color:var(--pk)"><div class="c">≡</div><div class="n">LOGGER</div><div class="m" id="nLog">—</div></div>
   </div></div></div>
  <div class="panel"><h3>MNQ · 5 min · today<span class="r" id="chartR"></span></h3><div class="chartbox"><canvas id="chart"></canvas></div>
   <div class="legend"><span><i style="background:var(--cy)"></i>entry</span><span><i style="background:var(--up)"></i>take-profit</span><span><i style="background:var(--vi);height:0;border-top:1px dashed var(--vi)"></i>hourly decision</span><span id="lgPos"></span></div></div>
  <div class="panel"><h3>Neural shell · market pulse<span class="r" id="neuR"></span></h3><div class="neural"><canvas id="neu"></canvas>
   <div class="decide"><span>decision state</span><b id="dState">—</b><span id="dSub"></span></div></div>
   <div class="caption">Bright dots are real 5-minute bars from the feed (green up, red down, size = move); the faint shell is decoration. Inputs on the left are live values the bot checks.</div></div>
 </div>

 <div class="col">
  <div class="panel"><h3>Accounts<span class="r" id="accR"></span></h3><table><thead><tr><th>Firm</th><th>Now</th><th>Today</th><th>Total</th></tr></thead><tbody id="accBody"></tbody></table></div>
  <div class="panel"><h3>Challenge score<span class="r" id="ringR"></span></h3><div class="ringwrap"><canvas id="ring"></canvas><div class="kv" id="ringKv"></div></div></div>
  <div class="panel"><h3>Stats from the feed<span class="r">last 100 events</span></h3><div class="stats" id="stats"></div></div>
  <div class="panel"><h3>$ tail -f bot.log<span class="r" id="logR"></span></h3><div class="log" id="log"></div></div>
 </div>
</div>
<div class="foot"><span>Real data only · nothing on this screen is simulated</span><a href="/prop/classic">Classic view &amp; pairing ⚙</a><a href="/">Home</a></div>
</div>
<script>
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num=v=>{const n=Number(v);return v!=null&&v!==''&&Number.isFinite(n)?n:null};
const usd=(v,d=2)=>num(v)==null?'—':num(v).toLocaleString('en-US',{style:'currency',currency:'USD',minimumFractionDigits:d,maximumFractionDigits:d});
const sgn=(v,d=2)=>num(v)==null?'—':(num(v)>=0?'+':'−')+usd(Math.abs(num(v)),d);
const cls=v=>num(v)==null||Math.abs(num(v))<0.005?'sub':num(v)>0?'up':'down';
const C={up:'#2ee59d',down:'#ff4d6d',cy:'#36d6ff',vi:'#a26bff',pk:'#ff4fd8',am:'#ffb547',dim:'#565f78'};
let S=null,sel=(()=>{try{return localStorage.getItem('termAcct')||''}catch(e){return ''}})(),lastIds=new Set(),pulses=[];
/* ---------- time (ET) ---------- */
function et(d=new Date()){const p=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',weekday:'short',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).formatToParts(d).map(x=>[x.type,x.value]));
  return {wd:['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].indexOf(p.weekday),date:p.year+'-'+p.month+'-'+p.day,h:+p.hour%24,m:+p.minute,s:+p.second}}
function mins(t){return t.h*60+t.m+t.s/60}
function marketOpen(t=et()){return t.wd>=1&&t.wd<=5&&mins(t)>=570&&mins(t)<960}
function nextCheck(t=et()){if(t.wd<1||t.wd>5)return null;const m=mins(t);for(let h=10;h<=15;h++){if(h*60>m)return h*60}return null}
function nextStartTxt(t=et()){if(t.wd>=1&&t.wd<=5&&mins(t)<465)return 'today 7:45 AM ET';let n=t.wd,k=0;do{n=(n+1)%7;k++}while(n===0||n===6);return (k===1?'tomorrow':['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][n])+' 7:45 AM ET'}
const hm=m=>{let h=Math.floor(m/60),mm=Math.round(m%60);return (h>12?h-12:h)+':'+String(mm).padStart(2,'0')+(h>=12?' PM':' AM')};
/* ---------- data helpers ---------- */
const accts=()=>((S&&S.latest&&S.latest.accounts)||[]).filter(a=>a&&a.status);
function cur(){const A=accts();if(!A.length)return null;return A.find(a=>a.account===sel)||A[0]}
function eqOf(a){const s=a.status||{},b=num(s.balance),u=num(s.position)?num(s.open_pnl)||0:0;return b==null?null:b+u}
function startOf(a){const s=(a.status||{}).state||{};return num(s.start_balance)||((num(a.status.size_k)||50)*1000)}
function dayStartOf(a){return num(((a.status||{}).state||{}).day_start_balance)}
function short(a){return (a.firm||'Topstep')+' '+(num(a.status.size_k)?num(a.status.size_k)+'K':'')}
function evs(){return (S&&S.events)||[]}
function todayBars(){const B=(S&&S.latest&&S.latest.bars)||[];if(!B.length)return [];const day=et(new Date(B[B.length-1][0])).date;return B.filter(b=>et(new Date(b[0])).date===day)}
/* ---------- load ---------- */
async function load(){try{const r=await fetch('/prop/state',{credentials:'same-origin'});if(r.status===401||r.redirected){location.href='/login';return}
  S=await r.json();ingestEvents();render()}catch(e){$('#beat').textContent='reconnecting…'}}
function ingestEvents(){const E=evs();for(const e of E.slice().reverse()){if(!lastIds.has(e.id)){if(lastIds.size)fire(e);lastIds.add(e.id)}}}
function fire(e){const k=e.kind;const to=k==='buy'||k==='sell'||k==='flat'?3:k==='halt'||k==='error'?2:k==='pass'?3:4;pulses.push({t:0,to,color:k==='sell'||k==='halt'?C.down:k==='buy'||k==='pass'?C.up:C.vi});
  const map={3:'#agExec',2:'#agRisk',4:'#agLog'},el=$(map[to]);if(el){el.classList.remove('glow');void el.offsetWidth;el.classList.add('glow')}}
/* ---------- render ---------- */
function render(){if(!S)return;const A=accts(),a=cur(),t=et(),open=marketOpen(t);
  const so=$('#acctSel');const opts=A.map(x=>'<option value="'+esc(x.account)+'"'+(a&&x.account===a.account?' selected':'')+'>'+esc(short(x)+' · '+x.account.slice(0,22))+'</option>').join('');
  if(so.dataset.o!==opts){so.innerHTML=opts;so.dataset.o=opts}so.style.display=A.length>1?'':'none';
  // header
  const online=!!S.online,anyLive=A.some(x=>x.orders);$('#led').className='led'+(online?' on':'');$('#orb').className='orb'+(online?' on':'');
  $('#mkt').textContent=!S.paired?'not paired':!online?'bot offline · next start '+nextStartTxt(t):open?'market open · bot running':'bot running · market closed';
  const md=$('#mode');md.textContent=!online?'OFFLINE':anyLive?'LIVE':'DRY RUN';md.className='mode '+(!online?'off':anyLive?'live':'dry');
  const ag=S.heartbeat_age_s;$('#beat').textContent=ag==null?'':'· last report '+(ag<90?ag+'s':ag<5400?Math.round(ag/60)+'m':ag<172800?Math.round(ag/3600)+'h':Math.round(ag/86400)+'d')+' ago';
  const live=A.filter(x=>x.orders),T=live.length?live:A;let eq=0,today=0,total=0,okE=true;
  for(const x of T){const e=eqOf(x),ds=dayStartOf(x);if(e==null){okE=false;continue}eq+=e;total+=e-startOf(x);if(ds!=null)today+=e-ds}
  $('#tEq').textContent=okE&&T.length?usd(eq):'—';$('#tToday').innerHTML='<span class="'+cls(today)+'">'+sgn(today)+' today</span> <span class="dim">·</span> <span class="'+cls(total)+'">'+sgn(total)+' total</span>';
  const bn=$('#banner');if(!S.paired){bn.className='banner show';bn.innerHTML='<b>Not paired.</b> Open the <a href="/prop/classic">classic view</a> and tap ⚙ to pair your Mac.'}
  else if(!online){bn.className='banner show';bn.innerHTML='<b>Bot offline.</b> It runs from your Mac Mon–Fri 7:45 AM–4:05 PM ET. Next start <b>'+esc(nextStartTxt(t))+'</b>.'}else bn.className='banner';
  renderAgents(A,a,t,open,online);renderAccounts(A,a);renderRing(a);renderStats(a);renderLog();renderCmd(A);drawSpark();
}
function renderAgents(A,a,t,open,online){const tb=todayBars(),last=tb.length?tb[tb.length-1]:null,first=tb.length?tb[0]:null;
  const st=(a&&a.status)||{},cs=st.state||{};
  // scout
  $('#cScout').textContent=!online?'SLEEP':open?'SCAN':'IDLE';$('#cScout').style.color=open&&online?C.cy:C.dim;
  const mv=last&&first?(last[4]/first[1]-1)*100:null;
  $('#kScout').innerHTML='MNQ <b>'+(last?last[4].toFixed(2):'—')+'</b> · <span class="'+cls(mv)+'">'+(mv==null?'—':(mv>=0?'+':'')+mv.toFixed(2)+'%')+'</span> session · '+tb.length+' bars';
  $('#bScout').style.width=Math.min(100,tb.length/78*100)+'%';$('#nScout').textContent=tb.length+' bars';
  // analyst
  const nc=nextCheck(t),m=mins(t);let at='';if(nc!=null){const left=nc-m,mm=Math.floor(left),ss=Math.floor((left-mm)*60);at='next decision <b>'+hm(nc)+'</b> · in <b>'+mm+':'+String(ss).padStart(2,'0')+'</b>';
    $('#bAnalyst').style.width=Math.max(0,100-left/60*100)+'%'}else{at='no more decisions today';$('#bAnalyst').style.width='0'}
  const fast=A.some(x=>x.status&&x.status.fast);const think=nc!=null&&nc-m<1&&online;$('#cAnalyst').textContent=fast?'FAST 5M':think?'THINK':open&&online?'WAIT':'IDLE';$('#cAnalyst').style.color=think||fast?C.vi:C.dim;
  $('#kAnalyst').innerHTML=at+(fast?' · fast mode on':'');const done=nc==null?(open?6:0):Math.max(0,(nc/60)-10);$('#nAnalyst').textContent=Math.min(6,done)+'/6 checks';
  // risk
  const ds=dayStartOf(a||{status:{}}),e=a?eqOf(a):null,dstop=num(cs.daily_stop)||800,used=e!=null&&ds!=null&&e<ds?ds-e:0,floor=num(st.floor),room=e!=null&&floor!=null?e-floor:null;
  const halted=st.allowed===false;$('#cRisk').textContent=halted?'HALT':'OK';$('#cRisk').style.color=halted?C.down:C.am;
  $('#kRisk').innerHTML='daily loss <b>'+usd(used,0)+'</b> / '+usd(dstop,0)+' · room <b>'+usd(room,0)+'</b>'+(st.note?'<br><span class="dim">'+esc(st.note)+'</span>':'');
  $('#bRisk').style.width=Math.min(100,used/dstop*100)+'%';$('#nRisk').textContent=halted?'halted':'guards ok';
  // executor
  const rows=A.map(x=>{const p=num(x.status.position)||0;return '<b>'+esc((x.firm||'Topstep'))+'</b> '+(p>0?'<span class="up">LONG '+p+'</span>':p<0?'<span class="down">SHORT '+Math.abs(p)+'</span>':'<span class="dim">flat</span>')+(x.orders?'':' <span class="dim">(dry)</span>')}).join('<br>');
  const anyPos=A.some(x=>num(x.status.position));$('#cExec').textContent=anyPos?'IN TRADE':'FLAT';$('#cExec').style.color=anyPos?C.up:C.dim;$('#kExec').innerHTML=rows||'—';
  const todayEv=evs().filter(x=>x.time&&et(new Date(x.time)).date===et().date);const orders=todayEv.filter(x=>x.kind==='buy'||x.kind==='sell'||x.kind==='flat').length;$('#nExec').textContent=orders+' orders today';
  // logger
  const le=evs()[0];$('#kLog').innerHTML=evs().length+' events · last: <span class="dim">'+esc(le?le.text.slice(0,60):'—')+'</span>';$('#nLog').textContent='#'+evs().length;
  $('#flowR').textContent=online?(open?'live · every 15 s':'standing by'):'offline';
  // decision state
  const p=num(st.position)||0;$('#dState').textContent=p>0?'LONG':p<0?'SHORT':'FLAT';$('#dState').style.color=p>0?C.up:p<0?C.down:C.dim;
  $('#dSub').innerHTML=p?'open <span class="'+cls(st.open_pnl)+'">'+sgn(st.open_pnl)+'</span>':nc!=null?'next check '+hm(nc):'';
  $('#neuR').textContent=tb.length+' bars · '+(a?short(a):'');$('#chartR').textContent=last?'last '+last[4].toFixed(2):'';
  $('#lgPos').innerHTML=p?'<span class="'+(p>0?'up':'down')+'">'+(p>0?'LONG ':'SHORT ')+Math.abs(p)+' @ '+num(st.avg).toFixed(2)+'</span>':'';
}
function renderAccounts(A,a){$('#accR').textContent=A.length+' accounts';
  $('#accBody').innerHTML=A.map(x=>{const e=eqOf(x),ds=dayStartOf(x),td=e!=null&&ds!=null?e-ds:null,tot=e!=null?e-startOf(x):null,p=num(x.status.position)||0;
   return '<tr data-a="'+esc(x.account)+'"'+(a&&x.account===a.account?' class="sel"':'')+'><td><span class="firm">'+esc((x.firm||'Topstep').toUpperCase())+'</span> <span class="dim">'+(num(x.status.size_k)||'')+'K</span></td><td>'+(p>0?'<span class="up">LONG '+p+'</span>':p<0?'<span class="down">SHORT '+Math.abs(p)+'</span>':'<span class="dim">flat</span>')+'</td><td class="'+cls(td)+'">'+sgn(td)+'</td><td class="'+cls(tot)+'">'+sgn(tot)+'</td></tr>'}).join('')||'<tr><td colspan="4" class="dim">no accounts reported yet</td></tr>';
  document.querySelectorAll('#accBody tr[data-a]').forEach(r=>r.onclick=()=>{sel=r.dataset.a;try{localStorage.setItem('termAcct',sel)}catch(e){}render();drawChart()})}
let ringV={p:0,r:0};
function renderRing(a){if(!a){$('#ringKv').innerHTML='';return}const st=a.status||{},cs=st.state||{},e=eqOf(a),start=startOf(a),tgt=num(st.target)??num(cs.target),floor=num(st.floor),mll=num(cs.mll)||(start*0.04),prog=e!=null?e-start:0,room=e!=null&&floor!=null?e-floor:null;
  const funded=(st.kind||cs.kind)==='funded';ringV.p=funded?(num(cs.cycle_cap)?Math.max(0,Math.min(1,(e-(num(cs.cycle_start_balance)||start))/num(cs.cycle_cap))):0):tgt?Math.max(0,Math.min(1,prog/tgt)):0;ringV.r=room!=null?Math.max(0,Math.min(1,room/mll)):0;
  $('#ringR').textContent=short(a);const days=(cs.trade_days||[]).length;
  $('#ringKv').innerHTML=(funded?'<span>stage</span><span class="up">FUNDED · payouts</span>':'<span>target</span><span>'+usd(tgt,0)+'</span><span>progress</span><span class="'+cls(prog)+'">'+sgn(prog)+'</span><span>still needed</span><span>'+usd(Math.max(0,(tgt||0)-prog),0)+'</span>')+
   '<span>room to limit</span><span class="'+(room!=null&&room<mll*0.3?'down':'')+'">'+usd(room,0)+'</span><span>trading days</span><span>'+days+(num(cs.min_days)?' / '+num(cs.min_days)+' min':'')+'</span>'+(cs.passed?'<span>status</span><span class="up">PASSED</span>':'')}
function renderStats(a){const E=evs().filter(e=>!a||!e.account||e.account===a.account);const fl=E.filter(e=>e.kind==='flat'&&num(e.pnl)!=null&&!/dry run/i.test(e.text||''));
  const w=fl.filter(e=>num(e.pnl)>0),l=fl.filter(e=>num(e.pnl)<=0),best=fl.length?Math.max(...fl.map(e=>num(e.pnl))):null,worst=fl.length?Math.min(...fl.map(e=>num(e.pnl))):null,net=fl.reduce((s,e)=>s+num(e.pnl),0);
  const tr=E.filter(e=>(e.kind==='buy'||e.kind==='sell')&&!/dry run/i.test(e.text||'')).length;
  const st=[['trades',tr,''],['wins / losses',w.length+' / '+l.length,''],['win rate',fl.length?Math.round(w.length/fl.length*100)+'%':'—',''],['closed net',sgn(net,0),cls(net)],['best trade',sgn(best,0),cls(best)],['worst trade',sgn(worst,0),cls(worst)]];
  $('#stats').innerHTML=st.map(s=>'<div class="stat"><div class="v '+s[2]+'">'+s[1]+'</div><div class="l">'+s[0]+'</div></div>').join('')}
let logShown='';
function renderLog(){const E=evs().slice(0,40);const key=E.map(e=>e.id).join();if(key===logShown)return;logShown=key;
  $('#log').innerHTML=E.slice(0,24).map(e=>{const tt=e.time?new Date(e.time).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'';const acc=e.account?String(e.account).split('-')[0]+' ':'';
   return '<div class="ln"><span class="tm">'+tt+'</span><span class="k-'+esc(e.kind)+'">'+esc(String(e.kind||'').toUpperCase().padEnd(6,' '))+'</span> <span class="dim">'+esc(acc)+'</span>'+esc(e.text)+'</div>'}).join('')+'<div class="ln"><span class="cursor"></span></div>';
  $('#logR').textContent='line #'+evs().length}
function renderCmd(A){const c=S.command,el=$('#cmdTxt'),btn=$('#closeNow'),anyPos=A.some(x=>x.orders&&num(x.status.position));
  btn.disabled=!S.online||!anyPos;btn.textContent=anyPos?'CLOSE TRADE NOW':'NO OPEN TRADE';$('#cYou').textContent=c&&c.status==='pending'?'SENT':'READING';
  if(!c){el.textContent='';return}const age=(Date.now()-new Date(c.requested_at).getTime())/1000;if(age>3600){el.textContent='';return}
  el.textContent=c.status==='pending'?'Close requested — waiting for the Mac…':c.status==='done'?'Done: '+(c.result||'closed')+' · trading continues (5-min checks today)':c.status==='expired'?'Request expired — the Mac did not answer in 3 minutes.':''}
$('#closeNow').onclick=async()=>{if(!confirm('Close the open trade on every LIVE account now?\nThe bot keeps trading afterwards (5-minute checks for the rest of today).'))return;
  try{const r=await fetch('/prop/command/close',{method:'POST',credentials:'same-origin'});if(!r.ok)throw 0;$('#cmdTxt').textContent='Close requested — waiting for the Mac (about 15 s)…'}catch(e){$('#cmdTxt').textContent='Could not send — try again.'}load()};
$('#acctSel').onchange=e=>{sel=e.target.value;try{localStorage.setItem('termAcct',sel)}catch(x){}render();drawChart()};
/* ---------- canvas helpers ---------- */
function fit(cv){const r=cv.getBoundingClientRect(),d=window.devicePixelRatio||1;if(cv.width!==Math.round(r.width*d)||cv.height!==Math.round(r.height*d)){cv.width=Math.round(r.width*d);cv.height=Math.round(r.height*d)}const g=cv.getContext('2d');g.setTransform(d,0,0,d,0,0);return [g,r.width,r.height]}
/* spark: equity of selected account through today's closed trades */
function drawSpark(){const cv=$('#spark');const [g,w,h]=fit(cv);g.clearRect(0,0,w,h);const tb=todayBars();if(tb.length<2)return;const v=tb.map(b=>b[4]),mn=Math.min(...v),mx=Math.max(...v);
  g.beginPath();v.forEach((y,i)=>{const X=i/(v.length-1)*w,Y=h-2-(y-mn)/((mx-mn)||1)*(h-4);i?g.lineTo(X,Y):g.moveTo(X,Y)});const up=v[v.length-1]>=v[0];g.strokeStyle=up?C.up:C.down;g.lineWidth=1.5;g.stroke();
  g.lineTo(w,h);g.lineTo(0,h);g.closePath();const gr=g.createLinearGradient(0,0,0,h);gr.addColorStop(0,(up?C.up:C.down)+'44');gr.addColorStop(1,'transparent');g.fillStyle=gr;g.fill()}
/* candle chart */
function drawChart(){const cv=$('#chart');const [g,w,h]=fit(cv);g.clearRect(0,0,w,h);const tb=todayBars();
  if(!tb.length){g.fillStyle=C.dim;g.font='12px JetBrains Mono';g.fillText('waiting for today\'s first bars…',14,24);return}
  const a=cur(),st=(a&&a.status)||{},pos=num(st.position)||0,avg=num(st.avg);const lead=accts()[0];const sameInst=!a||!lead||a.account===lead.account;
  let lo=Math.min(...tb.map(b=>b[3])),hi=Math.max(...tb.map(b=>b[2]));let tp=null;
  if(pos&&avg&&sameInst){const sk=num(st.size_k)||50,tpd=600*sk/50,pv=2;tp=avg+(pos>0?1:-1)*tpd/(Math.abs(pos)*pv);lo=Math.min(lo,avg,tp);hi=Math.max(hi,avg,tp)}
  const pad=(hi-lo)*0.08||5;lo-=pad;hi+=pad;const L=8,R=58,T=8,B=20,W=w-L-R,H=h-T-B,n=78,cw=W/n,Y=p=>T+(hi-p)/(hi-lo)*H;
  g.strokeStyle='#ffffff0d';g.fillStyle=C.dim;g.font='10px JetBrains Mono';for(let i=0;i<=4;i++){const p=lo+(hi-lo)*i/4,y=Y(p);g.beginPath();g.moveTo(L,y);g.lineTo(L+W,y);g.stroke();g.fillText(p.toFixed(0),L+W+6,y+3)}
  const t0=new Date(tb[0][0]);const idx=b=>{const tt=et(new Date(b[0]));return Math.round((tt.h*60+tt.m-570)/5)};
  for(let hh=10;hh<=15;hh++){const x=L+((hh*60-570)/5)*cw;g.strokeStyle='#a26bff55';g.setLineDash([3,4]);g.beginPath();g.moveTo(x,T);g.lineTo(x,T+H);g.stroke();g.setLineDash([]);g.fillStyle=C.dim;g.fillText((hh>12?hh-12:hh)+'',x-3,h-6)}
  tb.forEach(b=>{const i=idx(b);if(i<0||i>=n)return;const x=L+i*cw+cw/2,up=b[4]>=b[1];g.strokeStyle=g.fillStyle=up?C.up:C.down;g.beginPath();g.moveTo(x,Y(b[2]));g.lineTo(x,Y(b[3]));g.stroke();
   const y1=Y(Math.max(b[1],b[4])),y2=Y(Math.min(b[1],b[4]));g.globalAlpha=.9;g.fillRect(x-Math.max(1,cw*.32),y1,Math.max(2,cw*.64),Math.max(1,y2-y1));g.globalAlpha=1});
  const lastB=tb[tb.length-1],lx=L+idx(lastB)*cw+cw/2,ly=Y(lastB[4]),ph=(Date.now()%1600)/1600;
  g.strokeStyle='#ffffff33';g.setLineDash([2,3]);g.beginPath();g.moveTo(L,ly);g.lineTo(L+W,ly);g.stroke();g.setLineDash([]);
  g.fillStyle=lastB[4]>=tb[0][1]?C.up:C.down;g.fillRect(L+W+2,ly-8,R-4,16);g.fillStyle='#06070d';g.font='bold 10px JetBrains Mono';g.fillText(lastB[4].toFixed(2),L+W+5,ly+4);
  g.beginPath();g.arc(lx,ly,3+ph*10,0,7);g.strokeStyle='rgba(255,255,255,'+(1-ph)*.6+')';g.stroke();
  if(pos&&avg&&sameInst){[[avg,C.cy,'entry'],[tp,C.up,'TP']].forEach(([p,c,l])=>{const y=Y(p);g.strokeStyle=c;g.lineWidth=1.2;g.beginPath();g.moveTo(L,y);g.lineTo(L+W,y);g.stroke();g.lineWidth=1;g.fillStyle=c;g.font='10px JetBrains Mono';g.fillText(l+' '+p.toFixed(2),L+4,y-4)})}}
/* flow particles */
const flowP=[];function drawFlow(dt){const cv=$('#flowCv');const [g,w,h]=fit(cv);g.clearRect(0,0,w,h);const xs=[.1,.3,.5,.7,.9].map(f=>f*w),y=h*0.36,cols=[C.cy,C.vi,C.am,C.up,C.pk];
  for(let i=0;i<4;i++){const gr=g.createLinearGradient(xs[i],0,xs[i+1],0);gr.addColorStop(0,cols[i]+'55');gr.addColorStop(1,cols[i+1]+'55');g.strokeStyle=gr;g.lineWidth=2;g.beginPath();g.moveTo(xs[i]+26,y);g.lineTo(xs[i+1]-26,y);g.stroke()}
  const active=S&&S.online,open=marketOpen(),rate=active?(open?.9:.25):.04;if(Math.random()<rate*dt*3)flowP.push({x:0,seg:0,sp:.35+Math.random()*.4});
  for(let k=flowP.length-1;k>=0;k--){const p=flowP[k];p.x+=p.sp*dt;if(p.x>=1){p.x=0;p.seg++;if(p.seg>=4||Math.random()<.18){flowP.splice(k,1);continue}}
   const X=xs[p.seg]+26+(xs[p.seg+1]-xs[p.seg]-52)*p.x;g.fillStyle=cols[p.seg+1];g.shadowColor=cols[p.seg+1];g.shadowBlur=10;g.beginPath();g.arc(X,y,2.2,0,7);g.fill();g.shadowBlur=0}
  for(let k=pulses.length-1;k>=0;k--){const p=pulses[k];p.t+=dt*.8;if(p.t>=1){pulses.splice(k,1);continue}const X=xs[0]+(xs[p.to]-xs[0])*p.t;g.fillStyle=p.color;g.shadowColor=p.color;g.shadowBlur=22;g.beginPath();g.arc(X,y,5,0,7);g.fill();g.shadowBlur=0}}
/* neural shell */
let ang=0;const LAT=900;function drawNeural(dt){const cv=$('#neu');const [g,w,h]=fit(cv);g.clearRect(0,0,w,h);ang+=dt*(S&&S.online?.25:.08);
  const B=((S&&S.latest&&S.latest.bars)||[]).slice(-90),cx=w*0.58,cy=h*0.52,R=Math.min(w*0.26,h*0.36),r=R*0.42;
  const a=cur(),st=(a&&a.status)||{},tb=todayBars(),last=tb.length?tb[tb.length-1]:null,first=tb.length?tb[0]:null;
  const ds=a?dayStartOf(a):null,e=a?eqOf(a):null,floor=num(st.floor);const inputs=[['price vs open',last&&first?(last[4]/first[1]-1)*100:0,'%'],['position',num(st.position)||0,''],['open P&L',num(st.open_pnl)||0,'$'],['today',e!=null&&ds!=null?e-ds:0,'$'],['room',e!=null&&floor!=null?e-floor:0,'$'],['bars today',tb.length,'']];
  const pts=[];B.forEach((b,i)=>{const ret=b[4]/b[1]-1,u=i/Math.max(1,B.length)*Math.PI*2*3+ang,v=(i*2.399)%(Math.PI*2)+ang*.6;
   const X=(R+r*Math.cos(v))*Math.cos(u),Yy=(R+r*Math.cos(v))*Math.sin(u)*.42,Z=r*Math.sin(v)+(R+r*Math.cos(v))*Math.sin(u)*.3;pts.push({x:cx+X,y:cy+Yy-Z*.5,z:Z,ret,i})});
  pts.sort((p,q)=>p.z-q.z);
  // torus lattice (structure only, dim) so the shape reads like a shell; data dots are drawn on top
  for(let k=0;k<LAT;k++){const u=k*0.0613+ang,v=(k*2.399)%(Math.PI*2)+ang*.6,X=(R+r*Math.cos(v))*Math.cos(u),Yy=(R+r*Math.cos(v))*Math.sin(u)*.42,Z=r*Math.sin(v)+(R+r*Math.cos(v))*Math.sin(u)*.3,d=(Z+R)/(2*R);
   g.fillStyle=k%3?'rgba(54,214,255,'+(0.05+0.25*d)+')':'rgba(162,107,255,'+(0.05+0.25*d)+')';g.fillRect(cx+X,cy+Yy-Z*.5,1.4,1.4)}
  inputs.forEach((inp,k)=>{const y=18+k*(h-36)/5,x=8;g.fillStyle='#ffffff08';g.fillRect(x,y-10,w*0.2,22);g.fillStyle=C.dim;g.font='9px JetBrains Mono';g.fillText(inp[0].toUpperCase(),x+5,y-1);
   const v=inp[1];g.fillStyle=v>0?C.up:v<0?C.down:C.sub;g.font='bold 10px JetBrains Mono';g.fillText((inp[2]==='$'?sgn(v,0):inp[2]==='%'?(v>=0?'+':'')+v.toFixed(2)+'%':String(v)),x+5,y+9);
   const tgt=pts.length?pts[(k*13+Math.floor(ang*3))%pts.length]:{x:cx,y:cy};g.strokeStyle=(k%2?C.vi:C.cy)+'40';g.beginPath();g.moveTo(x+w*0.2,y);g.bezierCurveTo(w*0.32,y,cx-R*1.1,tgt.y,tgt.x,tgt.y);g.stroke()});
  pts.forEach(p=>{const d=(p.z+R)/(2*R),s=1.6+Math.min(4,Math.abs(p.ret)*2500);const col=p.ret>=0?C.up:C.down;g.globalAlpha=.35+.65*Math.max(0,Math.min(1,d));g.fillStyle=col;g.shadowColor=col;g.shadowBlur=8;g.beginPath();g.arc(p.x,p.y,s*(.6+.6*d),0,7);g.fill()});g.globalAlpha=1;g.shadowBlur=0;
  if(!B.length){g.fillStyle=C.dim;g.font='12px JetBrains Mono';g.fillText('no bars yet',cx-40,cy)}
  const p=num(st.position)||0,col=p>0?C.up:p<0?C.down:C.vi,t=(Date.now()%2400)/2400;g.strokeStyle=col;g.globalAlpha=.5*(1-t);g.beginPath();g.arc(cx,cy,R*.25+t*R*.9,0,7);g.stroke();g.globalAlpha=1}
/* ring */
let ringA={p:0,r:0};function drawRing(dt){const cv=$('#ring');const [g,w,h]=fit(cv);g.clearRect(0,0,w,h);ringA.p+=(ringV.p-ringA.p)*Math.min(1,dt*3);ringA.r+=(ringV.r-ringA.r)*Math.min(1,dt*3);
  const cx=w/2,cy=h/2,R1=w*0.42,R2=w*0.32,st=-Math.PI/2;g.lineCap='round';
  [[R1,ringA.p,C.up,9],[R2,ringA.r,ringA.r<.3?C.down:C.cy,6]].forEach(([R,v,c,lw])=>{g.strokeStyle='#ffffff10';g.lineWidth=lw;g.beginPath();g.arc(cx,cy,R,0,7);g.stroke();g.strokeStyle=c;g.shadowColor=c;g.shadowBlur=12;g.beginPath();g.arc(cx,cy,R,st,st+Math.PI*2*Math.max(.001,v));g.stroke();g.shadowBlur=0});
  g.fillStyle='#fff';g.font='800 '+Math.round(w*0.2)+'px JetBrains Mono';g.textAlign='center';g.fillText(Math.round(ringA.p*100),cx,cy+w*0.05);g.font=Math.round(w*0.065)+'px JetBrains Mono';g.fillStyle=C.dim;g.fillText('% to target',cx,cy+w*0.15);g.textAlign='left'}
/* loop */
let lt=performance.now(),chartT=0;function loop(now){const dt=Math.min(.1,(now-lt)/1000);lt=now;drawFlow(dt);drawNeural(dt);drawRing(dt);chartT+=dt;if(chartT>.05){drawChart();chartT=0}
  const t=et();$('#clock').textContent=String(t.h).padStart(2,'0')+':'+String(t.m).padStart(2,'0')+':'+String(t.s).padStart(2,'0')+' ET';requestAnimationFrame(loop)}
setInterval(()=>{if(S)renderAgents(accts(),cur(),et(),marketOpen(),!!S.online)},1000);
load();setInterval(load,5000);requestAnimationFrame(loop);window.addEventListener('resize',()=>{drawChart();drawSpark()});
</script></body></html>
'''
