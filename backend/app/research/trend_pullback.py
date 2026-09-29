"""Research-only daily trend-pullback candidate."""
STRATEGY_VERSION="daily-trend-pullback-vol-targeted-v1"
def returns(bars):
 out=[]; pos=None
 for i in range(51,len(bars)-1):
  if pos:
   e,s,t=pos; row=bars[i]
   if float(row['low'])<=s: out.append(s/e-1-.001);pos=None
   elif float(row['high'])>=t: out.append(t/e-1-.001);pos=None
   continue
  close=float(bars[i]['close']); sma=sum(float(x['close']) for x in bars[i-50:i])/50; high=max(float(x['high']) for x in bars[i-6:i])
  if close>sma and close<=high*.985:
   e=float(bars[i+1]['open']);pos=(e,e*.97,e*1.06)
 return out
