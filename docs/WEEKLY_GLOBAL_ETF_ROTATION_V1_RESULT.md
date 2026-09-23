# Weekly global ETF rotation v1: fixed-rule result

The 14-symbol, raw-price, whole-share weekly momentum rule was frozen in `d62e670` before the ETF price pull. Its 2022–2024 development period returned **-14.60%**. Its 2025–September 22, 2026 period completed 34 trades, returned **-21.03%** at 0.1% modeled roundtrip cost, and reached **-29.28%** maximum drawdown.

This candidate failed before any paper or live allocation. The model uses U.S.-listed ETFs, including funds with foreign holdings; it does not provide direct execution on foreign exchanges. Its historical periods were subsequently inspected while developing the slower monthly variant and no longer constitute untouched confirmation for that variant.
