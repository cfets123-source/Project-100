import httpx, json, time, sys
C=httpx.Client(timeout=20)
def fetch(sym, interval, start_ms):
    out=[]; t=start_ms
    while True:
        r=C.get("https://api.binance.us/api/v3/klines",params={"symbol":sym,"interval":interval,"startTime":t,"limit":1000}).json()
        if not r: break
        out+=r; t=r[-1][0]+1
        if len(r)<1000: break
        time.sleep(0.15)
    return out
for s in ("BTCUSD","ETHUSD","SOLUSD"):
    for iv in ("4h","1d"):
        rows=fetch(s,iv,1546300800000)  # 2019-01-01
        json.dump(rows,open(f"{s}_{iv}.json","w")); print(s,iv,len(rows), time.strftime('%Y-%m-%d',time.gmtime(rows[0][0]/1000)))
