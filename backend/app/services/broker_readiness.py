"""Read-only broker verification.

This module deliberately has no path to order preview, submission, or
cancellation. It is the first gate after a real broker adapter exists: prove
the authenticated account and balances are coherent before any later mode can
even consider execution.
"""
import math
import time


def verify_read_only_connection(adapter, expected_account_id: str):
    """Return a conservative connection report without invoking trading methods.

    `expected_account_id` is selected outside this function after the operator
    sees the broker's dedicated Agentic account. A report can be read-only ready
    while always remaining execution-disabled.
    """
    report = {
        "connected": False,
        "read_only_ready": False,
        "execution_enabled": False,
        "expected_account_id": expected_account_id,
        "verified_at": time.time(),
        "reasons": [],
    }
    try:
        if not adapter.authenticate():
            report["reasons"].append("broker authentication was not confirmed")
            return report
        accounts = adapter.get_accounts()
        matches = [account for account in accounts if str(account.get("account_id")) == expected_account_id]
        if len(matches) != 1:
            report["reasons"].append("expected dedicated account was not returned exactly once")
            return report
        balances = adapter.get_balances()
        buying_power = adapter.get_buying_power()
        for key in ("cash", "equity"):
            value = balances.get(key)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                report["reasons"].append(f"broker returned invalid {key}")
        if not isinstance(buying_power, (int, float)) or not math.isfinite(buying_power) or buying_power < 0:
            report["reasons"].append("broker returned invalid buying power")
        # Read these now so the dashboard can display a reconciled starting view.
        positions = adapter.get_positions()
        orders = adapter.get_orders()
        if not isinstance(positions, list) or not isinstance(orders, list):
            report["reasons"].append("broker returned malformed positions or orders")
        if report["reasons"]:
            return report
        report.update(connected=True, read_only_ready=True,
                      account={"account_id": expected_account_id, "type": matches[0].get("type")},
                      balances={"cash": balances["cash"], "equity": balances["equity"],
                                "buying_power": buying_power},
                      open_positions=len(positions), open_orders=len(orders))
        return report
    except Exception as exc:
        # Surface only an error class to operators; avoid leaking broker payloads,
        # tokens, or account identifiers through an API response.
        report["reasons"].append(f"broker verification failed: {type(exc).__name__}")
        return report
