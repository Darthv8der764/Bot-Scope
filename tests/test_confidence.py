"""Offline checks of the confidence meter, the live paper log and the veto scorecard."""
from datetime import timedelta

import pytest

from botscope import confidence, journal, loader, view
from botscope.confidence import meter
from test_format import fake_day


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_JOURNAL_DIR", str(tmp_path))
    monkeypatch.setattr(view.data, "day_bars", lambda sym, d, tf: (fake_day(), "made-up test bars"))


def good(n, lo=5.0):
    return {"trades": n, "avg_r": 0.3, "total_r_range_5_50_95": [lo, 20.0, 40.0]}


def test_levels_from_untested_trades():
    assert meter(None)["level"] == "very low"
    assert meter(good(20))["level"] == "very low"                         # too few trades
    assert meter({"trades": 80, "avg_r": -0.1})["level"] == "very low"    # loses money
    assert meter(good(80, lo=-2))["level"] == "low"                       # could be luck
    assert meter(good(80))["level"] == "medium"


def test_little_live_history_caps_the_meter():
    m = meter(good(400))                                                  # great backtest, no live trades
    assert m["level"] == "medium" and any("capped" in w for w in m["why"])
    assert meter(good(400), [0.5] * 12)["level"] == "high"
    assert meter(good(400), [0.5] * 30)["level"] == "very high"
    assert meter(good(400), [-0.5] * 30)["level"] == "medium"             # losing live: down a level, capped at medium


def test_never_a_percentage():
    for m in (meter(good(400), [0.5] * 30), meter(None)):
        text = " ".join([m["level"], *m["why"], m["note"]])
        assert "%" not in text and m["level"] in confidence.LEVELS


def test_meter_reads_saved_backtest_and_live_log():
    journal.upsert("backtests", {"bot": "first_hour_breakout"}, {"untested": good(150)})
    assert confidence.for_bot("first_hour_breakout")["level"] == "medium"
    st = view.build("first_hour_breakout", "TEST", "2026-09-01")
    assert st["confidence"]["untested_trades"] == 150


def test_live_day_logs_closed_trades_once():
    cls = loader.get("first_hour_breakout")
    bs = fake_day()
    d = bs[0].t.date()
    view.log_paper_day("first_hour_breakout", "TEST", d, cls, bs)
    view.log_paper_day("first_hour_breakout", "TEST", d, cls, bs)
    rows = journal.load("paper_results")
    assert len(rows) == 1 and rows[0]["why_out"] == "target hit" and rows[0]["r"] > 0


def test_open_trade_is_not_a_result_yet():
    cls = loader.get("first_hour_breakout")
    bs = [b for b in fake_day() if b.t.hour < 10 or (b.t.hour == 10 and b.t.minute < 5)]   # entry but no exit yet
    view.log_paper_day("first_hour_breakout", "TEST", bs[0].t.date(), cls, bs)
    assert not journal.load("paper_results")


def test_veto_scorecard_says_hurt_when_vetoed_trade_would_have_won():
    assert view.veto_scorecard()["verdict"] == "no vetoes to grade yet"
    args = ("first_hour_breakout", "TEST", "2026-09-01")
    tid = view.build(*args)["trades"][0]["id"]
    view.veto(*args, tid, "looks stretched")
    sc = view.veto_scorecard("first_hour_breakout")
    row = sc["rows"][0]
    assert row["verdict"] == "hurt" and row["your_reason"] == "looks stretched" and row["would_have_r"] > 1.5
    assert sc["hurt"] == 1 and sc["net_r_saved"] < 0 and "hurt" in sc["verdict"] and "luck" in sc["verdict"]


def test_veto_scorecard_lists_vetoes_it_cannot_replay():
    journal.add("vetoes", {"bot": "first_hour_breakout", "symbol": "TEST", "day": "2026-09-01", "trade_id": "TEST_gone"})
    sc = view.veto_scorecard()
    assert sc["rows"][0]["verdict"] == "unknown" and "problem" in sc["rows"][0]


def test_next_level_says_what_would_move_it_in_counts():
    assert meter({"trades": 12, "avg_r": 0.2})["next_level"].startswith("18 more untested trades")
    assert "more trades alone won't" in meter({"trades": 900, "avg_r": -0.08})["next_level"]
    assert meter(good(50))["next_level"] == "10 more closed live paper trades that hold up"      # medium, capped by live
    assert meter(good(50), [0.5] * 10)["next_level"] == "50 more untested trades that keep making money"
    assert meter(good(400), [0.5] * 30)["next_level"] == "already at the top level"
    assert "%" not in meter(good(50))["next_level"]


def test_r_from_tight_stops_means_very_low():
    u = {"trades": 300, "avg_r": 2.0, "total_r": 600.0, "total_r_range_5_50_95": [50, 600, 1200],
         "tight_stop_trades": 54, "without_tight_stops_r": -81.4}
    m = confidence.meter(u)
    assert m["level"] == confidence.LEVELS[0] and "R can't be trusted" in m["why"][-1]
