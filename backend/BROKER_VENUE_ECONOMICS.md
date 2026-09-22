# Veloikos broker and venue economics — 2026-09-22

This is a research and integration plan, not a declaration that a route can
submit live orders. Account permissions, legal terms, data entitlement, exact
symbol support, order protections, and a full paper lifecycle must be verified
for each route. The live Alpaca system's current halt remains in force.

| Route | Useful coverage | Entry cost and constraints | Veloikos status |
| --- | --- | --- | --- |
| Alpaca Trading API | US stocks/ETFs; account-approved options and crypto | Stocks/ETFs commission-free; spread/slippage remain. Real-time OPRA is in the $99/month Algo Trader Plus data plan. | US equity/ETF route exists. Live crypto is inactive. Live OPRA request returned 403; options route is research only. |
| Robinhood Agentic Trading | Eligible US equities, ETFs, options and crypto | Stocks/ETFs and their options have no broker commission, but regulatory/options pass-through fees apply. Crypto routing may have 0–0.95% fees plus execution spread. | Dedicated account is unfunded. Codex MCP authorization does not authorize the deployed application; app OAuth and route validation remain. |
| Interactive Brokers Pro API | Direct foreign markets, US/global stocks, options, mutual funds and more | No account/inactivity minimum for Pro, but US equity tiered minimum $0.35/order, US options minimum $1/order, and selected German shares minimum €1.25/order, plus applicable third-party, FX and data costs. Market-data subscriptions require $500 account equity for an individual, plus subscription charges. | Not integrated or funded. IBKR Lite's commission-free account is **not API-eligible**. Pro is a later route when expected edge covers costs and data access is feasible. |
| E*TRADE developer API | Account data and manual order tools | Developer Terms §4.9 prohibit automated order generation without an affirmative instruction for each order. | Excluded from unattended execution. |

At $100, one $0.35 entry and $0.35 exit on IBKR Pro consumes at least $0.70,
or 0.7% of the account, before spreads and other charges. A hypothetical
$1.25 fee on each side consumes 2.5% before other costs. These examples
illustrate the order-minimum effect; actual foreign-currency fees must be
converted using a current FX quote. Multiple funded brokers would also need a
single cross-broker cash, exposure, and drawdown ledger before allocation.

The first expansion review is triggered only when broker-confirmed Project 100
equity exceeds $1,000. At that point, assess IBKR Pro account opening and
actual data subscriptions, paper-test its selected venue/order types, and
compare measured net expected return with existing Alpaca/Robinhood routes.
The review does not itself move money, subscribe to data, or enable execution.
Before a second broker receives capital, reconcile combined equity and
available cash across brokers, deduplicate exposure, and apply one global
loss limit. Review additional venues at later capital milestones using the
same measured net-return test.

For low-cost international **exposure**, US-listed international ETFs or ADRs
may be available through current US equity routes. They trade on US venues,
not the underlying Asian or European exchanges. Mutual funds use a daily NAV,
may impose purchase minimums or redemption terms, and are not an intraday
trading route. Direct foreign listings and mutual funds should therefore be
evaluated against their actual broker, fund, FX, tax, data, and order costs,
not placed into the current live scanner by default.

The `app.markets.venue_economics` module compares the **same proposed order**
across venues using an independently estimated gross profit and explicit
round-trip commission, spread, slippage, FX, and allocated market-data cost.
An unknown input or nonpositive expected net profit rejects the venue. This
is a tested library, not yet connected to the live worker. Next: connect
account-specific fee schedules and measured execution costs to a paper-only
candidate evaluator, then reconcile realized all-in P&L against its estimate.

Primary sources:

- Alpaca data plans: https://alpaca.markets/data
- Alpaca options: https://docs.alpaca.markets/us/docs/options-trading
- Robinhood agentic trading: https://robinhood.com/us/en/support/articles/trading-with-your-agent/
- Robinhood trading fees: https://robinhood.com/us/en/support/articles/trading-fees-on-robinhood/
- Robinhood crypto tiers: https://robinhood.com/us/en/support/articles/crypto-fee-tiers/
- IBKR API/Lite restriction: https://www.interactivebrokers.com/docs/third-party-integrations/general-third-party-frequently-asked-questions
- IBKR stocks: https://www.interactivebrokers.com/en/pricing/commissions-stocks.php
- IBKR options: https://www.interactivebrokers.com/en/pricing/commissions-options.php
- IBKR mutual funds: https://www.interactivebrokers.com/en/pricing/commissions-mutual-funds.php
- IBKR data minimums: https://www.interactivebrokers.com/en/pricing/market-data-pricing.php
- E*TRADE developer terms: https://developer.etrade.com/support/terms-of-use
