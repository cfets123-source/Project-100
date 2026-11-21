# Multi-market scan v1: history result (2 October 2026)

**Question:** does scanning many markets (stocks, ETFs, leveraged ETFs, bonds, commodities, international, crypto) find a better $100 → $200 strategy than Stage Runner's single TQQQ rule?

**Method:**
- **Universe:** 143 symbols. Daily split-adjusted bars from Yahoo, 2010 to Sep 2026; crypto from 2014+.
- **Three frozen rules,** fixed before looking at results:
  - Trend start: close crosses into close > 50-day > 200-day average. Stop −10%, target +20%, 60-day limit, exit on a close below the 50-day.
  - Dip in uptrend: above the 200-day with 2-day RSI under 10. Stop −8%, target +6%, 10-day limit, exit on a close above the 5-day.
  - 20-day breakout: above the 200-day. Stop −7%, target +15%, 30-day limit.
- **Fills:** entry at the next open. Stop is checked before target on the same bar. Costs are 0.05% per side for US listings and 0.20% for crypto.
- **Periods:** development 2011–2020, holdout 2021 to Sep 2026.
- **Script:** `scan_bt.py` / `port.py` in the session research workspace.

## Per-trade results (all signals, every symbol)

Average trade results were positive in both periods for most rule and asset-group pairs, for example:

- Dip-in-uptrend on leveraged ETFs: +0.47%/trade (dev), +1.02% (holdout).
- Breakout on index ETFs: +0.98% / +0.86%.

The large-stock list is today's large companies, so it carries survivorship bias.

## As a $100 account holding one position at a time

The strongest 6-month-momentum signal was taken each time the account was flat.

| Strategy | Dev 2011–2020 end value (max drawdown) | Holdout 2021–Sep 2026 end value (max drawdown) |
|---|---|---|
| TQQQ only · trend rule | $128 (54%) | $124 (19%) |
| Dip-in-uptrend · leveraged ETFs | $116 (67%) | **$334 (27%)** |
| Dip-in-uptrend · leveraged + index ETFs | $110 (48%) | $160 (41%) |
| Trend · leveraged ETFs | **$481 (42%)** | $79 (54%) |
| Breakout · index ETFs | $163 (32%) | $130 (29%) |
| Breakout · stocks + crypto | $385 (44%) | $149 (45%) |
| All rules · all ETFs | $57 (54%) | $424 (24%) |

**Conclusion:** no rule and market combination did well in both decades as a single $100 position. Each period's winner was mediocre or losing in the other period. Searching more markets produced more candidates, not a reliable edge.

The next step is therefore a **watch-only forward scanner.** It records every live signal from these frozen rules across all markets and measures the outcomes going forward. Nothing is promoted to live trading without that forward evidence.
