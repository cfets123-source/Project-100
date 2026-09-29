# Florida crypto route — verified September 24, 2026

Binance.US Advanced (Spot) Trading is the best fee fit among the routes researched for this account size. This is a venue recommendation, not a finding of a profitable strategy or an activated account.

Alpaca support ticket 359105 explicitly confirms crypto trading is unavailable to Florida residents. Its inactive status is therefore an eligibility restriction, not a missing switch in Veloikos. Do not try to repair it by changing account flags.

## Verified route and costs

- Binance.US lists Florida among supported states without a crypto-only restriction: https://support.binance.us/en/articles/9842798-list-of-supported-and-unsupported-states-and-regions
- Advanced spot fees: 0% maker, 0.02% taker on most pairs, no subscription or minimum volume. These rates do not apply to One Click Buy/Sell: https://blog.binance.us/zero-fee-trading/
- ACH deposits and withdrawals are free. Card deposits cost 3.99%, wire withdrawals $25, and crypto withdrawal fees vary: https://www.binance.us/fees
- A $100 taker fill therefore costs $0.02 in trading fees; a hypothetical $100 buy plus $100 sell costs $0.04, excluding spread, slippage, and price movement. Maker fills have zero explicit trading fee but can remain unfilled or be adversely selected.
- Official API supports REST and WebSocket access. LIMIT_MAKER rejects an order that would immediately trade as a taker; an ordinary LIMIT order does not ensure maker treatment: https://docs.binance.us/

Public API observation at 2026-09-24 19:23 UTC is saved in binance-public-probe.json. BTCUSD and ETHUSD both returned TRADING, spot trading allowed, and LIMIT_MAKER support. Both have a $1 minimum-notional filter. BTC quantity increment is 0.00001 and ETH increment is 0.0001; rounding means the actual minimum may exceed $1. This was a public-data check, not an authenticated account or order test. Top-of-book snapshots are not durable liquidity or future fill guarantees.

## Alternatives checked

Robinhood offers a commission-free market-maker route, but currently discloses $0.95 per $100 order volume received from market makers and included in the spread. That is not equivalent to free execution. Exchange-routed trades use fee tiers. https://robinhood.com/us/en/support/articles/360022216832/

Coinbase Advanced has API access without a subscription, but charges volume-based trading fees; the exact account tier is shown after sign-in. https://help.coinbase.com/en/coinbase/trading-and-funding/advanced-trade/advanced-trade-fees

Kraken Pro is available in Florida and has an API, but charges trading fees. Its July 2026 low-volume tier change makes older comparisons unreliable. https://www.kraken.com/features/fee-schedule

## Implementation handoff

The user needs a verified Binance.US account before private API access can be checked. Basic Verification is required for API Management: https://support.binance.us/en/articles/9842800-how-to-create-an-api-key-on-binance-us

There is no Binance.US account connection or execution adapter in the deployed app yet. Keep Alpaca for its supported securities route; implement Binance.US as a separate broker/account scope. Do not point an Alpaca adapter at Binance.US or carry Alpaca strategy approval across venues.

Next engineering work: encrypted credential setup, authenticated read-only balance/fee/permission checks, symbol filters using Decimal arithmetic, order reconciliation and restart behavior, then venue-specific paper execution with maker nonfills and taker exits charged realistically. Do not assume every historical candle touch fills a maker order. A zero-fee-only exit can remain unfilled, so urgent exits require an explicit taker-cost assumption. The existing crypto rotation failed the historical screen; reducing fees alone does not establish an edge.

## OPRA support request

Sent from the account email to support@alpaca.markets on September 24 at 19:23:21 UTC, subject “OPRA agreement unavailable in active Level 3 options account.” Sent message ID: 1a0d4df55a37b99a. Gmail read-back verified SENT and exact body. Asked for the OPRA signing path and paid-data requirements, acknowledged the Florida crypto answer, and explicitly requested no subscription enrollment or trading-permission changes. OPRA remains unsigned pending resolution.
