"""view.history: intraday bots that set history_days see the earlier sessions' bars (gap bots)."""
from datetime import date, datetime, timedelta

from botscope import backtest
from botscope.bot import BarData, Bot, Entry, NoTrade
from botscope.data import ET


def _session(day: date, open_px: float, close_px: float, n: int = 30):
    t0 = datetime(day.year, day.month, day.day, 9, 30, tzinfo=ET)
    step = (close_px - open_px) / (n - 1)
    return [BarData(t0 + timedelta(minutes=5 * i), open_px + step * i, open_px + step * i + .2,
                    open_px + step * i - .2, open_px + step * i, 1000) for i in range(n)]


DAYS = [date(2026, 9, 14), date(2026, 9, 15), date(2026, 9, 16)]
BARS = _session(DAYS[0], 100, 101) + _session(DAYS[1], 104, 106) + _session(DAYS[2], 106, 105)


def fake(sym, start, end, tf, feed):
    return [b for b in BARS if start <= b.t.date() <= end]


class Gap(Bot):
    name, timeframe, symbols, history_days = "Gap", "5Min", ["X"], 1
    asset, max_trades_per_day, flat_by_close = "stock_intraday", 1, True

    def indicators(self, bars):
        return {}

    def entry(self, view):
        if not view.history:
            return NoTrade("no yesterday")
        if len(view.bars) == 1 and view.last.o > view.history[-1].c * 1.02:
            return Entry("long", view.last.c - 1, view.last.c + 2, "gapped up 2%+")
        return NoTrade("no gap")

    def exit(self, view, pos):
        return None


def test_run_window_passes_yesterday_and_skips_history_only_days():
    seen = []

    class Spy(Gap):
        def entry(self, view):
            seen.append((view.now.date(), [b.t.date() for b in view.history][:1]))
            return super().entry(view)
    trades, _, problems = backtest.run_window(Spy(), ["X"], DAYS[1], DAYS[2], fetch=fake)
    assert [t.day for t in trades] == [str(DAYS[1])] and not problems         # 9/15 gapped up from 9/14's close
    assert {d for d, _ in seen} == {DAYS[1], DAYS[2]}                          # 9/14 was fetched only as history
    assert dict(seen)[DAYS[2]] == [DAYS[1]]                                    # history = the session just before


def test_run_day_downloads_history_itself_and_says_when_it_cannot(monkeypatch):
    from botscope import data
    monkeypatch.setattr(data, "bars", fake)
    day_bs = [b for b in BARS if b.t.date() == DAYS[1]]
    trades, problems = backtest.run_day(Gap(), "X", DAYS[1], day_bs, backtest.COSTS["stock_intraday"])
    assert len(trades) == 1 and not problems

    def broken(*a):
        raise ConnectionError("offline")
    monkeypatch.setattr(data, "bars", broken)
    trades, problems = backtest.run_day(Gap(), "X", DAYS[1], day_bs, backtest.COSTS["stock_intraday"])
    assert not trades and "view.history unavailable" in problems[0]
