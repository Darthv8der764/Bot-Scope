"""Offline checks of the drift alarm."""
import random

from botscope import drift


def test_needs_enough_live_trades():
    assert drift.check([0.5] * 5, [0.1] * 50)["level"] == "not enough live trades"
    assert drift.check([0.5] * 12, [])["level"] == "no backtest to compare"


def test_fits_watch_and_alarm():
    rng = random.Random(1)
    bt = [rng.choice([2.0, -1.0, -1.0, 0.2]) for _ in range(300)]     # about +0.05R per trade
    assert drift.check([2.0, -1.0, -1.0, 0.2] * 5, bt)["level"] == "ok"
    alarm = drift.check([-1.0] * 20, bt)
    assert alarm["level"] == "alarm" and alarm["backtest_runs_worse"] < 50
    assert "%" not in " ".join(alarm["why"])
    assert drift.check([2.0] * 20, bt)["level"] == "too good"
