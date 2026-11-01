import pytest

from botscope import journal, trade_import, trade_notes


def _trades():
    trade_import.from_text("fills", "symbol,side,qty,price,time\nSPY,buy,10,100,2026-10-05T09:31:00\n"
                           "SPY,sell,10,104,2026-10-05T10:00:00\nQQQ,sell,1,50,2026-10-05T11:00:00\n"
                           "QQQ,buy,1,51,2026-10-05T11:30:00\n", "t.csv", "America/New_York")
    return trade_import.trades()


def test_note_gives_setup_r_and_stays_after_reimport():
    spy, qqq = _trades()
    out = trade_notes.note(spy["trade_id"], "Pullback ", 98, "waited for the dip", {"feeling": "Calm", "trades_today": "0"})
    assert out["setup"] == "pullback" and out["stop"] == 98 and out["r"] == 2.0          # +4 on a 2 risk
    assert out["checklist"] == {"feeling": "calm", "trades_today": "0"}
    assert trade_notes.note(qqq["trade_id"], stop=52)["r"] == -0.5                        # a short: lost 1 on a 2 risk
    _trades()                                                                            # imported again
    got = {t["symbol"]: t for t in trade_notes.with_notes(trade_import.trades())}
    assert got["SPY"]["r"] == 2.0 and got["SPY"]["note"] == "waited for the dip" and got["QQQ"]["setup"] is None


def test_left_out_fields_stay_and_empty_clears():
    spy, _ = _trades()
    tid = spy["trade_id"]
    trade_notes.note(tid, "breakout", 99, "x", {"feeling": "rushed"})
    out = trade_notes.note(tid, checklist={"last_trade": "loss"})
    assert out["setup"] == "breakout" and out["stop"] == 99 and out["checklist"] == {"feeling": "rushed", "last_trade": "loss"}
    out = trade_notes.note(tid, setup="", stop=0, note="")
    assert out["setup"] is None and out["stop"] is None and out["r"] is None and out["note"] is None
    assert len(journal.load("trade_notes")) == 1                                         # one note per trade


def test_bad_input_says_what_is_wrong():
    spy, qqq = _trades()
    with pytest.raises(ValueError, match="no trade with id"):
        trade_notes.note("nope", "x")
    with pytest.raises(ValueError, match="long's stop is below"):
        trade_notes.note(spy["trade_id"], stop=101)
    with pytest.raises(ValueError, match="short's stop is above"):
        trade_notes.note(qqq["trade_id"], stop=49)
    with pytest.raises(ValueError, match="unknown checklist question"):
        trade_notes.note(spy["trade_id"], checklist={"should_i_buy": "yes"})
    with pytest.raises(ValueError, match="'feeling' is one of"):
        trade_notes.note(spy["trade_id"], checklist={"feeling": "lucky"})


def test_demo_trades_come_with_their_notes():
    out = trade_import.from_demo()
    ts = trade_notes.with_notes(trade_import.trades())
    assert out["round_trips"] == len(ts) and all(t["setup"] for t in ts)       # every demo trade has its note
    assert sum(t["r"] is not None for t in ts) < len(ts)                        # some have no stop, so no R
