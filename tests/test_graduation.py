"""Offline checks of the graduation test and the per-bot live switch."""
import pytest

from botscope import graduation, journal, settings


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_JOURNAL_DIR", str(tmp_path))
    monkeypatch.setenv("BOTSCOPE_ENV_FILE", str(tmp_path / "none.env"))
    monkeypatch.delenv("BOTSCOPE_LIVE_TRADING", raising=False)


def fill_good_history():
    rs = [1.5, -1.0, 0.8, 1.2, -0.5] * 80
    journal.upsert("backtests", {"bot": "inside_bar_breakout"}, {"untested": {"trades": 400, "avg_r": 0.4,
                   "total_r_range_5_50_95": [60, 160, 260]}, "untested_rs": rs})
    journal.upsert("reports", {"bot": "inside_bar_breakout"}, {"untested": {"trades": 400, "avg_r": 0.4}})
    journal.upsert("luck", {"bot": "inside_bar_breakout"}, {"level": "beats luck"})
    for i in range(40):
        journal.add("paper_results", {"bot": "inside_bar_breakout", "symbol": "AAPL", "day": f"2026-09-{i % 25 + 1:02d}",
                                      "trade_id": f"t{i}", "r": [1.5, -1.0, 0.8, 1.2][i % 4]})


def test_new_bot_fails_and_cannot_go_live():
    t = graduation.test("inside_bar_breakout")
    assert not t["passed"] and "checks to go" in t["verdict"]
    assert graduation.switch_live("inside_bar_breakout", True, confirm=True)["live"] is False


def test_failed_bot_never_graduates(relabel):
    relabel("first_hour_breakout", status="failed")
    t = graduation.test("first_hour_breakout")
    assert not next(c for c in t["checks"] if c["check"] == "Not labeled failed")["pass"]


def test_graduated_bot_needs_switch_then_yes(monkeypatch):
    fill_good_history()
    t = graduation.test("inside_bar_breakout")
    assert t["passed"], [c for c in t["checks"] if not c["pass"]]
    assert "live switch is off" in graduation.switch_live("inside_bar_breakout", True)["blocked"]
    monkeypatch.setenv("BOTSCOPE_LIVE_TRADING", "1")
    assert "question" in graduation.switch_live("inside_bar_breakout", True)
    assert graduation.switch_live("inside_bar_breakout", True, confirm=True)["live"]
    assert settings.load()["live_bots"] == ["inside_bar_breakout"]
    graduation.switch_live("inside_bar_breakout", False)                       # off always works, no questions
    assert settings.load()["live_bots"] == []


def test_a_bot_changed_since_its_report_does_not_graduate():
    from botscope import loader, report
    fill_good_history()
    cls = loader.get("inside_bar_breakout")
    journal.upsert("reports", {"bot": "inside_bar_breakout"}, {"untested": {"trades": 400, "avg_r": 0.4},
                                                            "bot_file_hash": report.fingerprint(cls)})
    assert graduation.test("inside_bar_breakout")["passed"]
    journal.upsert("reports", {"bot": "inside_bar_breakout"}, {"untested": {"trades": 400, "avg_r": 0.4},
                                                            "bot_file_hash": "an-older-version"})
    t = graduation.test("inside_bar_breakout")
    row = next(c for c in t["checks"] if c["check"] == "Report is for today's code")
    assert not t["passed"] and not row["pass"] and row["has"] == "changed since its report"
