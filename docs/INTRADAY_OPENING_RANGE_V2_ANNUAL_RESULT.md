# Opening-range v2: complete annual follow-up result

The unchanged, frozen 20-symbol v2 evaluator used all **406,786** Alpaca IEX five-minute bars from July 1, 2025 through June 30, 2026. All 20 symbol series reached June 30; the corrected adapter consumed every `next_page_token`. This is the sequential follow-up specified after the losing April–June 2025 quarter, so it is exploratory rather than a first-look out-of-sample test.

It selected **938 simulated trades**. Compounded modeled account return after the fixed 0.1% round-trip cost was **-39.46%**, with **-40.98% maximum drawdown** and **36.0% positive trades**. There were 510 stop exits, 191 target exits, and 237 session exits. The quarter results were 2025 Q3: 237 trades, -14.16%; 2025 Q4: 221 trades, -13.16%; 2026 Q1: 221 trades, -12.94%; and 2026 Q2: 259 trades, -6.72%.

The annual result fails the pre-specified positive-return and 15% maximum-drawdown thresholds. This test does not prove every intraday strategy is unprofitable. It establishes that this exact high-frequency hypothesis did not earn a paper or live promotion on the tested year. Its parameters and window should not be retuned and presented as a new untouched test.
