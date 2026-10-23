"""Offline checks of the event-day split."""
from datetime import date

from botscope import eventdays
from botscope.backtest import Trade


def _t(day, r):
    return Trade("SPY", day, "long", 1, 1, 1, "", "", r, r, 0, t_in=f"{day}T10:00:00-04:00", risk_pct=1)


def test_event_dates_merge_opex_and_releases_and_survive_a_missing_key():
    ev, probs = eventdays.event_dates(date(2026, 9, 1), date(2026, 9, 30),
                                      econ=lambda a, b: [{"date": "2026-09-10", "event": "CPI inflation (8:30 AM ET)"}])
    assert ev["2026-09-18"] == ["Monthly options expiration"] and ev["2026-09-10"] == ["CPI inflation"] and not probs

    def broken(a, b):
        raise RuntimeError("FRED_API_KEY missing")
    ev, probs = eventdays.event_dates(date(2026, 9, 1), date(2026, 9, 30), econ=broken)
    assert list(ev) == ["2026-09-18"] and "only options expiration" in probs[0]


def test_split_counts_and_verdicts():
    trades = [_t("2026-09-10", -1.0)] * 12 + [_t("2026-09-11", 0.5)] * 12 + [_t("2026-09-18", 1.0)] * 3
    rows = {r["days"]: r for r in eventdays.split(trades, {"2026-09-10": ["CPI inflation"],
                                                           "2026-09-18": ["Monthly options expiration"]})}
    assert rows["CPI inflation"]["verdict"] == "loses money here" and rows["ordinary days"]["avg_r"] == 0.5
    assert rows["any event day"]["trades"] == 15 and "too few" in rows["Monthly options expiration"]["verdict"]
    assert "%" not in str(rows)


def test_chart_event_banner_adds_the_bot_fit(monkeypatch):
    from botscope import desk, journal, loader, view
    monkeypatch.setattr(desk, "events_on", lambda day: [{"event": "Jobs report (8:30 AM ET)", "source": "FRED"}])
    journal.upsert("event_fit", {"bot": "nr7_swing"}, {"groups": [
        {"days": "Jobs report", "trades": 14, "avg_r": -0.86, "total_r": -12.0, "verdict": "loses money here"}]})
    ev = view._events("2026-11-06", [], loader.get("nr7_swing"))
    assert ev[-1]["event"] == "this bot loses money on Jobs report days (-0.86R a trade over 14 untested)"
    assert len(view._events("2026-11-06", [], loader.get("first_hour_breakout"))) == 1      # no saved fit: no extra line
