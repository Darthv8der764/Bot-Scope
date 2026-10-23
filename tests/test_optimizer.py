"""Honest optimizer: a grid of honest reports, the best cell, and the luck checks around it."""
import shutil
from pathlib import Path

import pytest

from botscope import demo, journal, loader, optimizer, strategy_factory as sf


@pytest.fixture
def bot(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_BOTS_DIR", str(tmp_path / "bots"))
    (tmp_path / "bots").mkdir()
    shutil.copy(Path(sf.__file__).resolve().parent.parent / "bots" / "pullback_swing.py", tmp_path / "bots")
    return loader.get("pullback_swing")


def test_grid_best_cell_and_checks(bot):
    out = optimizer.optimize(bot, "rsi_below", "stop_ranges", ["SPY"], fetch=demo.bars)
    assert out["cells_tried"] == len(out["grid"]) * len(out["grid"][0]) >= 9
    assert out["values"]["rsi_below"] == [6, 8, 10, 12, 14]
    assert out["current"]["rsi_below"] == 10 and "verdict" in out
    if "best" in out:
        assert "best of" in out["luck_in_best"] and "neighbors make money" in out["neighbors"]["summary"]
        assert set(out["held_out"]) == {"best", "today"}
    assert journal.load("optimizer")[-1]["settings"] == ["rsi_below", "stop_ranges"]
    md = optimizer.markdown(out)
    assert "(today)" in md and "rsi_below" in md
    assert bot.params["rsi_below"] == 10                      # the bot itself is never changed


def test_settings_must_be_numbers(bot):
    with pytest.raises(ValueError, match="number settings"):
        optimizer.pick_settings(bot, "nope", None)
    assert optimizer.pick_settings(bot, None, None) == ("trend_days", "rsi_days")


def test_reruns_with_other_settings_add_up(bot):
    optimizer.optimize(bot, "rsi_below", "stop_ranges", ["SPY"], fetch=demo.bars)
    assert "tries_across_runs" not in optimizer.optimize(bot, "rsi_below", "stop_ranges", ["SPY"], fetch=demo.bars)
    other = [k for k, v in bot.params.items() if isinstance(v, (int, float)) and k not in ("rsi_below", "stop_ranges")][0]
    out = optimizer.optimize(bot, "rsi_below", other, ["SPY"], fetch=demo.bars)
    assert "across optimizer runs" in out["tries_across_runs"]


def test_cells_with_tight_stops_are_never_the_best(bot, monkeypatch):
    real = optimizer.report.full_report

    def fake(cls, *a, **k):
        out = real(cls, *a, **k)
        if cls.params["rsi_below"] == 14:                # pretend this row's stops sat a few cents away
            out["untested"] = out["untested"] | {"avg_r": 9.9, "trades": 99, "tight_stop_trades": 40,
                                                 "total_r": 980.0, "without_tight_stops_r": -5.0}
        return out
    monkeypatch.setattr(optimizer.report, "full_report", fake)
    out = optimizer.optimize(bot, "rsi_below", "stop_ranges", ["SPY"], fetch=demo.bars, save=False)
    assert out.get("best", {}).get("rsi_below") != 14 and "5 cells had stops" in out["tight_stop_cells"]
    assert "⚠" in optimizer.markdown(out)


def test_all_cells_tight_says_widen_the_stop(bot, monkeypatch):
    real = optimizer.report.full_report

    def fake(cls, *a, **k):
        out = real(cls, *a, **k)
        out["untested"] = out["untested"] | {"trades": 99, "avg_r": 2.0, "tight_stop_trades": 40, "total_r": 198.0,
                                             "without_tight_stops_r": -5.0}
        return out
    monkeypatch.setattr(optimizer.report, "full_report", fake)
    out = optimizer.optimize(bot, "rsi_below", "stop_ranges", ["SPY"], fetch=demo.bars, save=False)
    assert "widen the stop first" in out["verdict"] and "best" not in out


def test_small_settings_keep_every_step():
    assert optimizer._values(0.002, optimizer.STEPS_INTRADAY) == [0.0015, 0.002, 0.0025]   # was 0.002, 0.003
    assert optimizer._values(2.0, optimizer.STEPS_DAILY) == [1.2, 1.6, 2.0, 2.4, 2.8]
    assert optimizer._values(200, optimizer.STEPS_DAILY) == [120, 160, 200, 240, 280]


def test_when_every_cell_loses_the_verdict_says_settings_dont_fix_it(bot, monkeypatch):
    real = optimizer.report.full_report
    def losing(cls, *a, **kw):
        out = real(cls, *a, **kw)
        u = out["untested"]
        if u.get("avg_r") is not None:
            u["avg_r"] = -abs(u["avg_r"]) - 0.001 * cls.params["rsi_below"]
        return out
    monkeypatch.setattr(optimizer.report, "full_report", losing)
    out = optimizer.optimize(bot, "rsi_below", "stop_ranges", ["SPY"], fetch=demo.bars, save=False)
    assert out["verdict"].startswith("no cell makes money after costs") and "doesn't fix this bot" in out["verdict"]
    md = optimizer.markdown(out)
    assert "★" not in md and "**Verdict:** no cell makes money" in md and "Held-out" in md and "Luck in the best" in md


def test_each_symbol_and_window_is_fetched_once_per_run():
    calls = []

    def fetch(*args):
        calls.append(args)
        if args[0] == "BAD":
            raise ConnectionError("no data")
        return [args[0]]
    get = optimizer._once(fetch)
    assert get("SPY", 1, 2) == ["SPY"] and get("SPY", 1, 2) == ["SPY"] and get("SPY", 1, 3) == ["SPY"]
    assert len(calls) == 2
    for _ in range(2):                    # a failure is never remembered: each cell says the symbol had no data
        with pytest.raises(ConnectionError):
            get("BAD", 1, 2)
    assert len(calls) == 4
    get("SPY", 1, 2).append("changed")    # one cell can't change the bars the next cell sees
    assert get("SPY", 1, 2) == ["SPY"]
