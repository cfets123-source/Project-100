# Cross-market research batch, frozen September 24 before outcomes

Mandate: $100 toward $200–$500, then subsequent milestones. No invented deadline.
Screen actual account access separately from instrument/catalog availability.
No live orders, permission changes, cash transfers, or production approvals.

Fixed candidates, no parameter search:
1. Broad US equity: SPY, 200-session trend filter, month-end decisions.
2. Cross-asset ETF rotation: SPY, QQQ, IWM, EFA, EEM, TLT, IEF, GLD, DBC;
   highest positive 126-session price return above its 200-session average.
3. Direct-stock rotation: AAPL, MSFT, JPM, XOM, JNJ; same 126/200 rule.
4. Spot crypto rotation: BTC and ETH; highest positive 180-day price return
   above its 200-day average, month-end decisions. No shorts or leverage.

All start with $100 cash per window. 95% cash exposure in one selected asset.
US candidates use fractional quantity (research assumption, verify current
fractionability separately), crypto fractional quantity. Rank from completed
month-end close, sell old position first next session/open, and buy after T+3,
T+2 or T+1 settlement for equities; crypto can swap at next UTC-day open with
both legs charged. Remain in cash if no eligible symbol. Skip initial partial
month; no data after a decision may affect its signal. No stop or profit target;
monthly trend exits allow substantial losses between decisions. This is a
separate execution contract, not the existing fractional DAY-stop worker.

Use raw SIP bars and split-adjusted signals for securities, split-aware quantity
and entry accounting. Dividend cash omitted in this screening batch, clearly
label price returns. Raw Coinbase BTC/USD and ETH/USD candles are a venue proxy,
not verified Alpaca execution history. Crypto one-way cost 0.35% base (0.25%
published low-tier Alpaca taker fee plus assumed 0.10% spread/slippage), stress
0.75%. US one-way costs 0.05% base and 0.15% stress. Costs are assumptions beyond
published fees and do not model taxes. Cash earns zero. No extra deposits.

Fixed windows: 2018–2021, 2022–2024, 2025–2026-09-23 exclusive, with prior data
for at least 200 observations. Require complete official equity sessions and
complete UTC crypto days. Read coverage before any outcomes; missing data must
be repaired or the candidate marked unavailable, never quietly dropped.

Historical screen: positive account return in all 3 base-cost windows; no window
drawdown worse than 35%; recent stress-cost return positive; at least 12 completed
round trips over all windows. Record milestone touches separately, not as a
mandatory historical 2x/5x gate. Windows/universes are retrospectively chosen and
recent data were already inspected for other hypotheses: no claim of pristine
holdout. A pass identifies a research lead, not proof of future profit.

Compare with buy-and-hold of SPY and BTC at identical costs/capital, labeled
benchmarks, not optimized alternatives. Report terminal liquidation-equivalent
value, marked equity, worst drawdown, turnover, time in cash, $200/$500 touches,
and each parameter. Multiple tests require forward confirmation, not selecting
the luckiest path and claiming validation.

Options: inspect actual approval, OPRA access, and complete historical bid/ask
availability. Do not substitute underlying returns for option P&L. Direct bonds
and mutual funds: verify an actual adapter/account route; bond ETFs provide a
testable proxy exposure but are not direct bonds or mutual funds. Unsupported
markets remain explicit untested rows in the access matrix.
