from decimal import Decimal as D

from app.markets.venue_economics import VenueEstimate, evaluate_venue, select_venue


def venue(name, *, entry=D("0"), exit=D("0"), spread=D("0"),
          slippage=D("0"), fx=D("0"), data=D("0"), gross=D("2")):
    return VenueEstimate(name, D("100"), gross, entry, exit, spread, slippage, fx, data)


def test_small_foreign_trade_is_rejected_when_fees_exceed_edge():
    result = evaluate_venue(venue("foreign-api", entry=D("1.25"), exit=D("1.25"),
                                  spread=D("10"), fx=D("10")))
    assert not result.eligible
    assert result.reason == "cost_exceeds_expected_edge"
    assert result.all_in_cost == D("2.70")
    assert result.cost_pct == D("2.700")
    assert result.expected_net_return_pct == D("-0.700")


def test_cheapest_net_venue_wins_even_when_both_quote_zero_commission():
    selected = select_venue([venue("wide-spread", spread=D("80")),
                             venue("narrow-spread", spread=D("10"))])
    assert selected.venue == "narrow-spread"
    assert selected.expected_net_profit == D("1.90")


def test_unknown_data_cost_cannot_be_treated_as_free():
    result = evaluate_venue(venue("unpriced-data", data=None))
    assert not result.eligible
    assert result.reason == "cost_or_edge_unknown"
    assert select_venue([venue("unpriced-data", data=None)]) is None


def test_omitted_data_cost_is_unknown_by_default():
    estimate = VenueEstimate("unpriced", D("100"), D("2"), D("0"), D("0"), D("0"), D("0"))
    assert evaluate_venue(estimate).reason == "cost_or_edge_unknown"


def test_nonfinite_inputs_and_different_notional_are_rejected():
    assert evaluate_venue(venue("bad", spread=D("NaN"))).reason == "cost_or_edge_unknown"
    larger = VenueEstimate("larger", D("200"), D("4"), D("0"), D("0"), D("0"), D("0"), D("0"), D("0"))
    assert select_venue([venue("small"), larger]) is None


def test_subscription_cost_is_allocated_to_expected_trade():
    result = evaluate_venue(venue("subscribed", data=D("1.50"), spread=D("10")))
    assert result.eligible
    assert result.all_in_cost == D("1.60")
    assert result.expected_net_profit == D("0.40")
