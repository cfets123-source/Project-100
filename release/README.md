# Deployed web app and read-only account observer

This package contains the repaired application source and tests, without account databases or credentials. It is intended for the existing Project 100 server. The user explicitly approved upload after the initial automatic-review block. The first image passed all 415 tests on the server; the final image adds the read-only observer and receives its own verification before deployment.

The local app is running at http://127.0.0.1:8765/dashboard with no connected broker. This is a development preview, not the production account.

The proposed server action is to build image `veloikos-stage-repair:20260924` in `/opt/veloikos-releases/20260924-stage-repair`, run its tests in an isolated container, and validate the candidate risk collector against a read-only database mount and read-only broker adapter. `verify_reconciler.py` persists derived evidence only in memory.

Only after those checks pass, the prepared `compose.api.yml` replaces the existing web/API service and starts a read-only account observer. It keeps every order-execution flag disabled, preserves the original database and credentials on the server, retains authentication, and binds to loopback port 8000. Capture the current image identity and an online SQLite backup before replacing the API; keep the previous image and compose configuration for rollback. Additive schema changes preserve existing order and account rows. No trading worker, trading state, strategy approval, or numeric risk limit is changed by this deployment. The new account observer collects read-only broker data and persists derived risk and milestone observations every 60 seconds. Its code forces all execution flags off independently of environment variables.

The broker execution repairs are source-tested but not deployed or broker-validated. Actual strategy selection/approval and real-money activation remain separate from the web release. The inspected pullback strategy is still execution-mismatched; this release does not claim a profitable replacement.

## Verified deployment

The revised release was approved and deployed on September 24. All 418 tests passed in the final server image. The web/API and read-only account observer are running; authenticated health/dashboard checks passed, and the public HTTPS sign-in page is reachable at https://trade.veloikos.com/dashboard. See `deployment-receipt.json` for exact image identities, backup, and runtime evidence. The trading worker remains stopped and no trades were activated.

Rollback the web API to the previous image recorded in the receipt using the retained original compose configuration or an image-pinned override; stop only `account-observer` if removing the new observation process. Do not restore an old account database over newer fills or account events. The schema changes are additive and the prior image can ignore the new tables/columns.
