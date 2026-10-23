"""Offline checks of the morning brief."""
from datetime import date

from botscope import brief, preflight, settings

D = date(2026, 10, 16)
W = {"weather": "choppy", "mood": "normal", "as_of_close": "2026-10-15", "why": []}
EV = [{"date": "2026-10-16", "event": "CPI (8:30 AM, before open)", "source": "FRED"},
      {"date": None, "event": "unavailable: timeout", "source": "Finnhub"}]


def test_three_lines_with_sources():
    b = brief.brief(D, weather=W, events=EV)
    assert len(b["lines"]) == 3 and "choppy" in b["lines"][0] and "CPI" in b["lines"][1]
    assert b["lines"][2].startswith("Bots: none on") and "Alpaca" in b["sources"]


def test_on_bot_shows_what_it_watches_and_its_confidence():
    preflight.answer({"nr7_swing": True}, D)
    line = brief.brief(D, weather=W, events=[])["lines"][2]
    assert "watches" in line and "confidence" in line and "%" not in line


def test_stop_wins_and_unknown_weather_says_why():
    preflight.answer({"nr7_swing": True}, D)
    settings.change(stopped=True)
    b = brief.brief(D, weather={"error": "no keys"}, events=[])
    assert "STOP" in b["lines"][2] and "unknown (no keys)" in b["lines"][0]
    assert "no scheduled" in b["lines"][1]


def test_push_uses_your_phone_topic_only_when_asked():
    sent = []
    b = brief.brief(D, weather=W, events=[], push=True, send=lambda t, m, tags: sent.append(m) or {"sent": True})
    assert sent and sent[0].count("\n") == 2 and b["phone"]["sent"]
    assert "phone" not in brief.brief(D, weather=W, events=[])


def test_on_bot_gets_its_weather_fit_only_when_measured():
    from botscope import journal
    preflight.answer({"nr7_swing": True}, D)
    assert "weather" not in brief.brief(D, weather=W, events=[])["lines"][2]
    journal.upsert("weather_fit", {"bot": "nr7_swing"},
                   {"by_weather": [{"weather": "choppy", "trades": 14, "avg_r": -0.2, "total_r": -2.8}]})
    assert "struggles in choppy weather" in brief.brief(D, weather=W, events=[])["lines"][2]


def test_points_at_the_autopsy_only_after_a_losing_last_day():
    from botscope import journal
    preflight.answer({"nr7_swing": True}, D)
    for day, r in (("2026-10-14", -1.0), ("2026-10-15", 0.5)):
        journal.upsert("paper_results", {"bot": "nr7_swing", "symbol": "SPY", "day": day, "trade_id": day}, {"r": r})
    assert "loss_autopsy" not in brief.brief(D, weather=W, events=[])["lines"][2]      # the last day made money
    journal.upsert("paper_results", {"bot": "nr7_swing", "symbol": "SPY", "day": "2026-10-16", "trade_id": "x"}, {"r": -0.7})
    assert "lost -0.70R on 10-16 (loss_autopsy says why)" in brief.brief(D, weather=W, events=[])["lines"][2]


def test_event_day_note_only_for_todays_event_with_enough_trades():
    from botscope import journal
    preflight.answer({"nr7_swing": True}, D)
    journal.upsert("event_fit", {"bot": "nr7_swing"}, {"groups": [
        {"days": "CPI inflation", "trades": 12, "avg_r": -0.43, "total_r": -5.2, "verdict": "loses money here"},
        {"days": "GDP", "trades": 4, "avg_r": 0.5, "total_r": 2.0, "verdict": "too few trades to say (4, need 10+)"}]})
    cpi = [{"date": "2026-10-16", "event": "CPI inflation (8:30 AM ET)", "source": "FRED"}]
    line = brief.brief(D, weather=W, events=cpi)["lines"][2]
    assert "loses money on CPI inflation days (-0.43R a trade over 12 untested)" in line
    gdp = [{"date": "2026-10-16", "event": "GDP (8:30 AM ET)", "source": "FRED"}]
    assert "GDP" not in brief.brief(D, weather=W, events=gdp)["lines"][2]


def test_red_flag_is_named_not_just_a_symbol(relabel):
    relabel("first_hour_breakout", status="failed")
    preflight.answer({"first_hour_breakout": True}, D)
    line = brief.brief(D, weather=W, events=[])["lines"][2]
    assert "⚠ labeled failed" in line


def test_phone_push_only_once_a_day_unless_forced():
    sent = []
    send = lambda t, m, tags: sent.append(m) or {"sent": True}
    brief.brief(D, weather=W, events=[], push=True, send=send)
    b = brief.brief(D, weather=W, events=[], push=True, send=send)
    assert len(sent) == 1 and "already sent today" in b["phone"]["why"]
    brief.brief(D, weather=W, events=[], push=True, send=send, force=True)
    assert len(sent) == 2


def test_closed_market_day_says_no_bot_trades():
    preflight.answer({"nr7_swing": True}, D)
    hol = [{"date": "2026-11-26", "event": "Market closed (holiday)", "source": "Alpaca calendar"}]
    assert brief.brief(date(2026, 11, 26), weather=W, events=hol)["lines"][2] == \
        "Bots: stock market closed today (holiday), no stock bot trades"
    assert "Saturday" in brief.brief(date(2026, 10, 17), weather=W, events=[])["lines"][2]
    assert "closed" not in brief.brief(D, weather=W, events=[])["lines"][2]


def test_closed_stock_market_still_lists_crypto_bots_that_are_on():
    sat = date(2026, 10, 17)
    preflight.answer({"crypto_trend": True, "nr7_swing": True}, sat)
    line = brief.brief(sat, weather=W, events=[])["lines"][2]
    assert "stock market closed today (Saturday)" in line and "crypto trades every day" in line
    assert "Crypto trend" in line and "BTC/USD" in line and "NR7" not in line
