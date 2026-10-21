PROP_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Prop Challenge · Veloikos</title>
<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#07090b"><link rel="apple-touch-icon" href="/static/icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<style>
:root{--bg:#07090b;--panel:#0d1014;--panel2:#12161b;--line:#1d232b;--ink:#e6e8ea;--sub:#7d8590;--up:#0ecb81;--down:#f6465d;--acc:#ff7a1a;--gold:#f0b90b;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--acc);text-decoration:none}button{font:inherit;color:inherit;cursor:pointer}
.top{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:10px;padding:max(10px,env(safe-area-inset-top)) 14px 10px;background:#090c0f;border-bottom:1px solid var(--line)}
.top h1{font-size:16px;margin:0;font-weight:700}.top a{font-size:13px}
.pill{font:700 11px var(--mono);letter-spacing:.08em;padding:4px 8px;border-radius:4px;background:#1d232b;color:var(--sub)}
.pill.live{background:rgba(14,203,129,.15);color:var(--up)}.pill.dry{background:rgba(240,185,11,.15);color:var(--gold)}.pill.off{background:rgba(246,70,93,.15);color:var(--down)}
.beat{margin-left:auto;font:12px var(--mono);color:var(--sub);white-space:nowrap}
.wrap{max-width:900px;margin:0 auto;padding:12px;display:grid;gap:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:14px}
.lbl{font:600 11px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--sub)}
.hero{display:grid;grid-template-columns:1.4fr 1fr 1fr;gap:10px}.hero b{display:block;font:700 22px var(--mono);margin-top:4px}
.hero .main b{font-size:28px}
.up{color:var(--up)}.down{color:var(--down)}.muted{color:var(--sub)}
.prog{position:relative;height:12px;border-radius:6px;background:#1d232b;margin:14px 0 6px;overflow:visible}
.prog i{position:absolute;left:0;top:0;bottom:0;border-radius:6px;background:linear-gradient(90deg,var(--acc),var(--up))}
.prog em{position:absolute;top:-5px;width:2px;height:22px;background:var(--down)}
.row{display:flex;justify-content:space-between;gap:10px;font:12px var(--mono);color:var(--sub)}
.pos{display:flex;align-items:center;gap:14px;flex-wrap:wrap}.side{font:800 20px var(--mono);padding:6px 12px;border-radius:5px;background:#1d232b}
.side.long{background:rgba(14,203,129,.15);color:var(--up)}.side.short{background:rgba(246,70,93,.15);color:var(--down)}
.pos b{font:700 18px var(--mono)}.pos small{display:block;color:var(--sub);font-size:11px}
.chart{position:relative;height:300px;margin:8px -4px 0}canvas{display:block;width:100%;height:100%}
.msg{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--sub);text-align:center;padding:20px}
.ev{display:grid;grid-template-columns:62px 1fr auto;gap:10px;padding:10px 0;border-bottom:1px solid var(--line);font-size:14px}.ev:last-child{border:0}
.ev time{font:12px var(--mono);color:var(--sub)}.ev .k{font:700 11px var(--mono);text-transform:uppercase}
.k.buy{color:var(--up)}.k.sell{color:var(--down)}.k.flat{color:var(--sub)}.k.halt,.k.error{color:var(--gold)}.k.pass{color:var(--acc)}
.note{padding:10px 12px;border-radius:5px;background:var(--panel2);font-size:13px;margin-top:10px}
.pair code{display:block;margin:10px 0;padding:10px;border-radius:5px;background:#000;font:13px var(--mono);word-break:break-all;color:var(--gold)}
.btn{background:var(--acc);border:0;border-radius:6px;padding:10px 14px;font-weight:700;color:#000}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.stats b{display:block;font:700 16px var(--mono);margin-top:3px}
@media(max-width:620px){.hero{grid-template-columns:1fr 1fr}.hero .main{grid-column:1/-1}.stats{grid-template-columns:1fr 1fr}.chart{height:240px}}
</style></head><body>
<header class="top"><a href="/dashboard">← Main</a><h1>Prop Challenge</h1><span id="mode" class="pill">…</span><span id="beat" class="beat"></span></header>
<main class="wrap">
<section class="card hero"><div class="main"><span class="lbl">Account balance</span><b id="bal">—</b><span id="acct" class="muted" style="font-size:12px"></span></div>
<div><span class="lbl">Today</span><b id="today">—</b></div><div><span class="lbl">Open P&amp;L</span><b id="opl">—</b></div></section>
<section class="card"><div class="row"><span class="lbl">Challenge progress</span><span id="toGo"></span></div>
<div class="prog"><i id="progBar" style="width:0"></i><em id="floorMark" style="left:0"></em></div>
<div class="row"><span id="pStart">Start</span><span id="pTarget">Target</span></div><div id="guard" class="note muted">Waiting for the bot…</div></section>
<section class="card"><span class="lbl">Position · <span id="ctr">MNQ</span></span>
<div class="pos" style="margin-top:10px"><span id="side" class="side">FLAT</span><div><small>Contracts</small><b id="qty">0</b></div><div><small>Price</small><b id="px">—</b></div><div><small>Open P&amp;L</small><b id="opl2">—</b></div></div>
<div class="chart"><canvas id="cv"></canvas><div id="cmsg" class="msg">Chart appears when the bot reports today's 5-minute bars.</div></div></section>
<section class="card"><span class="lbl">Stats</span><div class="stats" style="margin-top:8px"><div><span class="muted" style="font-size:12px">Trades today</span><b id="sT">0</b></div><div><span class="muted" style="font-size:12px">Winning trades</span><b id="sW">—</b></div><div><span class="muted" style="font-size:12px">Best trade</span><b id="sB">—</b></div><div><span class="muted" style="font-size:12px">Worst trade</span><b id="sL">—</b></div></div></section>
<section class="card"><span class="lbl">Activity</span><div id="evs"><div class="muted" style="padding:10px 0">No activity yet.</div></div></section>
<section class="card pair"><span class="lbl">Connect your Mac</span><p class="muted" style="font-size:13px">The bot trades from your Mac (Topstep rule) and reports here. Pair once; a new code replaces the old one.</p>
<button id="pairBtn" class="btn" type="button">Get pairing code</button><div id="pairOut"></div></section>
</main>
<script>
const q=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num=v=>{let n=Number(v);return v!=null&&Number.isFinite(n)?n:null};
const money=v=>num(v)==null?'—':num(v).toLocaleString('en-US',{style:'currency',currency:'USD'});
const signed=v=>num(v)==null?'—':(num(v)>=0?'+':'−')+Math.abs(num(v)).toLocaleString('en-US',{style:'currency',currency:'USD'});
const cls=v=>num(v)==null?'muted':num(v)>=0?'up':'down';
let S=null;
async function load(){try{let r=await fetch('/prop/state',{credentials:'same-origin'});if(r.status===401||r.redirected){location.href='/login';return}S=await r.json();render()}catch(e){q('#beat').textContent='connection problem — retrying'}}
function render(){let L=S.latest||{},st=L.status||{},cs=st.state||{};let mode=q('#mode');
if(!S.paired){mode.textContent='NOT PAIRED';mode.className='pill off'}else if(!S.online){mode.textContent='OFFLINE';mode.className='pill off'}else if(L.orders){mode.textContent='LIVE ORDERS';mode.className='pill live'}else{mode.textContent='DRY RUN';mode.className='pill dry'}
let a=S.heartbeat_age_s;q('#beat').textContent=a==null?'no report yet':(a<90?'● '+a+'s ago':'last report '+(a<3600?Math.round(a/60)+'m':Math.round(a/3600)+'h')+' ago');q('#beat').style.color=S.online?'var(--up)':'var(--sub)';
let bal=num(st.balance),opl=num(st.open_pnl)||0,start=num(cs.start_balance)||50000,target=start+3000,floor=num(st.floor),eq=bal==null?null:bal+opl,dayStart=num(cs.day_start_balance);
q('#bal').textContent=money(eq);q('#acct').textContent=L.account||'';q('#ctr').textContent=L.contract||'MNQ';
let td=eq!=null&&dayStart!=null?eq-dayStart:null;q('#today').innerHTML='<span class="'+cls(td)+'">'+signed(td)+'</span>';
q('#opl').innerHTML='<span class="'+cls(st.position?opl:null)+'">'+(st.position?signed(opl):'—')+'</span>';q('#opl2').innerHTML=q('#opl').innerHTML;
let lo=Math.min(floor??start-2000,start-2000),span=target-lo,P=v=>Math.max(0,Math.min(100,(v-lo)/span*100));
if(eq!=null){q('#progBar').style.width=P(eq)+'%';q('#toGo').innerHTML=cs.passed?'<span class="up">TARGET REACHED</span>':money(target-eq)+' to target'}
if(floor!=null)q('#floorMark').style.left=P(floor)+'%';q('#pStart').textContent='Loss limit '+money(floor);q('#pTarget').textContent='Target '+money(target);
let g=q('#guard');g.className='note '+(st.allowed===false?'down':'muted');g.textContent=cs.passed?'Challenge passed — request your funded account on Topstep.':(st.note?st.note:(eq!=null&&floor!=null?money(eq-floor)+' above the trailing loss limit. Bot stops for the day at −$800 and for good within $400 of the limit.':'Waiting for the bot…'));
let pos=num(st.position)||0,side=q('#side');side.textContent=pos>0?'LONG':pos<0?'SHORT':'FLAT';side.className='side '+(pos>0?'long':pos<0?'short':'');q('#qty').textContent=Math.abs(pos);q('#px').textContent=num(st.price)!=null?num(st.price).toFixed(2):'—';
let evs=S.events||[],today=new Date().toDateString(),trades=evs.filter(e=>(e.kind==='sell'||e.kind==='buy'||e.kind==='flat')&&new Date(e.time).toDateString()===today);
let closed=evs.filter(e=>num(e.pnl)!=null&&new Date(e.time).toDateString()===today).map(e=>num(e.pnl));
q('#sT').textContent=trades.length;q('#sW').textContent=closed.length?closed.filter(x=>x>0).length+' / '+closed.length:'—';q('#sB').innerHTML=closed.length?'<span class="up">'+signed(Math.max(...closed))+'</span>':'—';q('#sL').innerHTML=closed.length?'<span class="down">'+signed(Math.min(...closed))+'</span>':'—';
q('#evs').innerHTML=evs.length?evs.slice(0,40).map(e=>'<div class="ev"><time>'+esc(new Date(e.time).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'}))+'</time><div><span class="k '+esc(e.kind)+'">'+esc(e.kind)+'</span> '+esc(e.text)+'</div><span class="'+cls(e.pnl)+'">'+(num(e.pnl)!=null?signed(e.pnl):'')+'</span></div>').join(''):'<div class="muted" style="padding:10px 0">No activity yet.</div>';
draw(L.bars||[],evs.filter(e=>num(e.price)!=null))}
const cv=q('#cv'),ctx=cv.getContext('2d');
function draw(bars,marks){let dpr=devicePixelRatio||1,W=cv.clientWidth,H=cv.clientHeight;cv.width=W*dpr;cv.height=H*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);q('#cmsg').style.display=bars.length?'none':'flex';if(!bars.length)return;
let ax=62,pw=W-ax,ph=H-20,lo=Math.min(...bars.map(b=>b[3])),hi=Math.max(...bars.map(b=>b[2]));let pad=(hi-lo)*.08||1;lo-=pad;hi+=pad;let Y=v=>6+(hi-v)/(hi-lo)*(ph-12),n=bars.length,st=pw/n,bw=Math.max(1,Math.min(9,st*.7)),X=i=>i*st+st/2;
ctx.font='11px ui-monospace,Menlo,monospace';ctx.fillStyle='#7d8590';ctx.strokeStyle='#161b21';for(let k=0;k<=4;k++){let v=lo+(hi-lo)*k/4,y=Math.round(Y(v))+.5;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(pw,y);ctx.stroke();ctx.fillText(v.toFixed(2),pw+6,y+4)}
bars.forEach((b,i)=>{let up=b[4]>=b[1],c=up?'#0ecb81':'#f6465d',x=Math.round(X(i))+.5;ctx.strokeStyle=c;ctx.beginPath();ctx.moveTo(x,Y(b[2]));ctx.lineTo(x,Y(b[3]));ctx.stroke();let t=Y(Math.max(b[1],b[4])),bt=Y(Math.min(b[1],b[4]));ctx.fillStyle=c;ctx.fillRect(x-bw/2,t,bw,Math.max(1,bt-t))});
let t0=new Date(bars[0][0]).getTime(),t1=new Date(bars[n-1][0]).getTime();marks.forEach(m=>{let t=new Date(m.time).getTime();if(t<t0||t>t1+300000)return;let i=Math.min(n-1,Math.round((t-t0)/((t1-t0)/(n-1||1)))),x=X(i),y=Y(num(m.price)),buy=m.kind==='buy';ctx.fillStyle=buy?'#0ecb81':m.kind==='sell'?'#f6465d':'#ff7a1a';ctx.beginPath();if(buy){ctx.moveTo(x,y+4);ctx.lineTo(x-6,y+14);ctx.lineTo(x+6,y+14)}else{ctx.moveTo(x,y-4);ctx.lineTo(x-6,y-14);ctx.lineTo(x+6,y-14)}ctx.fill()});
let last=bars[n-1][4],ly=Math.round(Y(last))+.5;ctx.setLineDash([3,3]);ctx.strokeStyle='#ff7a1a';ctx.beginPath();ctx.moveTo(0,ly);ctx.lineTo(pw,ly);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle='#ff7a1a';ctx.fillRect(pw+1,ly-8,ax-2,16);ctx.fillStyle='#000';ctx.fillText(last.toFixed(2),pw+5,ly+4);
ctx.fillStyle='#7d8590';[0,Math.floor(n/2),n-1].forEach(i=>ctx.fillText(new Date(bars[i][0]).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'}),Math.max(0,Math.min(pw-50,X(i)-20)),H-4))}
q('#pairBtn').onclick=async()=>{if(S&&S.paired&&!confirm('A new code disconnects the Mac until you run the new command. Continue?'))return;try{let r=await fetch('/prop/pair',{method:'POST',credentials:'same-origin'});let d=await r.json();q('#pairOut').innerHTML='<p class="muted" style="font-size:13px">On your Mac, open Terminal and run:</p><code>bash ~/p100-prop/pair.sh '+esc(d.token)+'</code><p class="muted" style="font-size:12px">This code is shown once.</p>'}catch(e){q('#pairOut').textContent='Could not create a code — try again.'}};
new ResizeObserver(()=>S&&render()).observe(cv);load();setInterval(load,5000);
</script></body></html>'''
