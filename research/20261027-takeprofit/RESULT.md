# Take-profit test — 2026-10-27

Question: should the bot bank a profit at +$X and re-enter, instead of holding to its normal exit?
Data: QQQ 5-min 2019-01 → 2026-10-26 (proxy for MNQ), the bot's NOISE rules (hourly checks, 1% vol sizing,
2 contracts × vol scale). Scored on Topstep 50K Combine rules (target $3,000, $2,000 trailing MLL, bot stop $800,
$400 buffer, 50% consistency). "From today" = starting at the live account's position on 10/27 (−$439, $1,494 room).

| Version | Pass fresh DEV/CONF | Pass from today DEV/CONF | Median days | $/day |
|---|---|---|---|---|
| Current rules | 43% / 36% | 36% / 32% | 27 / 25 | 52 / 45 |
| **TP $600 + re-enter** | **49% / 39%** | **40% / 33%** | 29 / 22 | 41 / 38 |
| TP $400 (touch fill) | 49% / 42% | 38% / 36% | 30 / 26 | 40 / 29 |
| TP $400 (2-tick fill) | 49% / 37% | 38% / 30% | 31 / 27 | 39 / 26 |
| TP $250 | 45–46% / 50% | 36–37% / 40% | 31 / 36 | 27 / 25 |
| Daily lock $300–1,200 | 35–42% / 20–33% | 26–35% / 14–28% | | |
| Trail 50% after $200–700 | 35–45% / 36–42% | 27–38% / 28–34% | | |

Verdict: TP $600 is the only setting better in both periods and unchanged under stricter fills. Gain is modest
(+2–6 points pass rate). Daily profit locks hurt (they cut the trend days that carry the edge). Installed for
Combine accounts only (worker.TAKE_PROFIT_PER_50K = 600); funded accounts keep the current rules (higher $/day).
