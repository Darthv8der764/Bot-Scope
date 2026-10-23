import pytest

from botscope import gallery, journal


def fake_report(bot="first_hour_breakout"):
    journal.upsert("reports", {"bot": bot}, {"bot_name": "First hour breakout", "untested": {
        "trades": 40, "avg_r": -0.1, "total_r": -4.0, "max_drawdown_r": -7.0, "worst_losing_streak": 6, "costs_r": 1.2},
        "years": {"untested": [2022, 2023]}, "losing_untested_years": [2022], "crashes": [],
        "vs_spy": {"untested_years": 2, "years_beat": 0, "bot_usd": -400, "spy_usd": 900}})


def test_needs_an_honest_report_first(tmp_path):
    with pytest.raises(ValueError, match="honest_report"):
        gallery.export("first_hour_breakout", tmp_path)


def test_export_writes_readme_with_label_and_nothing_personal(tmp_path, relabel):
    relabel("first_hour_breakout", status="failed")
    fake_report()
    out = gallery.export("first_hour_breakout", tmp_path)
    assert out["files"] == ["README.md", "first_hour_breakout.py", "label.json"]
    md = (tmp_path / "first_hour_breakout" / "README.md").read_text()
    assert "FAILED its honest test" in md and "nutrition label" in md and "Not financial advice" in md
    assert "Beat just holding SPY?" in md and "0 of 2 untested years" in md
    assert "journal" not in " ".join(out["files"]) and "nothing was pushed" in out["next"]
