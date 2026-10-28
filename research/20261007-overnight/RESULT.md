# Overnight-hold test — result (7 October 2026): FAIL

The test held each ETF from the close to the next open, every day, at a realistic cost of 0.03% per side. The pass rule in PLAN.md was fixed before running.

| ETF | Period | Buy and hold | Overnight, 0.03%/side | Overnight, 0.01%/side (best case) | Intraday (open → close) |
|---|---|---|---|---|---|
| SPY | 2011–2020 | $359 (34% worst drop) | $53 (63%) | $146 (30%) | $33 |
| SPY | 2021–Sep 2026 | $226 (24%) | $67 (41%) | $118 (24%) | $60 |
| QQQ | 2011–2020 | $628 (29%) | $81 (46%) | $221 (28%) | $38 |
| QQQ | 2021–Sep 2026 | $249 (35%) | $74 (42%) | $132 (31%) | $60 |
| TQQQ | 2011–2020 | $5,660 (70%) | $732 (68%) | $2,003 (68%) | $38 |
| TQQQ | 2021–Sep 2026 | $385 (82%) | $107 (73%) | $191 (70%) | $64 |

The overnight pattern is real before costs: overnight beats intraday in every row. But paying the spread twice a day turns SPY and QQQ into money losers. TQQQ stays positive but falls far short of simply holding it. Holding all day captures the overnight gain anyway, with no daily trading costs. Decision: not adopted.
