# Opening-range v1 independent-window result

The pre-registered 20-symbol strategy was evaluated against Alpaca IEX five-minute bars from January 2 through March 31, 2025. An initial run unknowingly used only the first page returned by Alpaca for each symbol. Its 72-trade result was incomplete and is superseded here. The corrected read-only adapter followed all `next_page_token` values, producing **93,953 bars through March 31 for all 20 symbols**.

On the complete window, the unchanged evaluator selected **112 simulated trades**. Modeled account return after the specified 0.1% round-trip cost was **-15.36%**, maximum drawdown **-18.15%**, and the positive-trade rate **37.5%**. There were 107 session exits, five stop exits, and no targets. The strategy fails both the positive-return and maximum-drawdown gates. It is not eligible for paper execution or live capital. The persisted validation record must reflect this corrected complete-window result.

This test uses IEX historical bars, which can omit market-wide trades and cannot prove real execution quality. The negative result is sufficient to reject this exact hypothesis without retuning its parameters on the same window.
