# Robinhood Agentic Trading onboarding

The Veloikos deployment has a read-only connection to one active Robinhood Agentic account. On September 24, 2026, the broker reported Level 2 options permission, $0 equity and buying power, no positions, and no orders. Robinhood's email to the account holder states that Level 3 is denied and another eligibility review will not occur until March 24, 2027. Treat Level 3 as unavailable; do not build or enable a spread route on the assumption that an appeal or later funding will change that decision. No credential, account number, token, or browser session belongs in this repository or dashboard.

## What remains before an execution route can be marked ready

1. The account holder funds the Agentic account through Robinhood's own transfer flow when they choose. Funding is a user-performed transfer and does not enable Veloikos execution.
2. Recheck broker balances, permissions, quote access, positions, and orders after the transfer settles. Level 2 permits buying single long calls and puts, subject to Robinhood's current account and contract checks; it does not permit Level 3 spreads.
3. Store broker credentials only in the deployment secret store. Do not add them to `.env`, git history, logs, screenshots, or the dashboard.
4. Complete exact-strategy validation, an option entry and protective-exit path, paper or simulated broker lifecycle, reconciliation, and deployment checks. Keep execution disabled until those gates pass.

The application starts its OAuth connection only from the password-protected
operator dashboard. Robinhood's callback endpoint is public solely for the
return from that authorization; it validates a short-lived PKCE state before
exchanging a code and never reveals tokens.

## Connection contract

The Robinhood adapter supports read-only account lookup, quotes, positions, orders, and capability discovery. Separate gated order transports exist, but no validated Robinhood option entry worker is running. The read-only verification gate checks the specifically selected dedicated account, finite balances and buying power, positions, and orders without calling any trade method. Any future live submission must reject unless all of these are true:

- the adapter's authenticated account is the selected dedicated Agentic account;
- the broker reports the necessary permission and trading capability;
- the app is in the explicitly configured live-autonomous mode;
- the independent live-execution flag is enabled through the deployment secret store;
- the deterministic risk engine, data-freshness check, account reconciliation, and kill-switch checks all approve the exact order.

The dashboard must distinguish **read-only connected**, **funded**, **broker permitted**, and **execution enabled**. A connected status alone does not imply an order can be placed.

Official Robinhood information: <https://robinhood.com/us/en/support/articles/agentic-trading-overview/>.
