"""Example bot: the textbook first-hour breakout on 5-minute candles (the intraday example and the tutorial's bot).

A generic, widely taught day-trading idea with round-number settings picked by hand, not tuned on any data, so every
year is untested. It is here to show the bot format on an intraday timeframe, not as a bot to trade.
Honest report (2026-10-18, DEMO DATA: made-up prices, so these numbers say nothing about real markets; all UNTESTED
years 2016-2026, one month a year, intraday costs, $10k a trade): -329.9R over 916 trades (-0.36R a trade), range
-396R to -263R; costs took 18.3R, so it lost before costs too; lost money in 10 of 11 years. On made-up prices the
breakouts mostly reverse. Run honest_report first_hour_breakout with real data keys for a real report.
"""
from datetime import time

from botscope.bot import Bot, Entry, NoTrade

RANGE_END = time(10, 30)          # the first hour: 9:30 to 10:29


class FirstHourBreakout(Bot):
    name = "First hour breakout"
    version = "1.0"
    description = "Follows the first close outside the first trading hour's high-low range. One try a day."
    rules = [
        "The first hour's range: the highest high and lowest low from 9:30 to 10:29.",
        "Skip the day if that range is narrower than 0.4% of the price (too quiet to mean anything).",
        "From 10:30 to 13:30, the first candle that closes above the range buys; below it, sells short.",
        "Stop: a fixed 0.5% from the entry price. Target: 2x the risk.",
        "One trade a day at most. Everything is closed by the end of the day.",
    ]
    symbols = ["SPY", "QQQ", "IWM", "DIA"]
    timeframe = "5Min"
    sides = "both"
    asset = "stock_intraday"
    max_trades_per_day = 1
    flat_by_close = True
    params = {"min_width": 0.004, "last_entry": "13:30", "stop_pct": 0.005, "r_multiple": 2.0}
    tuned_on = None
    status = "untested"
    notes = "Generic textbook example. Fixed-percent stop, so the risk per trade is the same size every day."

    def indicators(self, bars):
        top = bottom = None
        tops, bottoms = [], []
        for b in bars:
            if b.t.time() < RANGE_END:                     # still inside the first hour: no level to draw yet
                top = b.h if top is None else max(top, b.h)
                bottom = b.l if bottom is None else min(bottom, b.l)
                tops.append(None)
                bottoms.append(None)
            else:
                tops.append(top)
                bottoms.append(bottom)
        return {"first_hour_high": tops, "first_hour_low": bottoms}

    def _breakout(self, view, top, bottom):
        """An Entry when the candle that just closed is the day's first close outside the range; else None."""
        closes = [b.c for b in view.bars if b.t.time() >= RANGE_END]
        outside = [c > top or c < bottom for c in closes]
        if not outside or not outside[-1] or any(outside[:-1]):
            return None
        price = closes[-1]
        up = price > top
        risk = price * self.p["stop_pct"]
        stop = price - risk if up else price + risk
        target = price + self.p["r_multiple"] * risk if up else price - self.p["r_multiple"] * risk
        where = "above the first hour's high" if up else "below the first hour's low"
        return Entry("long" if up else "short", stop, target,
                     f"first close {where} ({bottom:.2f}-{top:.2f}), stop {self.p['stop_pct']:.1%} away")

    def entry(self, view):
        now = view.last.t.time()
        if view.trades_today >= self.max_trades_per_day:
            return NoTrade("one trade a day, already taken")
        if now < RANGE_END:
            return NoTrade("still inside the first hour (the opening range is forming)")
        top, bottom = view.ind["first_hour_high"][-1], view.ind["first_hour_low"][-1]
        if top is None or bottom is None:
            return NoTrade("no first-hour candles today")
        setup = self._breakout(view, top, bottom)
        if now > time.fromisoformat(self.p["last_entry"]):
            return NoTrade(f"after {self.p['last_entry']}: no new trades", almost=setup)
        width = (top - bottom) / bottom
        if width < self.p["min_width"]:
            return NoTrade(f"first hour too quiet: range {width:.2%}, needs {self.p['min_width']:.1%}", almost=setup)
        if setup:
            return setup
        if any(b.c > top or b.c < bottom for b in view.bars if b.t.time() >= RANGE_END):
            return NoTrade("the day's first breakout already came and went")
        return NoTrade(f"still inside the first hour's range ({bottom:.2f}-{top:.2f})")
