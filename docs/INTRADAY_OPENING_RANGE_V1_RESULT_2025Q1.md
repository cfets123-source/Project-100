# Opening-range v1 independent-window result

The pre-registered 20-symbol strategy was evaluated once against Alpaca IEX five-minute bars from January 2 through March 31, 2025. The locked evaluator selected 72 completed simulated trades. Its modeled account return after the specified 0.1% round-trip cost was **-11.40%**, with **-11.40% maximum drawdown** and a **37.5% win rate**. There were 68 session exits and four stop exits; no target was reached. The result fails the pre-registered positive-return gate. The strategy is not eligible for paper execution or live capital.

This test uses IEX historical bars, which can omit market-wide trades and cannot prove real execution quality. The negative result is sufficient to reject this exact hypothesis without retuning its parameters on the same window.
