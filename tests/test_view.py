"""Offline checks of the bot view: why-not reasons, veto, moved stop, drawings, and the localhost guard."""
import json
from datetime import date, timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from botscope import backtest, journal, loader, view
from test_format import fake_day


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_JOURNAL_DIR", str(tmp_path))
    monkeypatch.setattr(view.data, "day_bars", lambda sym, d, tf: (fake_day(), "made-up test bars"))


ARGS = ("first_hour_breakout", "TEST", "2026-09-01")


def test_trace_has_a_reason_for_every_bar():
    st = view.build(*ARGS)
    assert len(st["reasons"]) == len(st["candles"]) == 390
    kinds = {r["kind"] for r in st["reasons"].values()}
    assert {"no_trade", "entry", "exit"} <= kinds
    assert st["trades"][0]["why_out"] == "target hit" and st["account"] == "PAPER"


def test_why_not_here():
    assert "opening range" in view.why_not_here(*ARGS, "09:35")["reason"]


def test_veto_skips_trade_and_keeps_would_have_result():
    tid = view.build(*ARGS)["trades"][0]["id"]
    view.veto(*ARGS, tid, "looks stretched")
    st = view.build(*ARGS)
    assert not st["trades"] and st["vetoed"][0]["would_have_r"] > 1.5
    assert journal.load("vetoes")[0]["reason"] == "looks stretched"
    view.undo_veto(*ARGS, tid)
    assert view.build(*ARGS)["trades"]


def test_move_asks_scope_first_then_replays():
    t = view.build(*ARGS)["trades"][0]
    q = view.move_lines(*ARGS, t["id"], stop=t["entry"] - 0.05)
    assert "question" in q and not journal.load("trade_overrides")
    view.move_lines(*ARGS, t["id"], stop=t["entry"] - 0.05, scope="this_trade")
    t2 = view.build(*ARGS)["trades"][0]
    assert t2["moved"] and t2["stop"] == pytest.approx(t["entry"] - 0.05)
    idea = view.move_lines(*ARGS, t["id"], target=t["entry"] + 0.5, scope="rule")
    assert "backtest" in idea["rule_idea"]["status"]
    with pytest.raises(ValueError):
        view.move_lines(*ARGS, t["id"], stop=t["entry"] + 1, scope="this_trade")   # long stop above entry


def test_live_money_needs_confirm(monkeypatch):
    monkeypatch.setattr(view, "is_live_money", lambda: True)
    t = view.build(*ARGS)["trades"][0]
    r = view.move_lines(*ARGS, t["id"], stop=t["entry"] - 0.05, scope="this_trade")
    assert r.get("needs") == "confirm=true"


def test_drawings_round_trip_with_context():
    c = view.build(*ARGS)["candles"]
    view.add_drawing(*ARGS, "circle", [{"time": c[40]["time"], "price": 101}, {"time": c[60]["time"], "price": 102}], "bad")
    d = view.drawings_for_claude("first_hour_breakout")[0]
    assert d["note"] == "bad" and d["circle"]["from_time"] == "10:10" and d["candles_under"]["count"] == 21


def test_server_blocks_other_sites():
    base = view.ensure_server()
    ok = json.loads(urlopen(base + "/api/view?bot=first_hour_breakout&symbol=TEST&day=2026-09-01").read())
    assert ok["symbol"] == "TEST"
    bad = Request(base + "/api/veto", data=b"{}", headers={"Content-Type": "application/json", "Origin": "https://evil.example"})
    with pytest.raises(HTTPError) as e:
        urlopen(bad)
    assert e.value.code == 403


def test_empty_chart_says_why():
    from datetime import date
    from botscope.view import empty_reason
    today = date(2026, 10, 15)
    assert "Saturday, the market is closed" in empty_reason(date(2026, 10, 10), today)
    assert "hasn't happened yet" in empty_reason(date(2026, 10, 20), today)
    assert "opens at 9:30" in empty_reason(today, today)
    assert "holiday" in empty_reason(date(2026, 9, 7), today)


def test_quiz_hides_the_answer_and_scores_in_counts():
    from pathlib import Path
    html = (Path(__file__).resolve().parent.parent / "botscope" / "web" / "bot_view.html").read_text()
    assert 'id="r-quiz"' in html and "quizAt - 1" in html                  # markers stop before the asked candle
    assert "Hidden during the quiz." in html and "select(null)" in html    # no stop line or trade card gives it away
    assert 'api("/api/quiz"' in html and "Last 7 days: matched the bot on" in html
    assert "of ${quiz.n}</b> candles" in html and "Matching the bot doesn't make a trade good" in html


def test_quiz_score_counts_first_try_only_and_sums_the_week(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_JOURNAL_DIR", str(tmp_path))
    bot = next(iter(loader.load_all()[0]))
    first = view.quiz_score(bot, "AAPL", "2026-10-14", 3, 4)
    assert first["counted"] and first["week"] == {"quizzes": 1, "hits": 3, "candles": 4}
    again = view.quiz_score(bot, "AAPL", "2026-10-14", 4, 4)              # retake: answers already seen
    assert not again["counted"] and again["week"]["hits"] == 3
    assert view.quiz_score(bot, "NVDA", "2026-10-14", 1, 2)["week"] == {"quizzes": 2, "hits": 4, "candles": 6}
    with pytest.raises(ValueError):
        view.quiz_score(bot, "AAPL", "2026-10-15", 5, 4)


def test_chart_note_pins_to_one_candle_and_claude_reads_it():
    c = view.build(*ARGS)["candles"]
    view.add_drawing(*ARGS, "note", [{"time": c[30]["time"], "price": 100.6}], "news hit here")
    d = view.drawings_for_claude("first_hour_breakout")[-1]
    assert d["note"] == "news hit here" and d["kind"] == "note"
    with pytest.raises(ValueError):
        view.add_drawing(*ARGS, "note", [{"time": c[30]["time"], "price": 100.6}], "  ")


def test_crypto_charts_know_weekends_are_trading_days(monkeypatch):
    from datetime import date, datetime
    from botscope import data, view
    sat_morning = datetime(2026, 10, 17, 8, 0, tzinfo=data.ET)
    monkeypatch.setattr(data, "day_bars", lambda sym, d, tf: ([1], []))
    assert view.latest_session("BTC/USD", "5Min", sat_morning) == date(2026, 10, 17)
    assert view.latest_session("SPY", "5Min", sat_morning) == date(2026, 10, 16)
    assert view.latest_session("BTC/USD", "1Day", sat_morning) == date(2026, 10, 16)
    sun = datetime(2026, 10, 18, 12, 0, tzinfo=data.ET)
    assert view.latest_session("BTC/USD", "1Day", sun) == date(2026, 10, 17)
    assert view.latest_session("SPY", "1Day", sun) == date(2026, 10, 16)
    msg = view.empty_reason(date(2026, 10, 10), date(2026, 10, 15), crypto=True)
    assert "closed" not in msg and "Pick a weekday" not in msg
