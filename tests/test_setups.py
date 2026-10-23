"""Offline checks of the screenshot confidence check (made-up daily bars, no network)."""
from datetime import date, datetime, timedelta

from botscope import setups
from botscope.bot import BarData
from botscope.data import ET


def daily(closes, start=date(2020, 1, 1)):
    out, d = [], start
    for c in closes:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        out.append(BarData(datetime(d.year, d.month, d.day, 0, tzinfo=ET), c, c * 1.01, c * 0.99, c, 1e6))
        d += timedelta(days=1)
    return out


def test_unknown_setup_is_very_low_not_a_guess():
    r = setups.check("AAPL", "head_and_shoulders_maybe", fetch=lambda *a: [])
    assert r["confidence"] == "very low" and "not enough to go on" in r["why"][0] and "breakout" in r["known_setups"]


def test_few_matches_is_very_low_with_the_sample_size():
    bs = daily([100 + i * 0.1 for i in range(120)])
    r = setups.check("AAPL", "breakout", as_of="2021-01-01", fetch=lambda *a: bs)
    assert r["confidence"] == "very low" and r["sample"]["matches"] < 30 and "need 30+" in r["why"][0]


def test_steady_uptrend_breakouts_make_money_and_never_show_a_percent():
    bs = daily([100 * 1.002 ** i * 1.03 ** (i // 8) for i in range(2500)])                 # a staircase up
    r = setups.check("AAPL", "breakout", as_of="2031-01-01", fetch=lambda *a: bs)
    assert r["sample"]["matches"] >= 30 and r["step"] >= 2 and r["confidence"] in setups.LEVELS
    assert "%" not in str(r["why"]) + str(r["sample"]) and "not financial advice" in r["note"]


def test_never_peeks_past_the_screenshot_day():
    seen = {}
    setups.check("AAPL", "gap_up", as_of="2024-03-05", fetch=lambda s, a, b, tf, feed: seen.update(end=b) or [])
    assert seen["end"] == date(2024, 3, 4)


def test_stop_wins_a_tie_inside_one_bar():
    bs = daily([100] * 20)
    bs.append(BarData(bs[-1].t + timedelta(days=1), 100, 110, 90, 100, 1))       # hits stop and target
    assert setups.play(bs, 19, "long", 0) == -1.0
