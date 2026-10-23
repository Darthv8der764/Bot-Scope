import json
import re
import urllib.request
from datetime import date, datetime, time, timedelta

from botscope import journal, loader, signals, view
from botscope.bot import BarData, Bot, Entry, NoTrade
from botscope.data import ET

DAY = date(2026, 10, 19)                       # a Monday


def _bars(n=30, start=time(9, 30), step=5):
    t0 = datetime.combine(DAY, start, ET)
    return [BarData(t0 + timedelta(minutes=step * i), 100 + i * .1, 100.3 + i * .1, 99.8 + i * .1, 100.1 + i * .1, 1000)
            for i in range(n)]


def _bot(name, fire_at=None, almost_at=None):
    class B(Bot):
        symbols = ["TEST"]
        timeframe = "5Min"

        def entry(self, view):
            hm = view.now.strftime("%H:%M")
            if hm == fire_at:
                return Entry("long", view.last.c - 0.5, view.last.c + 5.0, "closed above the morning high")
            if hm == almost_at:
                return NoTrade("volume too low", almost=Entry("long", view.last.c - 0.4, view.last.c + 0.8, "breakout"))
            return NoTrade("no breakout yet")
    B.name = name
    return B


def _scan(monkeypatch, bots, now, mine=True, **kw):
    monkeypatch.setattr(loader, "is_mine", lambda c: mine)
    return signals.scan(now=now, bots=bots, fetch=lambda sym, day, cls: (_bars(), "test bars"), **kw)


NOW = datetime.combine(DAY, time(12, 2), ET)     # last finished 5-minute bar: 11:55 (the 12:00 one is still forming)


def test_rule_firing_on_last_bar_shows_with_stop_and_target(monkeypatch):
    r = _scan(monkeypatch, {"fires": _bot("Fires", fire_at="11:55"), "quiet": _bot("Quiet")}, NOW)
    assert r["market"]["stocks_open"] and r["refresh_s"] == 60 and r["paper_only"]
    assert len(r["signals"]) == 1
    s = r["signals"][0]
    assert s["bot"] == "fires" and s["symbol"] == "TEST" and s["side"] == "long" and s["time_label"] == "11:55 AM"
    assert s["stop"] == round(s["price"] - 0.5, 4) and s["target"] == round(s["price"] + 5.0, 4)
    assert s["risk"] == 0.5 and s["target_r"] == 10.0
    assert s["reason"] == "closed above the morning high"
    assert s["says"] == "your strategy Fires says buy" and "should" not in s["says"]
    assert s["link"].startswith("/?bot=fires&symbol=TEST&day=2026-10-19")
    assert {b["id"] for b in r["bots"]} == {"fires", "quiet"}        # the quiet bot was checked, but has no row


def test_rule_that_does_not_fire_is_not_listed(monkeypatch):
    r = _scan(monkeypatch, {"quiet": _bot("Quiet")}, NOW)
    assert r["signals"] == [] and r["close"] == [] and r["in_trade"] == []


def test_forming_bar_is_never_used(monkeypatch):
    r = _scan(monkeypatch, {"early": _bot("Early", fire_at="12:00")}, NOW)   # 12:00 bar closes at 12:05
    assert r["signals"] == []


def test_older_entry_is_already_in_a_trade_and_near_miss_is_close(monkeypatch):
    r = _scan(monkeypatch, {"old": _bot("Old", fire_at="10:00"), "near": _bot("Near", almost_at="11:55")}, NOW)
    assert [x["bot"] for x in r["in_trade"]] == ["old"] and r["in_trade"][0]["moved_r"] is not None
    assert [x["bot"] for x in r["close"]] == ["near"] and r["close"][0]["blocked_by"] == "volume too low"
    assert r["signals"] == []


def test_examples_only_when_asked(monkeypatch):
    bots = {"fires": _bot("Fires", fire_at="11:55")}
    r = _scan(monkeypatch, bots, NOW, mine=False)
    assert r["signals"] == [] and r["bots"] == [] and "include examples" in r["empty_reason"]
    r = _scan(monkeypatch, bots, NOW, mine=False, include_examples=True)
    assert len(r["signals"]) == 1 and r["signals"][0]["mine"] is False


def test_outside_hours_state(monkeypatch):
    evening = datetime.combine(DAY, time(18, 30), ET)
    r = _scan(monkeypatch, {"quiet": _bot("Quiet")}, evening)
    assert not r["market"]["stocks_open"] and r["refresh_s"] is None and not r["live"]
    assert r["market"]["note"] == "US market closed: last signals from 11:55 AM on Mon Oct 19."
    sat = datetime(2026, 10, 24, 11, 0, tzinfo=ET)
    assert not signals.stocks_open(sat) and not signals.stocks_open(datetime.combine(DAY, time(9, 29), ET))
    assert signals._session_day("SPY", "5Min", sat) == date(2026, 10, 23)          # Saturday: Friday's session


def test_track_record_fields(monkeypatch):
    cls = _bot("Fires", fire_at="11:55")
    journal.upsert("backtests", {"bot": "fires"}, {"untested": {"trades": 42, "avg_r": 0.12, "total_r_range_5_50_95": [1, 5, 9]}})
    journal.upsert("paper_results", {"bot": "fires", "symbol": "TEST", "day": "2026-10-16", "trade_id": "a"}, {"r": 1.5})
    t = signals.track_record(cls)
    assert t["confidence"] == "medium" and t["untested_trades"] == 42 and t["untested_avg_r"] == 0.12
    assert t["untested_source"] == "quick backtest" and t["live_paper_trades"] == 1 and t["live_paper_avg_r"] == 1.5
    assert "42 untested trades" in t["summary"]
    journal.upsert("reports", {"bot": "fires"}, {"untested": {"trades": 120, "avg_r": 0.2}})
    assert signals.track_record(cls)["untested_source"] == "full report"
    r = _scan(monkeypatch, {"fires": cls}, NOW)
    assert r["signals"][0]["track"]["untested_trades"] == 120          # every row carries its strategy's record


def test_never_places_an_order():
    for f in (signals.__file__, view.PAGE.with_name("signals.js")):
        src = open(f).read()
        for word in ("submit_order", "cancel_order", "replace_order", "close_position", "close_all", "place_",
                     "TradingClient", "/api/stop", "/api/move", "/api/veto"):
            assert word not in src, (f, word)
        assert not re.search(r"you should (buy|sell)", src, re.I)
    js = view.PAGE.with_name("signals.js").read_text()
    assert "not financial advice" in js and "nothing on this page places an order" in js


def test_api_and_studio_tab():
    base = view.ensure_server()
    got = json.load(urllib.request.urlopen(base + "/api/signals"))
    assert got["paper_only"] and "signals" in got and "market" in got
    studio = view.PAGE.with_name("studio.html").read_text()
    assert '["signals", "Signals", null]' in studio and '<script src="/signals.js"></script>' in studio
    assert urllib.request.urlopen(base + "/signals.js").status == 200
