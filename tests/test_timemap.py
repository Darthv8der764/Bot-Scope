"""Offline checks of the time-of-day map (made-up trades and random-walk days, no network)."""
from botscope import backtest, loader, timemap
from test_luck import fetch_from, walk_day


def T(t_in, r):
    return backtest.Trade("X", t_in[:10], "long", 1, 1, 0.9, "", "", r, 0, 0, t_in=t_in)


def test_rows_by_hour_count_wins_and_hold_back_small_rows():
    ts = [T(f"2025-03-0{d}T09:50:00-05:00", -1) for d in range(3, 8)] + [T("2025-03-03T13:05:00-05:00", 2)]
    r = timemap.rows(ts)
    assert [x["when"] for x in r] == ["9am-10am", "1pm-2pm"]
    assert r[0] == r[0] | {"trades": 5, "wins": 0, "total_r": -5, "verdict": "loses money here"}
    assert r[1]["verdict"].startswith("too few to say")
    assert all("%" not in str(x) for x in r)


def test_weekday_rows_in_calendar_order():
    r = timemap.rows([T("2025-03-07T10:00:00-05:00", 1), T("2025-03-03T10:00:00-05:00", 1)], "weekday")
    assert [x["when"] for x in r] == ["Monday", "Friday"]


def test_time_map_runs_on_untested_days_only():
    out = timemap.time_map(loader.get("first_hour_breakout"), ["AAPL"], 20, fetch=fetch_from(walk_day))
    assert out["window"]["period"] == "untested" and out["by"] == "hour"
    assert "tuned" in out["note"] and "Not financial advice" in out["note"]


def test_crypto_weekend_trades_get_their_own_rows():
    ts = [T("2025-03-08T10:00:00-05:00", 1), T("2025-03-09T10:00:00-05:00", -1), T("2025-03-03T10:00:00-05:00", 1)]
    r = timemap.rows(ts, "weekday")
    assert [x["when"] for x in r] == ["Monday", "Saturday", "Sunday"]
    assert sum(x["trades"] for x in r) == len(ts)          # no trade ever drops out of the map


def test_daily_bot_hint_talks_about_days():
    out = timemap.time_map(loader.get("pullback_swing"), ["AAA"], days=20, fetch=fetch_from(walk_day))
    assert out["by"] == "weekday" and "hour" not in out["hint"]
