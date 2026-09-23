# Monthly whole-share ETF time-series momentum v1 result

The exact code and gate were frozen in `fa6b43f` before the requested older raw IEX history was fetched. The response began **July 27, 2020**, despite a January 2016 request, so the planned 2017–2021 robustness window cannot be evaluated. The raw cache SHA-256 was `bbbfff39af0fde6284d38e42ba278a1aff6e737d1a2d78a1f1f5b7fb8e8052d3`. The partial August–December 2021 period produced only three completed trades, too few to substitute for the predeclared five-year window.

| Period, $100 reset at start | Completed trades | Return at 0.1% modeled round-trip cost | Maximum drawdown | Return at 0.2% cost |
| --- | ---: | ---: | ---: | ---: |
| 2022–2024 | 33 | +8.13% | -27.70% | +5.63% |
| 2025–September 22, 2026 | 19 | +20.03% | -12.31% | +18.64% |

The recent period ended with an open marked position. There were no unaffordable entry months at either cost. The 2022–2024 drawdown breaches the frozen -25% limit, and the planned older robustness period is unavailable. The 2025–2026 result is encouraging **research evidence**, not a pass under the stated gate or proof of future returns. Most recent selections were FXI and EEM, U.S.-listed ETFs that provide foreign-market exposure rather than direct exchange access. Raw XLE and XLU bars showed large December 2025 price discontinuities; no recent completed trade in this model used those symbols, but a future broker path must reconcile corporate actions and GTC order adjustments explicitly.

No paper or live promotion is authorized for this exact version. A separately frozen risk-managed variant can be assessed, but the inspected 2022–2026 periods must be treated as development rather than fresh independent confirmation. Actual paper broker fills and stop/exit reconciliation are necessary before any live-capital review.
