from app.markets.account_capabilities import account_approval_report


def test_options_approval_is_distinct_from_execution_authority():
    report = account_approval_report({
        "status": "ACTIVE", "trading_blocked": False, "account_blocked": False,
        "crypto_status": "INACTIVE", "options_trading_level": 3,
    })
    assert report["us_option"] == {"approved": True, "approved_level": 3, "detail": "level_3"}
    assert report["crypto"]["approved"] is False


def test_blocked_broker_account_cannot_grant_asset_approval():
    report = account_approval_report({
        "status": "ACTIVE", "trading_blocked": True, "account_blocked": False,
        "crypto_status": "ACTIVE", "options_trading_level": 3,
    })
    assert report["us_equity"]["approved"] is False
    assert report["crypto"]["approved"] is False
    assert report["us_option"]["approved"] is False
