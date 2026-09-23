# Weekly affordable momentum v1: raw-price research result

The exact rule and raw-price requirement were frozen in `ea3bdbe` before the result was read. The read-only Alpaca paper market-data request used IEX daily bars with `adjustment=raw` from January 2022 through September 22, 2026. The local raw cache SHA-256 was `fd1f0a9cbb55d3e222729a5d4392aa482e2d74d51d337cc20c7fe7349081a28c`. No broker order was submitted.

| Period | Completed trades | Modeled account return, 0.1% round-trip cost |
| --- | ---: | ---: |
| 2022 development | 14 | -18.18% |
| 2023 development | 20 | +7.36% |
| 2024 development | 20 | +8.88% |
| 2025 recent confirmation | 20 | -12.98% |
| 2026 through September 22 | 12 | +6.83% |
| 2025–2026 combined | 32 | -7.04% |

The recent window reached -20.53% maximum drawdown. Four candidate entry days had no affordable share at the modeled cash/exposure limit. The sample ended with an open marked position, so its final account return includes unrealized P&L. At 0.2% modeled cost, the path changed when fee-dependent affordability altered position selection; it returned +6.52% over the recent window with 31 completed trades. This is **not** favorable cost robustness: the sign reversal exposes how fragile the selected path is in a small whole-share account.

The strategy fails the frozen positive-return and drawdown gates. Its development years also vary substantially. It is not eligible for a paper execution worker or live capital. This research still excludes spread, market impact, actual broker fills, corporate actions beyond raw-price affordability, and portfolio effects from other accounts. The fixed current-symbol universe is subject to survivorship and affordability-selection bias.
