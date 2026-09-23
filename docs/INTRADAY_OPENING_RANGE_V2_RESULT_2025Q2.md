# Intraday opening-range v2: complete holdout result

The frozen v2 evaluator used all 20 symbols' Alpaca IEX five-minute pages for April 1 through June 30, 2025: 99,553 bars, including June 30 for every symbol. The first fetch had silently stopped at Alpaca's first page despite requesting a 10,000-row limit; its partial-window result was discarded. The corrected adapter followed every `next_page_token` before this evaluation.

The complete run selected **231 simulated trades**, with **-10.78% compounded account return after the specified 0.1% round-trip cost**, **-12.06% maximum drawdown**, and **35.9% positive trades**. Exits were 55 targets, 129 stops, and 47 session closes. This fails the pre-registered positive-return gate. The candidate is ineligible for paper execution and live capital. The window must not be reused as an untouched test for a tuned version.
