# Veloikos / Project 100 audit — September 24, 2026

The project has both scope drift and genuine execution defects. Stronger wording alone will not fix it. The existing AGENTS.md already specifies aggressive growth. The necessary correction is a consistent release contract, repair of account supervision, and an implemented milestone workflow. The immediate strategy question is whether an executable candidate can serve the first $200–$500 milestone, followed by liquidation and a separately evaluated next stage. The inspected evidence has not established that first-stage candidate.

## Scope and evidence

Read-only source review of the Project-100 checkout referenced in the workspace AGENTS.md, at git HEAD `7ed0153`, including existing uncommitted research changes. The Veloikos workspace originally contained only `.git`. The old task was idle when inspected. No deployment, broker balance, current open orders, or current positions was verified in this audit. No orders, halt resets, execution flags, or production services were changed. File fingerprints and an AST extraction of the risk-input defect are in `source-evidence.json`.

The September 24 repository test report records 383 passing tests from an isolated container. This audit did not rerun that suite and does not claim those tests cover the defects below. The same report notes an older deployed image; source tests alone do not establish deployed behavior.

## Findings, ordered by priority

### P1 — Loss limits receive hardcoded zero losses

`backend/app/runtime/alpaca_live_worker.py:74-78` passes literal zero daily P&L, weekly drawdown, and total drawdown into ExecutionGateway. It also supplies a fixed $5 million average dollar volume. The gateway builds TradeProposal directly from that context; the risk engine compares those supplied values against configured loss limits. Aggregate reservation checks constrain pending exposure, but do not reconstruct cumulative realized account losses.

Consequence: if this entry path is enabled, a history of actual losses will not trigger these specific loss checks through the supplied inputs. Current upstream strategy locks may prevent reaching this path; that does not repair it.

Repair: reconcile account equity/cash flows and persist session, week, and high-water-mark baselines; construct measured risk inputs, reject unknown/stale values, and supply observed liquidity. Prove entry rejection after real modeled account losses, across restarts and deposits/withdrawals.

### P1 — A shared paper/live state can stop the wrong account

`backend/app/services/state_machine.py` uses the singleton primary key `current`. `compose.host.paper.yml` points paper and live services to the same `sqlite:////data/paper.db` volume. The September 22 incident report records a paper protective-stop failure halting the shared state and stopping the live worker while a live ORCL position remained open.

Repair: account-and-mode-scoped state, with an explicit migration preserving every old halt. A separate intentional global emergency control can remain. Verify that a paper failure cannot change live-account state, reservations, or supervision.

The incident document reports an exit as pending at the time it was written; it does not establish a currently open position. Fresh broker reconciliation is required before any current-position claim.

### P1 — Entry approval blocks existing-position management

`alpaca_live_worker.py:42` loads the finally authorized adapter before protection checks, session-close management, and position management. `alpaca_live_execution.py` rejects non-LIVE state, failed strategy validation, and the listed holding-period mismatches before returning that adapter. The separate live reconciliation worker polls broker state but is explicitly read-only.

Consequence: loss of entry eligibility can prevent this worker from managing existing exposure. Broker-held stops may still operate, but software supervision is not independent. A separate emergency-exit helper exists; it is not a continuously running substitute in the inspected compose configuration.

Repair: separate entry eligibility from restricted existing-position supervision. Keep account/mode authentication and exposure-reducing constraints. Test halted entries, revoked strategy approval, stop expiry, partial fills, network ambiguity, and process restart without opening additional exposure.

### P1 — Backtested holding periods differ from executable holding periods

The current Alpaca boundary explicitly blocks four pullback strategy versions with `strategy_execution_horizon_mismatch_fractional_day_stop`. Historical tests permit overnight holdings; the fractional worker closes near session end to avoid expired DAY protection. These are different strategies. Removing the error would conceal that mismatch.

Alpaca's current fractional-trading documentation describes fractional market, limit, stop, and stop-limit orders with DAY time in force: https://docs.alpaca.markets/us/docs/fractional-trading . That supports the time-in-force concern; broker acceptance for the exact account/order still requires verification.

The frozen whole-share overnight alternative recorded -5.14% combined modeled return for 2025–September 2026, with -17.49% maximum drawdown, in `docs/WHOLE_SHARE_OVERNIGHT_V1_RESULT.md`. It failed its stated positive-return confirmation gate. A profitable 2026 subset does not validate the combined candidate.

Repair: choose and test an execution-consistent candidate; do not merely relabel overnight research as an intraday strategy. Candidate selection remains unresolved.

### P2 — The requested milestone product is missing

`capital_stages.py` explicitly implements PAPER scoring only, keyed to `paper:paper-1`. Its default ladder is $1k, $10k, $100k, $500k, $1m, with optional $500 and $300k. It omits $200, $3k, $5k, and $50k. It never liquidates, reconciles sale proceeds, or reinvests. The live dashboard hardcodes the next milestone to $1,000 and its progress denominator to $900.

Consequence: an account-equity display has been substituted for the sell/reconcile/reinvest lifecycle requested by the user. The live worker does compound against current account equity, but that is not the requested milestone behavior.

Repair: implement the explicit lifecycle in DELIVERY_PLAN.md. Separate milestone achievement from statistical strategy promotion. The existing paper gate also demands a minimum number of losses; that requirement must not prevent recording a genuinely achieved live cash milestone.

### P2 — Release instructions contradict the implementation

`docs/RELEASE_GATE.md` describes itself as the single truth source but makes Robinhood onboarding mandatory before funding. The repository now has Alpaca and Robinhood paths. `docs/DEPLOYMENT.md` and README retain claims about unverified containers/paper-only operation that conflict with newer repository deployment/test evidence. Configuration comments still refer to keeping live disabled throughout “this development task,” without a scoped task identity or expiry.

`services/live_readiness.py` appends a blocker whenever the live flag is true and always returns `live_execution_enabled: False`. That can be appropriate for a pre-activation check, but its generic live-readiness name conflates pre-activation preparation with running status. Other preflights require LIVE state. They are separate checks, not a demonstrated single executable deadlock, but their semantics are confusing.

Repair: route-specific, phase-specific readiness states: prepared, activation pending, running, entries paused, managing exposure, halted. Document observed facts with timestamps. Require only dependencies used by the selected route.

### P2 — Goal attainment and launch readiness are conflated

The goal-first research document rejects candidates that did not reach $500 in observed years. That is useful evidence about the growth ambition, but does not by itself determine whether software can reliably execute an operator-configured strategy. Conversely, passing software tests does not show positive expected returns.

Repair: retain separate engineering, economic, and activation decisions. Freeze the experiment and finite acceptance conditions; do not impose “prove $100 becomes $1m” as an engineering prerequisite or lower a failed economic threshold after seeing results.

## Strategy conclusion

The plan is stage-by-stage trading with realized proceeds funding each next stage. First evaluate $100 → $200–$500. Once that target is reached and sales reconcile, evaluate the proceeds → $1,000; repeat for $3,000, $5,000, $10,000, $50,000, $100,000, $300,000, $500,000, and finally $1,000,000. A different strategy can serve each stage. The first-stage strategy does not have to demonstrate the entire ladder. The inspected project has not yet established an execution-matched first-stage candidate; its negative tests reject those specific candidates, not the staged architecture itself.

Use a finite, predeclared research program focused on the next milestone: executable-universe screen at the current stage’s usable capital; frozen entry/exit/sizing rules; development data separated from confirmation; execution-matched costs and liquidity; account-level return paths including idle days; forward paper evidence where history is insufficient. Compare candidates by net expectancy, drawdown, probability of exhausting usable capital, and milestone reach frequency under stated assumptions. These estimates are not promises. Do not select a production winner from the current negative evidence.

## Disposition

The instruction replacement and concrete delivery plan are completed in this workspace. Production activation and code repairs are not completed by this audit. The immediate engineering work is the three P1 runtime defects, followed by milestone orchestration and route-specific release evidence. A current deployment/account inspection and a viable execution-matched strategy remain outstanding.
