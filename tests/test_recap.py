"""Offline checks of the weekly recap card."""
from datetime import date
from xml.etree import ElementTree

from botscope import recap

RES = [{"bot": "a", "day": "2026-10-12", "r": 2.0}, {"bot": "a", "day": "2026-10-14", "r": -1.0},
       {"bot": "b", "day": "2026-10-16", "r": -1.0}, {"bot": "a", "day": "2026-10-05", "r": 9.0}]   # last one: other week
BT = [{"bot": "a", "untested": {"avg_r": 0.1}}]


def test_week_numbers_and_honesty():
    rc = recap.build(date(2026, 10, 15), RES, BT, {"a": "Bot A"})
    assert rc["week"] == {"from": "2026-10-12", "to": "2026-10-16"} and rc["trades"] == 3 and rc["total_r"] == 0.0
    a = rc["bots"][0]
    assert a["bot"] == "Bot A" and a["total_r"] == 1.0 and a["wins"] == 1 and a["vs_backtest"] == "better than the backtest"
    assert rc["bots"][1]["backtest_avg_r"] is None and rc["bots"][1]["vs_backtest"] is None
    assert "Small week" in rc["honesty"] and [d["total_r"] for d in rc["by_day"]] == [2.0, 0.0, -1.0, 0.0, -1.0]


def test_svg_is_valid_and_has_no_dollars():
    for res in (RES, []):
        s = recap.svg(recap.build(date(2026, 10, 15), res, BT, {"a": "Bot <A> & co"}))
        ElementTree.fromstring(s)                       # well-formed, names escaped
        assert "$" not in s and "PAPER" in s and "Not financial advice" in s


def test_save_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(recap, "ROOT", tmp_path)
    out = recap.save(date(2026, 10, 15))
    assert out["image"].endswith("week-2026-10-12.svg") and (tmp_path / "data/recaps/week-2026-10-12.svg").exists()
