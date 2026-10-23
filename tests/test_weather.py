"""Offline checks of market weather (made-up closes and bars, no network)."""
from datetime import date, datetime, timedelta

from botscope import backtest, journal, loader, weather
from botscope.bot import BarData
from botscope.data import ET
from test_luck import fetch_from, walk_day


def series(closes, start=date(2025, 1, 1)):
    out, d = [], start
    for c in closes:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        out.append(BarData(datetime(d.year, d.month, d.day, 16, tzinfo=ET), c, c * 1.002, c * 0.998, c, 1e6))
        d += timedelta(days=1)
    return out


def test_classify_levels():
    up = [100 * 1.004 ** i for i in range(70)]
    assert weather.classify(up)["weather"] == "trending up"
    assert weather.classify(list(reversed(up)))["weather"] == "panic"          # 20%+ below the 60-day high
    chop = [100 + (1 if i % 2 else -1) * 0.6 for i in range(70)]
    c = weather.classify(chop)
    assert c["weather"] == "choppy" and c["numbers"]["trend_efficiency"] < 0.3
    crash = up[:-1] + [up[-2] * 0.95]
    assert weather.classify(crash)["weather"] == "panic"
    assert weather.classify([100] * 5)["weather"] == "unknown"


def test_labels_never_use_the_same_day():
    closes = [100 * 1.004 ** i for i in range(40)] + [50]       # a crash on the last day
    labels = weather.label_days(series(closes))
    last = max(labels)
    assert labels[last] == "trending up"                         # the crash isn't known at that day's open


def test_fit_rows_and_verdict():
    T = lambda d, r: backtest.Trade("X", d, "long", 1, 1, 0.9, "", "", r, 0, 0, t_in=d + "T10:00")
    trades = [T("2025-03-03", 1.0)] * 12 + [T("2025-03-04", -1.0)] * 3
    rows = weather.fit_rows(trades, {"2025-03-03": "choppy", "2025-03-04": "panic"})
    assert rows[0] == {"weather": "choppy", "trades": 12, "avg_r": 1.0, "total_r": 12.0}
    assert weather.fit_verdict(rows, "choppy").startswith("does well")
    assert weather.fit_verdict(rows, "panic").startswith("not enough")


def test_market_weather_runs_and_saves_fit():
    def fetch(sym, start, end, tf, feed):
        if sym == "SPY":
            return series([100 * 1.003 ** i for i in range(200)], start)
        return fetch_from(walk_day)(sym, start, end, tf, feed)
    out = weather.market_weather(loader.get("first_hour_breakout"), fetch=fetch)
    assert out["weather"]["weather"] in ("trending up", "choppy", "panic", "trending down")
    assert out["fresh_fit"]["window"]["period"] == "untested" and "today" in out["fresh_fit"]
    assert journal.find("weather_fit", bot="first_hour_breakout")[0]["bot_name"] == "First hour breakout"
    assert out["bots"][0]["name"] == "First hour breakout"
