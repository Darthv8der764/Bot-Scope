"""Offline checks of the loss autopsy."""
from botscope import autopsy, journal
from botscope.backtest import Trade


def _log(day, sym, tid, r, why="stop", bot="nr7_swing"):
    journal.upsert("paper_results", {"bot": bot, "symbol": sym, "day": day, "trade_id": tid},
                   {"side": "long", "r": r, "why_out": why, "entered": day})


def _trade(sym, t_in, r, cost_pct, why="stop"):
    return Trade(sym, t_in[:10], "long", 10, 9.8, 9.9, "", why, r, r, cost_pct, t_in=t_in, t_out=t_in, risk_pct=1.0)


def test_no_losing_day_says_so():
    _log("2026-10-14", "SPY", "SPY_2026-10-14_0945", 0.8, "target")
    assert autopsy.autopsy()["found"] is False


def test_four_checks_costs_and_a_gap():
    _log("2026-10-14", "SPY", "SPY_2026-10-14_0945", 0.4, "target")
    _log("2026-10-14", "QQQ", "QQQ_2026-10-14_1000", -1.6)
    journal.add("backtests", {"bot": "nr7_swing", "untested": {"max_drawdown_r": -6.0}})
    trades = {"SPY_2026-10-14_0945": _trade("SPY", "2026-10-14T09:45:00-04:00", 0.4, 0.3, "target"),
              "QQQ_2026-10-14_1000": _trade("QQQ", "2026-10-14T10:00:00-04:00", -1.6, 0.6)}
    a = autopsy.autopsy(replay=lambda cls, sym, d: {k: v for k, v in trades.items() if k.startswith(sym)},
                        weather_on=lambda d: "choppy", spy_move=lambda d: -0.012)
    c = {x["check"]: x["found"] for x in a["checks"]}
    assert a["found"] and a["total_r"] == -1.2 and set(c) == {"market", "market move", "costs", "fills", "other bots", "normal?"}
    assert "choppy" in c["market"] and "isn't measured" in c["market"]
    assert "turned it into a loss" not in c["costs"] and "0.90R" in c["costs"]
    assert "QQQ stop exit at -1.60R" in c["fills"] and "inside what it already did" in c["normal?"]
    assert a["chart_path"].endswith("day=2026-10-14")


def test_worse_than_testing_points_at_the_chart_and_unmatched_trades_say_unknown():
    _log("2026-10-15", "SPY", "SPY_2026-10-15_0945", -3.0)
    journal.add("backtests", {"bot": "nr7_swing", "untested": {"max_drawdown_r": -2.0}})
    a = autopsy.autopsy(day="2026-10-15", replay=lambda *a: {}, weather_on=lambda d: "panic")
    c = {x["check"]: x["found"] for x in a["checks"]}
    assert "aren't known" in c["costs + fills"] and "rule that misfired" in c["normal?"]


def test_market_move_check_words():
    assert "against the bot's long trades" in autopsy.market_move_check(-0.012, ["long", "long"])
    assert "went with it" in autopsy.market_move_check(0.02, ["long"])
    assert "flat market" in autopsy.market_move_check(0.001, ["short"])
    assert "were mixed" in autopsy.market_move_check(0.01, ["long", "short"])


def test_other_bots_same_day():
    _log("2026-10-15", "SPY", "SPY_2026-10-15_0945", -1.0)
    _log("2026-10-15", "AAPL", "AAPL_2026-10-15_1000", -0.5, bot="first_hour_breakout")
    c = {x["check"]: x["found"] for x in autopsy.autopsy(bot="nr7_swing", replay=lambda *a: {},
                                                          weather_on=lambda d: "choppy", spy_move=lambda d: 0.0)["checks"]}
    assert c["other bots"].startswith("1 of 1 other bots also lost") and "whole lineup" in c["other bots"]
