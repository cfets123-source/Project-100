# Connect a personal E*TRADE account

Veloikos has a read-only E*TRADE OAuth 1.0a connection. It reads brokerage
accounts, balances, stock quotes, and option chains. After authorization, a
chain is available at `/brokers/etrade/options/chain?symbol=SPY&year=2026&month=9&day=25`.
The response includes the broker's `quote_type`: a `DELAYED` response must not
be used as an executable price. It cannot submit or cancel orders. E*TRADE
account access does not add any asset class to live execution.

1. From your E*TRADE login, complete the [Individual live API key application](https://developer.etrade.com/getting-started), including the API User Intent Survey and Developer Agreement. Complete the Market Data Agreement for quote access. Use an individual key for your own account.
2. Put `ETRADE_CONSUMER_KEY` and `ETRADE_CONSUMER_SECRET` in the deployment's private `.env.host` file, then recreate only the API service. Do not place either value in Git, chat, a URL, or the dashboard.
3. Open `/brokers/etrade/connect` while logged in to the Veloikos dashboard. Open the E*TRADE authorization link in a new tab, approve access there, and enter its one-time verification code in the Veloikos form within five minutes.
4. Verify `/brokers/etrade/status` reports authorization recorded today and `/brokers/etrade/accounts` returns the intended account last four and read-only balance. A production token expires at midnight Eastern and may need renewal after two hours of inactivity; repeat authorization on a new day.

The E*TRADE sandbox uses canned responses and does not prove a strategy or live order path. The personal brokerage website may support products whose developer API has no supported execution endpoint; Veloikos will not infer execution capability from account holdings or quotes.
