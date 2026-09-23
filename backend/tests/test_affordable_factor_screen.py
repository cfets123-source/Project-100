import pytest

from app.research.affordable_factor_screen import RULES, ScreenResult, evaluate, select_development
from app.research.weekly_affordable_momentum_v1 import UNIVERSE


def test_screen_is_bounded_and_requires_raw_prices():
    assert len(RULES) == 10
    with pytest.raises(ValueError, match="raw prices"):
        evaluate({}, adjustment="all", style="momentum", lookback=20, trend=False)
    with pytest.raises(ValueError, match="outside the frozen"):
        evaluate({s: [] for s in UNIVERSE},
                 adjustment="raw", style="momentum", lookback=5, trend=False)


def test_selection_rejects_negative_or_excessive_drawdown():
    samples = [ScreenResult("loss", 40, -.01, -.1, ()),
               ScreenResult("too-deep", 40, .4, -.30, ()),
               ScreenResult("qualifier", 40, .1, -.12, ())]
    assert select_development(samples).rule == "qualifier"
    assert select_development(samples[:2]) is None
