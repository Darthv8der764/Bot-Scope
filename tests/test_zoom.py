"""Offline checks of the zoom stack (made-up bars, no network)."""
from datetime import date, datetime, timedelta

from botscope import zoom
from botscope.bot import BarData
from botscope.data import ET
from test_luck import walk_day


def fetch(sym, a, b, tf, feed):
    if tf == "1Day":
        return [BarData(datetime(d.year, d.month, d.day, 0, tzinfo=ET), 100, 101, 99, 100.5, 1)
                for d in (a + timedelta(days=i) for i in range((b - a).days + 1)) if d.weekday() < 5]
    days = [a + timedelta(days=i) for i in range((b - a).days + 1)]
    bs = [x for d in days if d.weekday() < 5 for x in walk_day(d, d.toordinal())]
    if tf == "15Min":
        bs = bs[::15]
    return bs


def test_three_levels_with_the_same_moment_marked():
    z = zoom.stack("aapl", "2026-09-02", "10:15", fetch=fetch)
    assert [l["timeframe"] for l in z["levels"]] == ["1Min", "15Min", "1Day"] and z["symbol"] == "AAPL"
    one, fifteen, daily = z["levels"]
    assert len(one["candles"]) == 390 and one["mark"] == fifteen["mark"]
    assert one["mark"] in {c["time"] for c in one["candles"]}
    assert daily["mark"] == daily["candles"][-1]["time"] and len(daily["candles"]) > 100
    assert "not financial advice" in z["note"]


def test_missing_level_is_named_not_fatal():
    def bad(sym, a, b, tf, feed):
        if tf == "15Min":
            raise ConnectionError("down")
        return fetch(sym, a, b, tf, feed)
    z = zoom.stack("AAPL", "2026-09-02", fetch=bad)
    assert z["levels"][1]["candles"] == [] and z["problems"][0].startswith("15Min")
