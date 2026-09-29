from app.research.monthly_etf_rotation import monthly_returns, UNIVERSE
def test_cash_when_no_etf_is_above_trend():
 bars=[{'timestamp':f'2023-{(i//20)+1:02d}-{(i%20)+1:02d}T00:00:00Z','open':100-i*.1,'close':100-i*.1} for i in range(260)]
 assert monthly_returns({s:list(bars) for s in UNIVERSE},'2023-01-01') == []
