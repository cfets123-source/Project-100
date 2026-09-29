# Concrete delivery contract

## 1. Establish one application and one release record

Use the actual Project-100 source identified in ../AGENTS.md. Preserve its dirty research files. Identify the deployed revision/image and collect a read-only broker snapshot with timestamp, mode, account identity, funds, positions, open orders, and data freshness. Reconcile the September 22 exit from broker evidence rather than its incident narrative.

Done means a single release record identifies source, deployment, account, strategy version, and current state. It does not mean enabling trading.

## 2. Repair execution supervision

Implement account/mode state isolation with migration; an exposure supervisor independent of entry approval; and measured account loss/drawdown/liquidity inputs. Keep one entry writer per account. Unknown order outcomes must be reconciled before retry.

Required regression scenarios: paper failure while a live position exists; strategy approval revoked while a position exists; configured daily/weekly/total loss limits breached; missing/stale equity history; restart with an outstanding order; partial fills and cancel/fill races; expired protection; duplicate worker startup. Broker doubles must prove no additional entry under blocked conditions and no duplicate exit.

Done means these cases fail before the fix, pass after it, and the relevant existing regression suite passes. Do not alter the production account merely to demonstrate a test.

## 3. Implement the milestone state machine

Proposed ladder, based on the latest request:
`100 → first target within 200–500 → 1,000 → 3,000 → 5,000 → 10,000 → 50,000 → 100,000 → 300,000 → 500,000 → 1,000,000`.

The first milestone is the user’s $200–$500 range; define its exact target as part of that stage’s strategy, without inventing mandatory liquidations at both endpoints. Interpretation of the later "$500" as $500k remains an explicit assumption. Store the policy version with each account so a future correction does not reinterpret an existing stage index.

States: `accumulating → target_detected → liquidating → reconciling → waiting_for_available_funds → stage_complete → accumulating`. Each transition must persist before dependent work. Retrying after restart must resume the same transition and order identities.

- Marked equity reaching a target only triggers evaluation. It is not a completed milestone.
- Stop opening entries during the milestone liquidation workflow. Resolve existing entry orders and their partial fills before computing the remaining position quantity.
- Coordinate existing protective and exit orders to avoid selling twice. Use the broker-supported order path; do not assume atomic cancellation or execution.
- Record completion only after confirmed exit fills, account/order reconciliation, and fee-adjusted available proceeds meet the threshold. If slippage leaves proceeds below target, remain at the current stage and report the shortfall.
- Track external deposits/withdrawals separately so deposits cannot masquerade as trading gains. Show both raw account equity and performance attributable to trading.
- Wait for usable funds according to the broker/account's actual settlement and buying-power rules.
- Reinvest only through the operator-configured strategy and limits for the next stage. A balance threshold alone cannot authorize a new instrument or higher risk.
- Show next target, current state, realized/marked value, costs, completed targets, and exact blocking reason on the dashboard. Persist achieved milestones even if later capital declines; report current equity separately.

Acceptance cases: crossing then slipping below target; delayed/partial fills; rejected liquidation; uncertain order response; restart at every state; deposit across a threshold; same snapshot processed twice; fees reduce cash below target; funds unavailable; multiple thresholds crossed; target at $1m. No stage completion from a paper account, accepted-only order, or unrealized quote.

## 4. Freeze a strategy experiment rather than another open-ended search

Focus on the first $200–$500 milestone using $100 starting capital. Select an executable route from current broker capabilities and buying power. Define the sell-and-reinvest transition before evaluating the candidate. Later stages are separate strategy decisions funded by the actual realized proceeds; do not demand that the first candidate achieve later milestones. Freeze the universe, data source, signal timestamp, entry, exit, holding period, costs, sizing scenarios, benchmark, confirmation period, and pass/fail criteria before observing new results. Inventory already-used periods so they are not described as untouched.

Evaluate account returns, not isolated winning trades. Include idle periods, unaffordable signals, settlement constraints, losing streaks, cost stress, and exhaustion of tradable capital. Candidate results must identify data shortcomings and selection bias. When real historical quotes are unavailable, define the exact forward observations needed and tie them to the frozen candidate.

Conclude each experiment with advance, reject, or insufficient evidence plus the specific missing observation. Do not perpetually add requirements, recycle negative strategies, or claim that an untested aggressive sizing level fixes an absent edge.

Done means a measured, versioned decision. No candidate is approved by this document.

## 5. Produce an operator-reviewable live release

The release bundle must contain the exact source/image, chosen route and strategy, account permissions and funding verification, measured numeric limits, lifecycle evidence, reconciliation results, authenticated dashboard, alert path, rollback procedure, and known limitations. Separate readiness before activation from operating health after activation.

The operator controls actual account activation. Preparing this bundle is engineering work; it does not authorize the assistant to select or execute real-money investments. Do not report the app as live until a fresh deployment/account check actually establishes that state. Do not report profit until fills and fees reconcile.
