"""Plain-English alerts: parsed into rules, checked on finished candles, sent at most once a day."""
from datetime import date

import pytest

from botscope import demo, journal, price_alerts as pa


@pytest.mark.parametrize("text,rule", [
    ("tell me when NVDA breaks yesterday's high", {"symbol": "NVDA", "kind": "yesterday", "level": "high", "side": "above"}),
    ("when SPY drops below yesterday's low", {"symbol": "SPY", "kind": "yesterday", "level": "low", "side": "below"}),
    ("when SPY falls below 590", {"symbol": "SPY", "kind": "price", "price": 590.0, "side": "below"}),
    ("tell me when QQQ goes above $600.5", {"symbol": "QQQ", "kind": "price", "price": 600.5, "side": "above"}),
    ("when AAPL moves 3% today", {"symbol": "AAPL", "kind": "move", "pct": 3.0, "side": "either"}),
    ("when MSFT is down 2%", {"symbol": "MSFT", "kind": "move", "pct": 2.0, "side": "down"}),
    ("when TSLA crosses its 50-day average", {"symbol": "TSLA", "kind": "average", "days": 50, "side": "cross"}),
    ("when BTC/USD breaks yesterday's high", {"symbol": "BTC/USD", "kind": "yesterday", "level": "high", "side": "above"}),
    ("tell me when SPY drops 2% in a day", {"symbol": "SPY", "kind": "move", "pct": 2.0, "side": "down"}),
    ("when NVDA jumps 4%", {"symbol": "NVDA", "kind": "move", "pct": 4.0, "side": "up"}),
    ("when QQQ falls 1.5% today", {"symbol": "QQQ", "kind": "move", "pct": 1.5, "side": "down"}),
    ("ping me when bitcoin is under 50k", {"symbol": "BTC/USD", "kind": "price", "price": 50000.0, "side": "below"}),
    ("when ETH goes above 4.5k", {"symbol": "ETH/USD", "kind": "price", "price": 4500.0, "side": "above"}),
])
def test_parse(text, rule):
    assert pa.parse(text) == rule


def test_unreadable_says_how():
    with pytest.raises(ValueError, match="e.g."):
        pa.parse("tell me something nice")
    with pytest.raises(ValueError, match="capitals"):
        pa.parse("when apple goes up")


def test_check_fires_once_a_day(monkeypatch):
    monkeypatch.setenv("BOTSCOPE_DEMO", "1")
    pa.add("when SPY goes above 1")                          # always true on demo prices
    pa.add("when SPY goes above 100000")
    sent = []
    day = date(2026, 10, 14)
    out = pa.check(day, send=lambda *a: sent.append(a) or {"sent": True})
    assert [r["status"] for r in out["rules"]] == ["hit", "not yet"] and len(sent) == 1
    assert "Info only" in sent[0][1]
    again = pa.check(day, send=lambda *a: sent.append(a) or {"sent": True})
    by = {r["reads_as"]: r["status"] for r in again["rules"]}
    assert by["SPY goes above 1"] == "hit (already sent today)" and len(sent) == 1
    assert pa.remove(journal.load("alert_rules")[0]["id"])["removed"]
