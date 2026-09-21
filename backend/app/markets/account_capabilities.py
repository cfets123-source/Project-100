"""Turn read-only broker permissions into explicit capability inputs.

Broker approval alone never grants Veloikos execution authority: market data,
strategy validation, and paper lifecycle evidence remain separate gates.
"""
from __future__ import annotations


def account_approval_report(account: dict) -> dict:
    active = (account.get("status") == "ACTIVE"
              and not account.get("trading_blocked")
              and not account.get("account_blocked"))
    option_level = int(account.get("options_trading_level") or 0)
    return {
        "account_active": active,
        "us_equity": {"approved": active, "detail": "active_brokerage_account"},
        "etf": {"approved": active, "detail": "active_brokerage_account"},
        "crypto": {"approved": active and account.get("crypto_status") == "ACTIVE",
                   "detail": str(account.get("crypto_status") or "INACTIVE").lower()},
        "us_option": {"approved": active and option_level >= 1,
                      "approved_level": option_level,
                      "detail": f"level_{option_level}" if option_level else "disabled"},
    }
