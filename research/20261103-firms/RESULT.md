# Strategy & firm research — 2026-10-27 → 2026-11-03

Data: QQQ 5-min 2019-01 → 2026-10-26 (MNQ proxy), daily gold + 13 FX pairs 2010 → 2026-10-29. Live bot rules:
NOISE hourly checks, 1% vol sizing, +$600 take-profit (resting at the broker), $800 daily stop. Scoring: pass % on the
firm's rules, 2019-23 vs 2024-26, from the live account's state where noted.

## Changes tested on the live rules (all rejected unless noted)
- Take-profit +$600 + re-entry: ADOPTED (only TP size better in both periods, robust to 2-tick fills).
- Volume filters (need high volume / skip frenzy): no robust gain.
- More trades: smaller breakout k=0.8/0.6, 30-min checks: worse.
- Exit checks every 5/15/30 min: worse; one extra 3:25 exit check: mixed (−2 / +8 pts), not adopted.
- No entries at/after 3:00 or 1:00: worse.
- False-breakout guardrails: k=1.2/1.5, 2-check confirmation, 20-day trend filter: none better in both periods.
- Other markets DIA/USO/IEF/SLV/UNG (+ earlier SPY/IWM/GLD): none pass both periods.
- SMC sweep→MSS→FVG retest 1:3 on Nasdaq 5-min: loses (5% of trades reach 3R).
- Alex G "set and forget" daily gold/FX: rules, 7-point checklist and blind chart judgment — no edge over 16 years.

## Firm rules (same bot, 7-yr sim, pass % 2019-23 / 2024-26)
| Firm | Cost | Pass | Typical days |
|---|---|---|---|
| Topstep 50K (trailing MLL), from 11/03 state | paid | 36 / 32 | ~25-32 |
| Eightcap 1-step $5K, 3x (static 8%) | ~$55 | 69 / 57 | ~40-44 |
| Goat Funded Trader 2-step $5K, 3x (static 10%) | ~$33-52 | 62 / 65 | ~59-69 |
| Maven 2-step $2K, 3x (static 8%) | $19 | 63 / 57 | ~48-61 |
| Maven 3-step $2K (3% static) | $13 | 9-20 | — |

Conclusion: the biggest lever is a static (non-trailing) max loss, which is how fxalexg runs his ladder (Eightcap).
