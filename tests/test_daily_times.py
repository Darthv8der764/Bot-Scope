"""Daily candles have a day, not a clock time: nothing a daily bot says reads "00:00" (QA pass 2026-11-12)."""
from datetime import date, datetime, timedelta

from botscope import backtest
from botscope.bot import BarData, Bot, Entry, NoTrade
from botscope.data import ET


class Daily(Bot):
    name = "Daily test"
    symbols = ["TEST"]
    timeframe = "1Day"
    flat_by_close = False

    def entry(self, view):
        if len(view.bars) == 2:
            return Entry("long", view.last.c - 5, view.last.c + 50, "second day")
        return NoTrade("waiting")


def test_holding_reason_names_the_entry_day():
    t0 = datetime(2026, 6, 1, tzinfo=ET)
    bs = [BarData(t0 + timedelta(days=i), 100 + i * .1, 100.5 + i * .1, 99.5 + i * .1, 100 + i * .1, 1000) for i in range(6)]
    trace = []
    backtest.run_day(Daily(), "TEST", date(2026, 6, 1), bs, backtest.COSTS[Daily.asset], trace=trace, history=[])
    holding = [x["reason"] for x in trace if x["kind"] == "holding"]
    assert holding and all("since Jun 2:" in r for r in holding) and not any("00:00" in r for r in holding)


def test_claude_reads_a_daily_drawing_by_day(monkeypatch):
    from datetime import timezone
    from botscope import view
    monkeypatch.setattr(view, "build", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    t = lambda d: int(datetime(2026, 6, d, tzinfo=timezone.utc).timestamp())       # noqa: E731
    view.add_drawing("nr7_swing", "SPY", "2026-06-30", "line", [{"time": t(3), "price": 500}, {"time": t(9), "price": 510}])
    got = view.drawings_for_claude("nr7_swing")[-1]["line"]
    assert got["from"]["time"] == "2026-06-03" and got["to"]["time"] == "2026-06-09"


def test_why_not_here_on_a_daily_bot_reads_that_days_candle(monkeypatch):
    """Claude's why_not_here(time="15:59") on a daily bot always said "no bar at that time" (QA pass 2026-11-12)."""
    from datetime import time as dtime
    from botscope import view
    from botscope.view import chart_time
    t = chart_time(datetime.combine(date(2026, 10, 7), dtime(0), ET))
    st = {"bot": {"timeframe": "1Day"}, "day": "2026-10-30", "reasons": {str(t): {"kind": "entry", "reason": "LONG at 1"}}}
    monkeypatch.setattr(view, "build", lambda *a, **k: st)
    assert view.why_not_here("nr7_swing", "SPY", "2026-10-07", "15:59") == {"day": "2026-10-07", "kind": "entry", "reason": "LONG at 1"}
    assert view.why_not_here("nr7_swing", "SPY", "2026-10-10", "09:30")["kind"] == "none"
