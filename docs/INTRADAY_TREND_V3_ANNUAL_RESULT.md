# Intraday trend-pullback v3: annual follow-up

The unchanged `intraday-liquid-trend-pullback-portfolio-v3` evaluator was run against the complete 20-symbol, paginated Alpaca IEX five-minute dataset from July 1, 2025 through June 30, 2026. It models two slots at 40% allocation each, next-bar entries, a 0.75% stop, a 1.5% target, a 0.1% round-trip cost, a daily loss lockout, and same-session exits. The data had already been inspected for other intraday candidates, so this is an exploratory long-horizon comparison, not untouched validation.

It generated **954 completed trades**, **-23.67% compounded modeled account return**, **-25.36% maximum drawdown**, and 38.5% positive trades. Each quarter was negative: Q3 2025 had 241 trades and -3.76%; Q4 2025 had 237 and -2.29%; Q1 2026 had 235 and -10.76%; Q2 2026 had 241 and -9.05%.

The earlier two-month loss therefore was not the sole reason to withhold this candidate. Its fixed rules also lost over the full year. This result does not rule out other intraday hypotheses, but this version has no evidence for a paper or live promotion.
