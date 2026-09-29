# Veloikos build handoff — September 24, 2026

## Objective
Execute successive trading stages: $100 to an exact first target within $200–$500 (currently $200), liquidate, reconcile proceeds, then reinvest toward $1,000, $3,000, $5,000, $10,000, $50,000, $100,000, $300,000, $500,000 and $1 million. Each stage may use a different strategy. No guaranteed returns or invented deadline. Read AGENTS.md before implementation.

## Verified state
- Web app deployed at https://trade.veloikos.com/dashboard. Latest deployment receipt: release/20260924-binance-connection/deployment-receipt.json. That release passed 451 tests locally and on the server.
- Binance.US connection completed after that release: account ending 7211 verified through the deployed form at 4:46:48 p.m. Eastern September 24. USD available $0, locked $0, open orders 0. BTCUSD and ETHUSD account fees: 0% maker, 0.02% taker.
- New key label Veloikos-Connect: Read enabled; Spot Trading and Withdrawals disabled; trusted IP restricted to 104.248.229.235. Account refresh succeeded after restriction. Credentials are stored encrypted on the server. Do not copy credentials into source, reports, chat, or logs.
- Earlier key Veloikos remains present and IP-restricted; its secret was not saved. Do not delete keys without the necessary authorization.
- The deployment receipt and final AGENTS.md deployment paragraph still say private credentials pending. Those statements describe the earlier deployment time; the later verified connection above supersedes that status. Do not rewrite historical receipts.
- Binance integration is READ-ONLY: account, balances, open-order count, fees and public quotes. There is no Binance order-execution adapter yet. Connecting did not activate trading.
- Last deployment verification had the live trading worker stopped and execution disabled. Recheck actual server state before changing or claiming current worker status.
- User requires no paid market-data subscriptions. Alpaca crypto is unavailable for this Florida account. Alpaca OPRA requires a paid plan; it has not been enabled.
- Current options quotes worked through the existing Robinhood Agentic connection in the September 24 probe. This does not establish a comprehensive historical OPRA bid/ask archive. See research/20260924-free-options-data/RESULT.md.

## Strategy evidence
See research/20260924-cross-market/RESULT.md and its frozen PLAN.md. Four candidates plus two benchmarks were tested across three independent windows and two cost assumptions (36 paths). Broad US equity trend alone passed the frozen screen, lagged SPY buy-and-hold in every window, and did not reach $200. Crypto rotation failed drawdown/recent-return checks. No tested aggressive-growth strategy has demonstrated the requested first-stage objective robustly. Historical monthly holding rules do not match the existing DAY-stop worker. Do not relabel failed candidates or bypass this mismatch.

## Next build work
1. Define one first-stage strategy experiment with explicit entry/exit rules, sizing, loss limits, actual venue fees, data needs, untouched evaluation data, acceptance criteria and stopping point before running it. Focus on the newly verified route rather than opening more accounts.
2. Build and test Binance execution support in simulation/paper mode: instrument filters, minimum order and precision handling, order IDs, partial fills, cancel/fill races, timeout reconciliation before retries, reconnect/restart recovery, and position supervision.
3. Integrate execution with the milestone lifecycle; demonstrate target detection, liquidation, confirmed flat positions and proceeds reconciliation, then the next stage. Ensure evidence holding periods match worker behavior.
4. Produce a route-specific release candidate and report engineering, strategy and account-funding readiness separately. User-controlled activation remains distinct from software deployment. Do not send real-money trades as part of development or verification.

## Relevant code and release
- backend/app/brokers/binance_us.py
- backend/app/binance_routes.py
- backend/tests/test_binance_us.py
- audit/PROJECT_AUDIT.md and audit/DELIVERY_PLAN.md
- Production compose: /opt/veloikos-releases/20260924-binance-connection/release/compose.api.yml, project project-100.
- Do not rebuild silently from the preserved older checkout or remove other project containers as orphans.

## Continuing in regular ChatGPT
Upload this file plus the relevant nonsecret source/research files. A new regular Chat conversation should not assume access to the local checkout, desktop browser sessions, or server. Use it for design, research and code review within available tools; actual changes/deployment require an appropriately connected development environment.
