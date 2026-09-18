# Robinhood Agentic Trading onboarding

Project 100 is **not connected to Robinhood yet**. This is intentional: a broker connection authorizes access to financial-account information and, once live execution is later enabled, could place orders. No credential, account number, token, or browser session belongs in this repository or dashboard.

## What is required before a connection can be marked ready

1. Create or identify the dedicated Robinhood Agentic Trading account in Robinhood's official setup. Do not use an account holding unrelated investments.
2. Fund that account with the $100 starting balance through Robinhood's own transfer flow. This is a user-performed financial transfer, not an automated Project 100 action.
3. Authorize a broker session through the official Robinhood Agentic Trading/MCP flow. Verify that it reports the dedicated account and its available cash.
4. Store broker credentials only in the deployment secret store. Do not add them to `.env`, git history, logs, screenshots, or the dashboard.
5. Run a read-only capability check and reconcile reported buying power with the account. Keep execution disabled.
6. Complete the paper, shadow, reliability, and deployment gates. A separate explicit live-enable decision is required after those gates pass.

## Connection contract

The future Robinhood adapter must implement the existing broker abstraction and support account lookup, quotes, positions, orders, order lookup, cancellation, and capability discovery. It must reject live submission unless all of these are true:

- the adapter's authenticated account is the selected dedicated Agentic account;
- the broker reports the necessary permission and trading capability;
- the app is in the explicitly configured live-autonomous mode;
- the independent live-execution flag is enabled through the deployment secret store;
- the deterministic risk engine, data-freshness check, account reconciliation, and kill-switch checks all approve the exact order.

The dashboard's Robinhood card remains **Not connected** until a real read-only capability check proves this contract. It never infers a connection from configuration text alone.

Official Robinhood information: <https://robinhood.com/us/en/support/articles/agentic-trading-overview/>.
