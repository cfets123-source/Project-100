from app.markets.options_research import assess_option_chain


def test_option_chain_probe_requires_valid_quotes_before_data_is_ready():
    report = assess_option_chain({"snapshots": {
        "SPY260925C00650000": {"latestQuote": {"bp": 1.00, "ap": 1.06}},
        "SPY260925C00655000": {"latestQuote": {"bp": 0, "ap": 0.05}},
    }}, underlying="SPY", feed="opra")
    assert report["quote_probe_ready"] is True
    assert report["strategy_data_ready"] is True
    assert report["quoted_contracts"] == 1
    assert report["tight_quote_contracts"] == 1
    assert report["status"] == "research_only"


def test_option_chain_probe_does_not_treat_empty_chain_as_ready():
    report = assess_option_chain({"snapshots": {}}, underlying="SPY", feed="opra")
    assert report["quote_probe_ready"] is False
    assert report["strategy_data_ready"] is False


def test_indicative_data_is_discovery_only_even_with_quotes():
    report = assess_option_chain({"snapshots": {
        "SPY260925C00650000": {"latestQuote": {"bp": 1.00, "ap": 1.06}},
    }}, underlying="SPY", feed="indicative")
    assert report["quote_probe_ready"] is True
    assert report["strategy_data_ready"] is False
