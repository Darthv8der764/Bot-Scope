"""Ask a market question: plain English -> a one-off honest test (tuned vs untested years, costs, vs SPY, confidence)."""
import json
from datetime import date, datetime, timedelta

from botscope import demo, question as q
from botscope.bot import BarData, View


def test_parses_the_common_questions():
    p = q.parse("how did buying SPY on red Mondays do?")
    assert p["symbols"] == ["SPY"] and p["side"] == "long" and ("weekday", [0]) in p["conds"] and ("candle", "red") in p["conds"]
    p = q.parse("buy qqq after 3 down days in a row, hold 5 days")
    assert p["symbols"] == ["QQQ"] and ("streak", 3, True) in p["conds"] and p["hold_days"] == 5
    p = q.parse("short IWM when it gaps up 1%, stop 2%")
    assert p["side"] == "short" and ("gap", "up", 1.0) in p["conds"] and p["stop_pct"] == 2.0
    assert ("move", True, 1.0) in q.parse("spy on fridays after a 1% drop")["conds"]
    assert ("extreme", 20, "high") in q.parse("SPY at a new 20-day high, hold a month")["conds"]
    assert ("avg", 200, False) in q.parse("buy SPY below the 200-day average")["conds"]
    assert "intraday" in q.parse("buy SPY in the first 30 minutes on Mondays")["not_understood"]


def test_unclear_question_asks_for_a_rule_instead_of_guessing():
    out = q.ask("what about tomorrow?")
    assert "error" in out and out["try_one_like"]


def _bars(closes_opens):
    d0 = datetime(2026, 1, 5, tzinfo=demo.ET)            # a Monday
    return [BarData(d0 + timedelta(days=i), o, max(o, c), min(o, c), c, 1) for i, (o, c) in enumerate(closes_opens)]


def test_the_rules_only_see_finished_days_and_do_what_they_say():
    bot = q.make_bot(q.parse("buy SPY on red Mondays"))()
    week = _bars([(100, 101), (101, 102), (102, 103), (103, 104), (104, 105), (105, 106), (106, 107), (108, 107)])
    v = View("SPY", week[:8], {})                         # the 8th day is a Monday (Jan 12) that closed red
    assert type(bot.entry(v)).__name__ == "Entry"
    assert type(bot.entry(View("SPY", week[:7], {}))).__name__ == "NoTrade"


def test_answer_is_honest_counts_tuned_and_untested(monkeypatch):
    monkeypatch.setenv("BOTSCOPE_DEMO", "1")
    out = q.ask("how did buying SPY on red Mondays do?", fetch=demo.bars, today=date(2026, 10, 16))
    assert out["tuned_years"] == [2025, 2026] and 2016 in out["untested_years"]
    assert out["untested"]["trades"] > 30 and "costs_usd" in out["untested"]
    assert out["confidence"]["level"] in out["confidence"]["levels"] and "vs_spy" in out
    assert "win" not in json.dumps(out).lower()           # counts and R, never a win %
    assert "TUNED" in out["tuned_note"]
    out2 = q.ask("buy SPY after 2 down days in a row", fetch=demo.bars, idea_from="elsewhere", today=date(2026, 10, 16))
    assert out2["tuned_years"] == [] and out2["questions_asked"] == 2 and "questions_note" in out2


def test_server_tool_exists():
    from botscope import server
    assert "error" in server.ask_market_question("what about tomorrow?")


def test_sell_means_short_names_mean_pairs_and_weeks_mean_days():
    r = q.parse("sell SPY after 5 up days")
    assert r["side"] == "short" and r["conds"] == [("streak", 5, False)]
    assert q.parse("buy SPY, sell after 5 days")["side"] == "long"            # an exit, not a short
    r = q.parse("buy AAPL when it hits a new 52-week high")
    assert r["conds"] == [("extreme", 260, "high")] and "(52-week)" in r["rules"][0]
    assert q.parse("buy SPY above its 40-week average")["conds"] == [("avg", 200, True)]
    r = q.parse("buy bitcoin after 2 red days in a row")
    assert r["symbols"] == ["BTC/USD"] and r["conds"] == [("streak", 2, True)]
    assert q.parse("buy ETH on Mondays")["symbols"] == ["ETH/USD"]


def test_weekend_days_work_for_crypto_and_are_never_widened_for_stocks():
    from botscope import question as q
    p = q.parse("buy ETH after a red sunday")
    assert ("weekday", [6]) in p["conds"] and ("candle", "red") in p["conds"]
    assert "Sunday" in p["rules"][0] and not p.get("not_understood")
    for text in ("buy SPY on Saturdays", "buy SPY on red Sundays"):
        p = q.parse(text)
        assert p["conds"] == [] and "don't trade on Saturdays or Sundays" in p["not_understood"]
        out = q.ask(text)
        assert "error" in out and "Saturdays or Sundays" in out["not_understood"]
    p = q.parse("buy SPY on Mondays and Sundays")
    assert ("weekday", [0]) in p["conds"] and "left out" in p["not_understood"]
