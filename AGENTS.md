# Project 100 working instructions

## Objective

Build Veloikos to pursue growth of a **$100 trading account to $1,000,000 within one year**. Work through account-equity waypoints: **$100 → $500 → $1,000 → $5,000 → $10,000 → $100,000 → $200,000/$300,000 → $500,000 → $1,000,000**. Gains at one stage fund the next. Count net broker account equity after fees and losses; do not count deposits, a single contract's percentage gain, paper profits, or an unfilled order as a reached milestone.

Treat this as an aggressive growth research and product objective. Do not silently replace it with a low-volatility preservation objective or assume the present 1%-per-trade live default is the right research target. Each stage may need a different instrument, strategy, account risk, trade frequency, and broker. High volatility and substantial drawdowns are acceptable **research scenarios** to quantify. They do not, by themselves, establish an edge.

## How to work

1. Start with the next unreached waypoint and its time budget. State the required account-level growth and identify broker routes that can actually trade at that balance. Prioritize high-upside, bounded-loss setups that fit the account; do not limit discovery to the current daily pullback worker or its five default symbols.
2. Convert any promising trading model, including one demonstrated on social media, into explicit entry, sizing, exit, and invalidation rules. Record what is verified versus self-reported. Freeze each candidate and its cost assumptions before measuring returns; preserve negative and positive results.
3. Compare **net daily account returns**, including idle days, with both the current waypoint and the full remaining ladder. Test aggressive sizing scenarios as scenarios, including the possibility of exhausting the account. Measure opportunity count, turnover, fees, spread, drawdown, and how often capital cannot fund the next trade. A high trade count or one lucky run is insufficient on its own; a losing period alone does not prove every other rule will fail.
4. Use development and later untouched or forward periods. A candidate that earns further work gets the exact-code paper lifecycle and broker quote/fill/exit evidence. If historical executable quotes are unavailable, build read-only forward collection or the required broker adapter; do not substitute underlying prices for option returns.
5. Promote an exact strategy version to live only after checking current broker permissions, account funding, market data, order sizing, protective exit, duplicate-order prevention, ledger reconciliation, and the account's actual operating state. Distinguish an **economic rule** from these order-safety controls. Do not treat a prior validation of a different rule, route, or risk level as approval for a new one.
6. Carry authorized work to a concrete result in each turn. Report what passed, what failed, what is deployed, and the next specific obstacle. Do not claim a guaranteed path to the dollar goal or label an untested candidate profitable.

## Current implementation boundary

The existing live Alpaca worker uses a one-position daily pullback rule even though configuration permits two positions. Core settings default to 1% risk per trade and 50% maximum position value. Those settings are **current implementation choices**, not the Project 100 ambition. A new aggressive strategy must have its own version and measured account-return record. Do not increase live caps, remove protective exits, or reset a halt merely to make a backtest or dashboard appear active. Keep credentials and private account data out of source control.

See [milestone strategy gate](docs/GOAL_FIRST_STRATEGY_GATE.md), [risk/strategy audit](docs/AGGRESSIVE_STRATEGY_AND_RISK_AUDIT_2026_09_23.md), and the candidate-specific result files in `docs/`.
