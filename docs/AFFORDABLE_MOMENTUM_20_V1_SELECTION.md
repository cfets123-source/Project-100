# Selected candidate before recent confirmation

The bounded factor screen defined in `985f6fb` used only January 2022–December 2024 data to choose among ten rules. The selected exact rule is `momentum-20-all`: each Friday close, rank fixed-universe symbols with positive 20-session raw return from strongest to weakest, then buy the highest-ranked affordable whole-share symbol at the next session open. It does not use a moving-average filter. All cash, stop, target, holding, gap, cost, and one-position assumptions remain those frozen in the screen plan and evaluator. This selection is named `weekly-affordable-momentum-20-whole-share-v1` for any future paper path.

| Development-only rule | Trades | Modeled return | Maximum drawdown |
| --- | ---: | ---: | ---: |
| momentum-20-all **selected** | 51 | +35.77% | -14.30% |
| momentum-20-trend | 50 | +27.03% | -15.31% |
| momentum-63-all | 56 | -7.87% | -26.68% |
| momentum-63-trend | 54 | -4.36% | -22.91% |
| momentum-126-all | 51 | +18.26% | -23.56% |
| momentum-126-trend | 48 | +7.22% | -21.94% |
| reversal-5-all | 51 | +2.36% | -25.55% |
| reversal-5-trend | 47 | +16.42% | -15.52% |
| reversal-20-all | 54 | +3.08% | -27.86% |
| reversal-20-trend | 42 | -11.14% | -24.76% |

The recent window has not been evaluated for this screen or selected rule at the time this selection is committed. It will be run once at 0.1% and 0.2% costs, starting with $100 cash and indicator warmup from prior bars. The existing historical reuse and fixed current-symbol biases still apply. A historical pass would only justify building the exact-version paper worker and collecting broker fills and stop/exit reconciliation.
