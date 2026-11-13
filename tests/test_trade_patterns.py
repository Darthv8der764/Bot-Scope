import json
from datetime import datetime

from botscope import trade_import, trade_notes, trade_patterns as tp


def _t(i, opened, closed, pnl, r=None, setup=None):
    return {"trade_id": str(i), "opened": opened, "closed": closed, "pnl": pnl, "r": r, "setup": setup}


def test_rows_by_setup_hour_holding_and_trade_before_on_known_trades():
    ts = [_t(1, "2026-10-05T09:31:00", "2026-10-05T09:33:00", 10, 1.0, "pullback"),     # first of the day, a win
          _t(2, "2026-10-05T09:40:00", "2026-10-05T10:20:00", -20, None, "pullback"),   # after a win
          _t(3, "2026-10-05T10:25:00", "2026-10-05T13:00:00", -5, -0.5),                # after a loss, no tag
          _t(4, "2026-10-09T15:00:00", "2026-10-12T10:00:00", 30, 2.0, "breakout")]    # a Friday, held over a weekend
    out = tp.table(ts, min_trades=2)
    assert [(r["group"], r["trades"], r["won"], r["total_usd"], r["trades_with_r"], r["total_r"]) for r in out["by_setup"]] == [
        ("breakout", 1, 1, 30, 1, 2.0), ("pullback", 2, 1, -10, 1, 1.0), ("no tag yet", 1, 0, -5, 1, -0.5)]
    assert [r["group"] for r in out["by_hour"]] == ["9am-10am", "10am-11am", "3pm-4pm"]
    assert [(r["group"], r["trades"]) for r in out["by_weekday"]] == [("Monday", 3), ("Friday", 1)]
    assert [(r["group"], r["trades"]) for r in out["by_holding"]] == [
        ("under 5 min", 1), ("30 min to 2 h", 1), ("2 h to 1 day", 1), ("over 1 day", 1)]
    assert [(r["group"], r["trades"]) for r in out["by_trade_before"]] == [
        ("after a win", 1), ("after a loss", 1), ("first trade of the day", 2)]
    assert out["all"]["trades"] == 4 and out["all"]["avg_usd"] == 3.75


def test_rows_by_weekday_and_time_of_day_on_known_trades():
    ts = [_t(1, "2026-10-05T09:31:00", "2026-10-05T09:40:00", 10),     # Monday morning
          _t(2, "2026-10-05T11:59:00", "2026-10-05T12:30:00", -4),     # still morning: it's the entry that counts
          _t(3, "2026-10-05T12:00:00", "2026-10-05T12:10:00", 6),      # Monday afternoon from 12:00 on
          _t(4, "2026-10-09T13:05:00", "2026-10-09T14:00:00", -8),     # Friday afternoon
          _t(5, "2026-10-09T15:00:00", "2026-10-09T15:30:00", -2),
          _t(6, "2026-10-06T10:00:00", "2026-10-06T10:20:00", 3)]      # Tuesday morning
    out = tp.table(ts, min_trades=2)
    assert [(r["group"], r["trades"], r["won"], r["total_usd"]) for r in out["by_day_part"]] == [
        ("Monday morning", 2, 1, 6), ("Monday afternoon", 1, 1, 6), ("Tuesday morning", 1, 1, 3),
        ("Friday afternoon", 2, 0, -10)]
    fri = out["by_day_part"][-1]
    assert fri["enough"] and fri["avg_usd"] == -5
    assert out["by_day_part"][1]["note"] == "not enough trades yet (1, need 2+)"


def test_small_rows_say_not_enough_trades_yet_and_r_only_with_a_stop():
    out = tp.table([_t(1, "2026-10-05T09:31:00", "2026-10-05T09:40:00", 5)])
    r = out["by_setup"][0]
    assert not r["enough"] and r["note"] == "not enough trades yet (1, need 5+)"
    assert r["total_r"] is None and r["avg_r"] is None and r["trades_with_r"] == 0


def test_demo_trades_show_the_planted_patterns():
    trade_import.from_demo()
    out = tp.patterns()
    after = {r["group"]: r for r in out["by_trade_before"]}
    assert after["after a loss"]["enough"] and after["after a win"]["enough"]
    assert after["after a loss"]["avg_usd"] < 0 < after["after a win"]["avg_usd"]
    held = {r["group"]: r for r in out["by_holding"]}
    assert held["5 to 30 min"]["total_usd"] > 0 > held["2 h to 1 day"]["total_usd"]
    assert held["2 h to 1 day"]["won"] == 0
    trades = trade_notes.with_notes(trade_import.trades())
    fri_pm = [t for t in trades if datetime.fromisoformat(t["opened"]).weekday() == 4 and t["opened"][11:] >= "13:00"]
    rest = [t for t in trades if t not in fri_pm]
    fri, other = tp.row("x", fri_pm), tp.row("y", rest)
    assert fri["enough"] and fri["avg_usd"] < 0 and fri["avg_usd"] < other["avg_usd"] and fri["won"] * 2 < fri["trades"]
    parts = {r["group"]: r for r in out["by_day_part"]}                              # the table shows it too
    fri_row = parts["Friday afternoon"]
    assert fri_row["enough"] and fri_row["avg_usd"] < 0 and fri_row["avg_usd"] < out["all"]["avg_usd"]
    assert out["by_setup"][0]["trades_with_r"] < out["by_setup"][0]["trades"]       # some demo trades have no stop


def test_plain_numbers_only_no_advice_or_percent():
    trade_import.from_demo()
    text = json.dumps(tp.patterns()).lower()
    for word in ("win rate", "%", "should", "buy ", "sell ", "avoid", "stop trading", "habit", "revenge", "tilt"):
        assert word not in text
    assert tp.patterns.__module__ and "Not financial advice" in tp.patterns()["note"]


def test_no_trades_yet_says_so():
    assert tp.patterns()["trades"] == 0 and "no trades imported yet" in tp.patterns()["error"]


def test_date_only_trades_stay_out_of_the_time_tables():
    from botscope import demo_trades
    from tests.test_trade_import import ROBINHOOD
    none = {"rows": 0, "not_filled": 0, "unreadable": 0, "unreadable_lines": []}
    trade_import.save("fills file timed.csv", [trade_import.fill(**x) for x in demo_trades.fills()], none)
    timed = tp.patterns()
    trade_import.from_text("robinhood", ROBINHOOD, "rh.csv", None)
    out = tp.patterns()
    assert out["trades"] == timed["trades"] + 2 and out["date_only"] == 2 and "Robinhood" in out["date_only_note"]
    assert out["all"]["trades"] == timed["trades"] + 2
    assert sum(r["trades"] for r in out["by_weekday"]) == timed["trades"] + 2
    for k in ("by_hour", "by_day_part", "by_holding", "by_trade_before"):
        assert sum(r["trades"] for r in out[k]) == timed["trades"], k
    assert timed["date_only"] == 0 and timed["date_only_note"] is None


def test_a_date_range_keeps_only_those_trades():
    trade_import.from_demo()
    out = tp.patterns(since="2026-09-01", until="2026-09-30")
    assert out["from"] >= "2026-09-01" and out["to"] <= "2026-09-30"
    assert out["trades"] == sum(t["opened"].startswith("2026-09") for t in trade_import.trades())
    assert "no trades between" in tp.patterns(since="2027-01-01")["error"]
    assert "isn't a date" in tp.patterns(until="September")["error"]
