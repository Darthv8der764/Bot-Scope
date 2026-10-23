"""Offline check of the paper-results CSV export (made-up rows in a temporary journal)."""
import csv

import pytest

from botscope import export, journal, server


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_JOURNAL_DIR", str(tmp_path))


def test_export_writes_every_paper_trade_sorted_and_labeled(tmp_path):
    for bot, day, tid, r in [("b", "2026-10-16", "SPY_1", 1.5), ("a", "2026-10-15", "QQQ_1", -1.0),
                             ("a", "2026-10-16", "SPY_2", 0.25)]:
        journal.upsert("paper_results", {"bot": bot, "symbol": tid[:3], "day": day, "trade_id": tid},
                       {"side": "long", "r": r, "why_out": "end of day"})
    out = export.paper_csv()
    rows = list(csv.DictReader(open(out["path"])))
    assert [r["trade_id"] for r in rows] == ["QQQ_1", "SPY_2", "SPY_1"]
    assert {r["period"] for r in rows} == {"paper"} and "id" not in rows[0]
    assert out["trades"] == 3 and out["total_r"] == 0.75 and out["days"] == "2026-10-15 to 2026-10-16"
    only = export.paper_csv(bot="a", path=str(tmp_path / "a.csv"))
    assert only["trades"] == 2 and only["bots"] == ["a"]


def test_export_tool_with_an_empty_log():
    out = server.export_paper_results()
    assert out["trades"] == 0 and out["days"] == "none" and "paper" in out["note"]
