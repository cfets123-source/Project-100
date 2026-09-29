# Veloikos 100 project instructions

## Mission and scope

Build a sequence of trading stages. The immediate objective is to trade the starting $100 to the first milestone in the $200–$500 range, sell, reconcile the proceeds, and use those proceeds for the next stage toward $1,000. Repeat this trade → reach target → sell → reconcile → reinvest cycle at each subsequent milestone. Each stage may use a different strategy suited to its available capital and next target. Do not evaluate the starting strategy as though it must reach the ultimate $1,000,000 destination. Do not promise returns or describe more trading as proof of an edge. The user requests aggressive trading; numeric settings must be defined explicitly.

Requested sequence: $100 → first milestone of $200–$500 → $1,000 → $3,000 → $5,000 → $10,000 → $50,000 → $100,000 → $300,000 → $500,000 → $1,000,000. The first target is a range in the request, not an instruction to force separate liquidations at both $200 and $500; record an exact target when defining that stage. Interpret the user's later "$500" as $500,000, pending correction. The current request does not impose a deadline; do not silently turn the older one-year aspiration into a release requirement.

The source checkout used for the September 24 development import is:
`/Users/macneoeduardo/Documents/Codex/2026-09-17/referenced-chatgpt-conversation-this-is-an/work/Project-100`
Application source is now imported into this Veloikos workspace for development, including the older checkout’s uncommitted source files. See audit/import-manifest.json for original hashes. Edit and test this workspace; the older checkout remains preserved. No credentials, account database, or production service was imported. This is not a second trading deployment. Record exact source provenance before any deployment.

## Work sequence

1. Resolve source and deployment provenance: record source commit plus dirty-file hashes, deployed image identity, account/mode, and observation time. Read-only verification precedes claims about current account or worker state.
2. Repair the concrete execution defects in `audit/PROJECT_AUDIT.md`: account/mode isolation, position supervision independent of entry approval, and real account loss/drawdown inputs. Demonstrate failures and repairs with broker doubles and restart/timeout scenarios.
3. Implement the milestone lifecycle as specified in `audit/DELIVERY_PLAN.md`. A balance display is not a completed liquidation or reinvestment workflow.
4. Maintain one route-specific release checklist. Separate engineering readiness, strategy evidence, and operator activation. Unused brokers are not mandatory launch dependencies. Do not require a historical 5x gain simply to classify software as technically operational.
5. Begin with the next unreached milestone. Record current usable capital, that stage’s exact target, strategy, entry/exit rules, sizing, costs, and transition condition. Evaluate frozen strategy candidates against executable broker conditions and net account returns for that stage. Later stages may require different strategies; failure to demonstrate the entire ladder is not a reason to reject an otherwise viable first-stage candidate. Define the experiment, data needs, acceptance rule, and stopping point before running it. Report a failed candidate as failed. Do not keep tuning against the same confirmation data or start unrelated experiments merely to appear busy.
6. Produce a concrete reviewable release artifact, validation results, and remaining blockers. Preparation and testing of software do not authorize this assistant to operate an investment account or choose and submit real-money trades. Keep actual activation as an operator-controlled action.

## Engineering acceptance requirements

- Paper incidents must not alter live-account state. All state, reservations, evidence, and locks must identify broker, account, and mode where applicable.
- Disabling entries must not silently disable monitoring or the explicitly configured management of existing exposure. Entry and exit permissions must be distinct; exits must never open or reverse exposure.
- Never replace unknown risk inputs with zero. Account drawdown must come from reconciled, persistent, cash-flow-adjusted equity history. Liquidity inputs must come from observed data.
- Unknown submission outcomes require reconciliation before retry. Partial fills, cancel/fill races, expired protection, disconnects, and restarts must have explicit behavior.
- Strategy version, holding period, session rules, instruments, sizing, fees, and execution path must match the evidence used for that version.
- Account growth may fund subsequent stages within an operator-defined mandate. A milestone must not silently broaden instruments, increase risk caps, or clear a halt.
- Normal autonomous operation is a software requirement. Do not add per-trade human approval to the product unless required by the chosen broker or operator mandate. This product requirement does not expand the assistant's own transaction permissions.

## Reporting and completion

Distinguish implemented, locally tested, paper-verified, deployed, live-enabled, order accepted, filled, reconciled, and profitable. Never call them interchangeable. Every blocker must name the failing condition, evidence, corrective action, and exact verification that closes it. Do not invent additional gates after agreed evidence passes unless a newly discovered defect justifies the change.

Retain authentication, secret isolation, duplicate-order prevention, reconciliation, and account-level limits. These prevent unintended behavior; they are not a substitute for testing whether the strategy makes money. Do not reset a halt, place trades, or raise limits to make a status display look successful.

## Verified deployment pointer — September 24

The web/API and forced read-only observer run from `/opt/veloikos-releases/20260924-stage-repair/release/compose.api.yml` on the existing server, project name `project-100`. See `release/deployment-receipt.json` for the exact tested image, prior image and backup. The public dashboard is https://trade.veloikos.com/dashboard. The old trading worker is still stopped and the account remains in shadow state; deployment of the web app does not establish live trading. Do not use the older checkout’s compose file to rebuild the API silently, or remove other project containers as orphans.

Latest web/observer release: `/opt/veloikos-releases/20260924-validation-repair/release/compose.api.yml`; receipt: `release/20260924-validation-repair/deployment-receipt.json`. It supersedes the stage-repair web image above. Server tests: 430 passed. Trading worker remains stopped.

Latest web/observer release: `/opt/veloikos-releases/20260924-binance-connection/release/compose.api.yml`; receipt: `release/20260924-binance-connection/deployment-receipt.json`. Server tests: 451 passed. Binance.US connection UI and public quotes deployed; private account credentials still pending. User explicitly chose no paid market-data subscriptions on September 24.
