# Options data without a new paid subscription — September 24

Use the already-authorized Robinhood Agentic connection for current option quotes. A read-only production probe at 19:34 UTC returned a current SPY October 1, 2026 $770 call quote: bid $3.84, ask $3.88, sizes 118/130, age 0.378 seconds. The account reports options level 2. This single contract is a data diagnostic, not a trade recommendation; its $388 ask cost exceeds the current Alpaca account balance. No orders were sent and no subscription was purchased.

Evidence is in access.json. Existing route: `/brokers/robinhood/options/quote`; existing adapter supports chains, filtered contracts, bid/ask quotes, timestamp quality and contract multipliers. E*TRADE is not currently configured or authorized, so it is not an immediately working alternative.

Robinhood's official Agentic documentation lists real-time option quotes and option OHLC histories. Its options agreement describes OPRA quotation access. A current quote is not a complete historical OPRA bid/ask archive; historical bars must not be presented as executable historical spreads.

- https://robinhood.com/us/en/support/articles/trading-with-your-agent/
- https://cdn.robinhood.com/assets/robinhood/legal/Options%20Agreement.pdf

Tradier is a backup candidate: its Standard plan advertises $0/month and developer API access, and brokerage account holders receive consolidated real-time US options data. It requires a Tradier account and applicable market-data agreements. However, its fee schedule lists a $50/year inactivity fee for accounts below $2,000 with fewer than two trades per year. Its historical API does not retain expired options; daily candles are not historical bid/ask evidence. Opening a second account merely for data is therefore less attractive than the working Robinhood connection.

- https://join.tradier.com/try-tradier
- https://docs.tradier.com/docs/market-data
- https://docs.tradier.com/docs/exchange-codes
- https://docs.tradier.com/docs/historical-data
- https://tradier.com/pricing

The user explicitly chose to keep subscriptions free after Alpaca ticket 361195 stated OPRA requires Algo Trader Plus. No paid upgrade is authorized. Keep Alpaca's unsigned OPRA entitlement visible as unavailable; use the Robinhood quote route without pretending this signs or unlocks Alpaca OPRA. A no-cost comprehensive expired-option bid/ask archive remains unverified.
