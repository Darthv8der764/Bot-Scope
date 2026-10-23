import pytest

from botscope import sizing


def test_one_percent_of_10k_with_a_one_dollar_stop_is_100_shares():
    s = sizing.shares_for(50, 49)
    assert s["shares"] == 100 and s["risk_usd"] == 100 and not s["capped_by_cash"]


def test_tight_stop_is_capped_by_cash_and_says_so():
    s = sizing.shares_for(100, 99.9)
    assert s["shares"] == 100 and s["capped_by_cash"] and "only buys 100" in s["explain"] and s["risk_usd"] == 10


def test_bad_inputs_are_refused():
    for a in [(100, 100), (0, 1), (100, 99, 10_000, 50)]:
        with pytest.raises(ValueError):
            sizing.shares_for(*a)
