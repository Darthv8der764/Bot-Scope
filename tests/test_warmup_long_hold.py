"""A long-hold daily bot must start each test window flat: warm-up bars are history only, never a place to enter.

Before the fix, a monthly 200-day trend bot bought during the warm-up (late in the year before), the position stayed
open into the window and blocked every new entry, then was thrown away for starting too early: 0 trades all year.
"""
from datetime import date, datetime, timedelta

import pytest

from botscope import backtest, luck
from botscope.bot import BarData, Bot, Entry, Exit, NoTrade
from botscope.data import ET


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_JOURNAL_DIR", str(tmp_path))


def _bars():
    """Weekday daily bars, 2015 to 2018: a slow steady climb, so the close is always above its 200-day average."""
    out, d, px = [], date(2015, 1, 2), 100.0
    while d <= date(2018, 12, 31):
        if d.weekday() < 5:
            t = datetime(d.year, d.month, d.day, 16, 0, tzinfo=ET)
            out.append(BarData(t, px, px * 1.004, px * 0.996, px * 1.001, 1_000_000))
            px *= 1.001
        d += timedelta(days=1)
    return out


BARS = _bars()


def fetch(sym, start, end, tf, feed):
    return [b for b in BARS if start <= b.t.date() <= end]


def _month_end(d: date) -> bool:
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt.month != d.month


class MonthlyTrend(Bot):
    """Buy at a month-end close above the 200-day average; sell at a month-end close below it. Holds for months."""
    name, version, timeframe, symbols, sides, asset = "Monthly trend", "1.0", "1Day", ["TEST"], "long", "swing"
    max_trades_per_day, flat_by_close, lookback_days, params, tuned_on, status = 1, False, 200, {}, None, "untested"

    def indicators(self, bars):
        cs = [b.c for b in bars]
        return {"sma200": [sum(cs[i - 199:i + 1]) / 200 if i >= 199 else None for i in range(len(cs))]}

    def entry(self, view):
        sma = view.ind["sma200"][-1]
        if sma is None:
            return NoTrade("200-day average not filled yet")
        if not _month_end(view.now.date()):
            return NoTrade("not a month-end close")
        if view.last.c <= sma:
            return NoTrade("below the 200-day average")
        return Entry("long", view.last.c * 0.5, None, "month-end close above the 200-day average")

    def exit(self, view, pos):
        sma = view.ind["sma200"][-1]
        if _month_end(view.now.date()) and sma is not None and view.last.c < sma:
            return Exit("month-end close below the 200-day average")
        return None


def test_long_hold_bot_trades_inside_a_yearly_window():
    bot = MonthlyTrend()
    warm = backtest.warmup_days(bot, 30)
    trades, _, problems = backtest.run_window(bot, ["TEST"], date(2017, 1, 1), date(2017, 12, 31), fetch=fetch,
                                              warmup_days=warm)
    assert not problems
    # the warm-up (back into 2016) filled the 200-day average, so the first month-end of the window can buy...
    assert [t.t_in[:10] for t in trades] == ["2017-01-31"]
    # ...and the bot rides the trend to the end of the window instead of showing 0 trades for the year
    assert trades[0].why_out == "end of test window" and trades[0].t_out[:10] == "2017-12-29"


def test_warmup_bars_are_history_only():
    bot = MonthlyTrend()
    bs = [b for b in BARS if date(2016, 1, 1) <= b.t.date() <= date(2017, 3, 31)]
    trace = []
    trades, _ = backtest.run_day(bot, "TEST", bs[-1].t.date(), bs, backtest.COSTS["swing"], trace=trace,
                                 close_at_end=True, entries_from=date(2017, 1, 1))
    assert [t.t_in[:10] for t in trades] == ["2017-01-31"]
    warm = [x for x in trace if x["t"].date() < date(2017, 1, 1)]
    assert warm and all(x["reason"].startswith("warm-up: history only") for x in warm)
    # without entries_from the same bars open a trade in the warm-up (late 2016) and hold it through the window
    held, _ = backtest.run_day(bot, "TEST", bs[-1].t.date(), bs, backtest.COSTS["swing"], close_at_end=True)
    assert held and held[0].t_in[:10] < "2017-01-01"


def test_yearly_report_and_luck_meter_see_one_trade_a_year():
    from botscope import report
    today = date(2018, 6, 1)
    full = report.full_report(MonthlyTrend, symbols=["TEST"], fetch=fetch, crashes=False, today=today, save=False)
    by_year = {r["year"]: r for r in full["by_year"]}
    assert [by_year[y]["trades"] for y in (2016, 2017, 2018)] == [1, 1, 1]
    lm = luck.luck_meter(MonthlyTrend, ["TEST"], years=True, fetch=fetch, save=False, today=today, twins=5, shuffles=1)
    assert lm["untested_trades"] == 3                     # was 0: every year's buy happened in the warm-up
