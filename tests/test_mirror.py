"""Offline checks of the mistake mirror (made-up trades and bars)."""
from datetime import date, time

import pytest

from botscope import loader, mirror
from test_format import fake_day

CSV = """Date,Time,Ticker,Side,Entry,Exit,Stop
2026-09-01,10:55,TEST,buy,100.6,103,99.4
2026-09-01,10:50,TEST,sell,100.5,101.5,
2026-09-01,09:35,TEST,long,100,99,
2026-09-01,09:40,FLAT,long,100,99,
"""


def bars_for(sym, d, tf):
    if tf != "5Min":
        return []
    return fake_day()[:20] if sym == "FLAT" else fake_day()          # FLAT: the range never finishes


def test_read_and_your_result(tmp_path):
    p = tmp_path / "t.csv"; p.write_text(CSV)
    t = mirror.read_trades(p)
    assert t[0] == {"date": date(2026, 9, 1), "time": time(10, 55), "symbol": "TEST", "side": "long", "entry": 100.6,
                    "exit": 103.0, "stop": 99.4}
    assert t[1]["side"] == "short" and t[1]["stop"] is None
    assert mirror.your_result(t[0]) == {"pct": 2.39, "r": 2.0}
    assert mirror.your_result(t[1]) == {"pct": -1.0}


def test_bad_rows_say_which_line(tmp_path):
    p = tmp_path / "t.csv"; p.write_text("date,symbol,side,entry,exit\n2026-09-01,TEST,maybe,1,2\n")
    with pytest.raises(ValueError, match="line 2"):
        mirror.read_trades(p)


def test_verdicts_against_the_example_bot(tmp_path):
    p = tmp_path / "t.csv"; p.write_text(CSV)
    out = mirror.mirror(str(p), ["first_hour_breakout"], bars_for=bars_for)
    v = [r["bots"]["first_hour_breakout"]["verdict"] for r in out["trades"]]
    assert v == ["agreed", "went the other way", "same side, different time", "stayed out"]
    assert "opening range" in out["trades"][2]["bots"]["first_hour_breakout"]["bot_at_your_time"]   # its reason at 09:35
    assert "opening range" in out["trades"][3]["bots"]["first_hour_breakout"]["why"]
    s = out["summary"]
    assert s["a_bot_agreed"] == 1 and s["every_bot_stayed_out"] == 1 and s["your_avg_pct_when_a_bot_agreed"] == 2.39
    assert s["your_avg_pct_when_bots_stayed_out"] == -1.0 and out["lines"][0].startswith("Your trades did better when the bots agreed")
    assert any("too few" in x for x in out["lines"]) and "didn't copy" in out["privacy"]


def test_missing_csv_says_what_to_export():
    from botscope import server
    out = server.mistake_mirror("/no/such/trades.csv")
    assert "no file at /no/such/trades.csv" in out["error"] and "date, time, symbol" in out["error"]
