"""Weekly checkup: drift, changed costs, data gaps, old/missing reports, changed bots on one card."""
from datetime import date

from botscope import backtest, checkup, journal


def test_card_flags_gaps_missing_reports_and_cost_changes(monkeypatch):
    journal.add("paper_results", {"bot": "nr7_swing", "day": "2026-10-13", "r": 0.2, "trade_id": "a"})
    c = checkup.checkup(date(2026, 10, 18))                  # a Sunday
    assert len(c["lines"]) == 4 and "first checkup" in c["lines"][1]
    assert "2026-10-12" in c["lines"][2] and "2026-10-13" not in c["lines"][2] and "2026-10-17" not in c["lines"][2]
    assert all("no honest report yet" in r["flags"] for r in c["bots"]) and c["needs_a_look"]
    assert "first checkup" in checkup.checkup(date(2026, 10, 18))["lines"][1]     # same day: still the first
    assert len(journal.load("checkup")) == 1                                      # one row per day
    assert "unchanged" in checkup.checkup(date(2026, 10, 19))["lines"][1]
    monkeypatch.setitem(backtest.COSTS, "swing", {**backtest.COSTS["swing"], "entry_bps": 99})
    assert "CHANGED" in checkup.checkup(date(2026, 10, 25))["lines"][1]
    assert "CHANGED" in checkup.checkup(date(2026, 10, 25))["lines"][1]           # a second look the same day too
    import re
    assert not re.search(r"(?i)win[_ ]?rate|win ?%", str(c))
