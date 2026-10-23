"""Offline checks of the bot vs bot arena (made-up bars, no network)."""
from datetime import date

import pytest

from botscope import arena, loader
from test_luck import fetch_from, walk_day
from test_report import shifted


def test_window_avoids_both_bots_tuned_days(relabel):
    a = relabel("first_hour_breakout", tuned_on=("2025-10-01", "2026-10-01"))
    start, end = arena.untested_window(a, a, 60, today=date(2026, 10, 15))
    assert end < date(2025, 10, 1) and (end - start).days == 60


def test_head_to_head_counts():
    h = arena.head_to_head({"d1": 2, "d2": 1, "d3": 1}, {"d1": -1, "d2": 0, "d3": 0}, reshuffles=200)
    assert h["a_ahead"] == 200 and h["b_ahead"] == 0 and h["a_better_days"] == 3
    v = arena.verdict("A", "B", {"trades": 12, "total_r": 4}, {"trades": 12, "total_r": -1}, h)
    assert v["level"] == "clear winner" and v["winner"] == "A"
    close = arena.head_to_head({"d1": 1, "d2": -1}, {"d1": -1, "d2": 1}, reshuffles=200)
    assert arena.verdict("A", "B", {"trades": 12, "total_r": 0}, {"trades": 12, "total_r": 0},
                         close)["level"] == "too close to call"


def test_too_few_trades_says_so():
    v = arena.verdict("A", "B", {"trades": 3, "total_r": 1}, {"trades": 20, "total_r": 1},
                      {"a_ahead": 1000, "b_ahead": 0, "of": 1000})
    assert v["winner"] is None and v["level"] == "not enough trades"


def test_race_two_versions_on_made_up_days():
    cls = loader.get("first_hour_breakout")
    r = arena.race(cls, None, {"r_multiple": 1.0}, {"r_multiple": 3.0}, ["AAA", "BBB"],
                   fetch=fetch_from(walk_day), today=date(2026, 10, 15))
    assert [row["bot"] for row in r["table"]][0].endswith("{'r_multiple': 1.0}")
    assert r["window"]["period"] == "untested for both bots"
    assert r["level"] in ("clear winner", "probably better", "too close to call", "not enough trades")


def test_same_bot_same_settings_ties():
    cls = loader.get("first_hour_breakout")
    r = arena.race(cls, None, symbols=["AAA"], fetch=fetch_from(lambda d, n: shifted(d)), today=date(2026, 10, 15))
    assert r["table"][0]["total_r"] == r["table"][1]["total_r"] and r["winner"] is None


def test_daily_vs_intraday_refused():
    with pytest.raises(ValueError):
        arena.race(loader.get("first_hour_breakout"), loader.get("nr7_swing"), fetch=fetch_from(walk_day))
