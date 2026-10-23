"""Offline checks that the format works beyond 1-minute bots: a 15-minute bot, a daily swing bot that holds for
days, and the end-of-day paper log."""
from datetime import date, datetime, timedelta

import pytest

from botscope import backtest, daily_log, data, journal, loader, view
from botscope.bot import BarData
from botscope.data import ET


def bar(t, o, h, l, c, v=1000):  # noqa: E741
    return BarData(t, o, h, l, c, v)


def inside_bar_day():
    """15-minute candles: a wide 'mother' candle, an inside candle, a close above the mother's high, then a climb."""
    t0 = datetime(2026, 9, 1, 9, 30, tzinfo=ET)
    px = [(100, 100.3, 99.9, 100.2), (100.2, 100.6, 100.1, 100.5),
          (100.5, 101.2, 100.3, 101.0),                                                             # mother 100.3-101.2
          (101.0, 101.1, 100.6, 100.9),                                                             # inside 100.6-101.1
          (100.9, 101.5, 100.85, 101.4),                                                            # breakout (10:30)
          ] + [(101.4 + i * 0.1, 101.6 + i * 0.1, 101.3 + i * 0.1, 101.5 + i * 0.1) for i in range(21)]
    return [bar(t0 + timedelta(minutes=15 * i), *p) for i, p in enumerate(px)]


def daily_series():
    """30 trading days: wide days, one very narrow day, then a close above it and a steady climb."""
    d0, out = datetime(2026, 6, 1, tzinfo=ET), []
    for i in range(30):
        if i == 10:
            out.append(bar(d0 + timedelta(days=i), 100, 100.2, 99.9, 100.1))       # NR7 day
        elif i < 10:
            out.append(bar(d0 + timedelta(days=i), 100, 102, 98, 100))
        else:
            c = 100.5 + (i - 11) * 0.05
            out.append(bar(d0 + timedelta(days=i), c - 0.2, c + 0.3, c - 0.4, c))
    return out


def test_inside_bar_buys_the_breakout_then_hits_target():
    bot = loader.get("inside_bar_breakout")()
    trace = []
    trades, problems = backtest.run_day(bot, "TEST", date(2026, 9, 1), inside_bar_day(), backtest.COSTS[bot.asset],
                                        trace=trace)
    assert not problems and len(trades) == 1
    t = trades[0]
    assert t.side == "long" and t.stop == pytest.approx(100.6) and t.t_in.startswith("2026-09-01T10:30")
    assert t.why_out == "target hit"
    assert backtest.no_peek_check(bot, inside_bar_day()) is None


def test_daily_swing_holds_for_days_and_exits_on_time():
    bot = loader.get("nr7_swing")()
    bs = daily_series()
    trace = []
    trades, problems = backtest.run_day(bot, "TEST", bs[-1].t.date(), bs, backtest.COSTS[bot.asset], trace=trace,
                                        close_at_end=True)
    assert not problems and trades
    t = trades[0]
    assert t.side == "long" and t.stop == pytest.approx(99.9)
    held = (datetime.fromisoformat(t.t_out) - datetime.fromisoformat(t.t_in)).days
    assert held >= 10 and t.why_out == "held 10 trading days"
    assert t.day == t.t_in[:10] != str(bs[-1].t.date())       # the entry day, not the window's last day
    assert any("inside the NR7" in x["reason"] for x in trace)


def test_sessions_keeps_daily_window_whole():
    bs = daily_series()
    assert list(data.sessions(bs, "1Day")) == [bs[-1].t.date()]
    assert len(data.sessions(bs, "1Day")[bs[-1].t.date()]) == 30


def test_daily_log_saves_closed_trades(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_JOURNAL_DIR", str(tmp_path))
    from test_format import fake_day
    monkeypatch.setattr(data, "view_bars", lambda sym, d, tf, days=0: (fake_day() if tf == "5Min" else inside_bar_day() if tf == "15Min"
                                                               else daily_series(), "test"))
    out = daily_log.run(date(2026, 9, 1))
    assert out["new_results"] >= 5 and not out["problems"]
    assert daily_log.run(date(2026, 9, 1))["new_results"] == 0          # running twice adds nothing
    assert {r["bot"] for r in journal.load("paper_results")} >= {"first_hour_breakout", "inside_bar_breakout"}


def test_daily_bot_only_logs_trades_entered_after_tracking_starts(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "view_bars", lambda sym, d, tf, days=0: (daily_series(), "test"))
    cls = loader.get("nr7_swing")
    late = daily_log.log_daily_bot("nr7_swing", cls, date(2026, 7, 30))      # tracking starts after the trade
    assert sum(x["new_results"] for x in late) == 0
    journal.remove("live_since", journal.load("live_since")[0]["id"])
    early = daily_log.log_daily_bot("nr7_swing", cls, date(2026, 6, 1))      # tracking started before it
    assert sum(x["new_results"] for x in early) == len(cls.symbols)
    rows = journal.find("paper_results", bot="nr7_swing")
    assert rows[0]["why_out"] == "held 10 trading days" and rows[0]["entered"] == "2026-06-12"
    assert sum(x["new_results"] for x in daily_log.log_daily_bot("nr7_swing", cls, date(2026, 7, 1))) == 0   # no repeats
