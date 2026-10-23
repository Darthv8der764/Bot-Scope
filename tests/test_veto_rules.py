"""Offline checks: repeated vetoes become a backtested rule suggestion that is never applied by itself."""
from datetime import date, datetime

import pytest

from botscope import backtest, journal, loader, veto_rules
from botscope.bot import Entry, View
from botscope.data import ET
from test_format import fake_day
from test_report import fake_fetch


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_JOURNAL_DIR", str(tmp_path))


def veto(sym, day, hhmm, side, entry=100.0, stop=101.0, reason="chasing a big candle"):
    return {"bot": "first_hour_breakout", "symbol": sym, "day": day, "trade_id": f"{sym}_{day}_{hhmm}",
            "side": side, "entry": entry, "stop": stop, "reason": reason}


def test_no_suggestion_from_two_vetoes():
    assert veto_rules.patterns([veto("AAPL", "2026-09-01", "0950", "short")] * 2) == []


def test_patterns_find_side_symbol_and_words():
    vs = [veto("AAPL", f"2026-09-0{i}", "1045", "short") for i in range(1, 4)] + [veto("MSFT", "2026-09-04", "0950", "long")]
    ps = veto_rules.patterns(vs)
    plains = [p["plain"] for p in ps]
    assert "Skip short trades." in plains and "Don't trade AAPL with this bot." in plains
    assert any(p["filters"] == {"skip_after": "10:44"} for p in ps)
    assert ps[0]["your_words"][:2] == ["chasing", "big"] or "chasing" in ps[0]["your_words"]


def test_filter_hook_skips_and_rejects_typos():
    bs = fake_day()
    v = View("AAPL", bs[:40], {})
    e = Entry("short", 101.0, 98.0, "x")
    assert backtest.filter_hook({"skip_side": "short"}, "AAPL")(v, e).reason == "rule idea: skip shorts"
    assert "after 10:00" in backtest.filter_hook({"skip_after": "10:00"}, "AAPL")(v, e).reason    # bar at 10:09
    assert backtest.filter_hook({"skip_after": "10:30"}, "AAPL")(v, e) is e
    assert backtest.filter_hook({"skip_symbols": ["aapl"]}, "AAPL")(v, e).reason.startswith("rule idea")
    with pytest.raises(ValueError):
        backtest.filter_hook({"skip_sides": "short"}, "AAPL")(v, e)


def test_suggest_backtests_before_after_and_never_applies(monkeypatch):
    monkeypatch.setattr(backtest.data, "bars", fake_fetch)
    for i in range(1, 5):
        journal.add("vetoes", veto("TEST", f"2026-09-0{i}", "1015", "short"))
    out = veto_rules.suggest("first_hour_breakout", fetch=fake_fetch)
    side = next(s for s in out["suggestions"] if s["filters"] == {"skip_side": "short"})
    u = side["before_after"]["untested"]
    assert u["trades_after"] < u["trades_before"] and "hurts" in side["verdict"] and "luck" in side["verdict"]
    ideas = journal.find("rule_ideas", bot="first_hour_breakout")
    assert ideas and all("NOT applied" in r["status"] for r in ideas)
    assert loader.get("first_hour_breakout").params["r_multiple"] == 2.0        # the bot itself is untouched
    assert any("different bot" in x for x in out["left_out_too_broad"])       # e.g. "no trades before 10:16"
