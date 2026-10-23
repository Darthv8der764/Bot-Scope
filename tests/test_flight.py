"""Flight simulator: a past day's candles with the future and the bot's trades held back until the end."""
import shutil
from pathlib import Path

import pytest

from botscope import flight, journal, loader


@pytest.fixture
def demo_bots(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_DEMO", "1")
    monkeypatch.setenv("BOTSCOPE_BOTS_DIR", str(tmp_path / "bots"))
    (tmp_path / "bots").mkdir()
    for b in ("first_hour_breakout.py", "pullback_swing.py"):
        shutil.copy(Path(flight.__file__).resolve().parent.parent / "bots" / b, tmp_path / "bots")


def test_intraday_day_starts_early_and_scores_against_holding(demo_bots):
    d = flight.flight("first_hour_breakout", "SPY", "2026-10-14")
    assert d["start"] == 6 and len(d["candles"]) == 78 and d["source"].startswith("DEMO DATA")
    assert all(t["t_in"] >= d["candles"][d["start"]]["t"] for t in d["bot_trades"])
    assert d["hold_pct"] == round((d["candles"][-1]["c"] / d["candles"][6]["o"] - 1) * 100 - d["cost_pct"], 3)   # after
    assert "round trip of costs" in d["hold_note"]          # costs too, like you and the bot ("After costs" on the page)
    assert d["cost_pct"] > 0


def test_daily_bot_plays_the_last_60_days(demo_bots):
    d = flight.flight("pullback_swing", "SPY", "2026-10-14")
    assert len(d["candles"]) - d["start"] == 60


def test_weekend_says_pick_another_day(demo_bots):
    with pytest.raises(ValueError, match="pick another day"):
        flight.flight("first_hour_breakout", "SPY", "2026-10-11")


def test_scores_are_saved_and_summed():
    flight.save_score({"bot": "b", "you_pct": 0.5, "bot_pct": 0.1, "hold_pct": 0.9, "trades": 2, "secret": "x"})
    out = flight.save_score({"bot": "b", "you_pct": -0.2, "bot_pct": 0.3, "hold_pct": -0.5, "trades": 1})
    assert out["summary"] == "last 2 flights: you beat the bot on 1 and just holding on 1"
    assert "secret" not in journal.load("flights")[0]
