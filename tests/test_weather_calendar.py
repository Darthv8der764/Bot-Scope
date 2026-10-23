"""Weather calendar: each day colored by the weather known at its open; the page links days to the bot view."""
from datetime import date
from pathlib import Path

from botscope import demo, weather


def test_days_have_weather_from_before_the_day_and_spy_move(monkeypatch):
    monkeypatch.setenv("BOTSCOPE_DEMO", "1")
    d = weather.calendar_days(3, fetch=demo.bars, now=date(2026, 10, 17))
    assert d["days"] and d["to"] == "2026-10-16" and all(x["day"] >= d["from"] for x in d["days"])
    assert set(d["counts"]) <= {"trending up", "trending down", "choppy", "panic"}
    assert sum(d["counts"].values()) == len(d["days"])
    bs = weather._index_bars(date(2026, 7, 1), date(2026, 10, 16), demo.bars)
    one = d["days"][-1]
    before = [b.c for b in bs if str(b.t.date()) < one["day"]]
    assert weather.classify(before)["weather"] == one["weather"]          # never its own close


def test_page_links_each_day_to_the_bot_view_replay():
    html = (Path(weather.__file__).with_name("web") / "weather.html").read_text()
    assert "/?bot=" in html and "&day=" in html and "/api/weather_calendar" in html
