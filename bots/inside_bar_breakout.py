"""Example bot: the textbook inside-bar breakout on 15-minute candles, longs only.

An inside bar is a candle that stays within the one before it (a pause). This is the generic chart-pattern version
found in most beginner trading books, with round-number settings picked by hand and never tuned, so every year is
untested. It shows a pattern bot on a 15-minute timeframe, not a bot to trade.
Honest report (2026-10-18, DEMO DATA: made-up prices, so these numbers say nothing about real markets; all UNTESTED
years 2016-2026, one month a year, intraday costs, $10k a trade): -158.8R over 313 trades (-0.51R a trade), range
-189R to -128R; costs took 1.9R, so it lost before costs too; lost money in all 11 years. Run honest_report
inside_bar_breakout with real data keys for a real report.
"""
from datetime import time

from botscope.bot import Bot, Entry, Exit, NoTrade


class InsideBarBreakout(Bot):
    name = "Inside bar breakout"
    version = "1.0"
    description = "Buys when price closes above a 'mother' candle after an inside candle, in an up day (15-minute)."
    rules = [
        "Inside candle: its high is below the candle before it (the mother) and its low is above the mother's low.",
        "Buy when a later candle closes above the mother's high, within 3 candles of the inside candle.",
        "Only between 10:00 and 14:00, and only when the price is above today's opening price.",
        "Stop: the inside candle's low. Target: 1.5x the risk.",
        "Sell at 15:30 if neither was hit. Longs only, one trade a day, closed by the end of the day.",
    ]
    symbols = ["SPY", "QQQ", "XLK", "XLF"]
    timeframe = "15Min"
    sides = "long"
    asset = "stock_intraday"
    max_trades_per_day = 1
    flat_by_close = True
    params = {"window": 3, "first_entry": "10:00", "last_entry": "14:00", "r_multiple": 1.5, "time_exit": "15:30"}
    tuned_on = None
    status = "untested"
    notes = "Generic textbook example. Longs only; the 'up day' filter is just price above today's open."

    def indicators(self, bars):
        day_open = bars[0].o if bars else None
        return {"day_open": [day_open] * len(bars)}

    def _signal(self, bars):
        """An Entry when the candle that just closed breaks a recent mother candle's high; else None."""
        last = bars[-1]
        for k in range(len(bars) - 2, max(0, len(bars) - 2 - self.p["window"]), -1):
            mother, inside = bars[k - 1], bars[k]
            if not (inside.h < mother.h and inside.l > mother.l):
                continue
            between = bars[k + 1:-1]
            if any(b.c > mother.h for b in between):
                return None                                  # it already broke out earlier
            if last.c > mother.h:
                risk = last.c - inside.l
                return Entry("long", inside.l, last.c + self.p["r_multiple"] * risk,
                             f"closed above the mother candle's high {mother.h:.2f} "
                             f"after an inside candle ({inside.l:.2f}-{inside.h:.2f})")
            return None
        return None

    def entry(self, view):
        bars = view.bars
        if view.trades_today >= self.max_trades_per_day:
            return NoTrade("one trade a day, already taken")
        if len(bars) < 3:
            return NoTrade("needs at least 3 candles today")
        sig = self._signal(bars)
        now = bars[-1].t.time()
        if not time.fromisoformat(self.p["first_entry"]) <= now <= time.fromisoformat(self.p["last_entry"]):
            return NoTrade(f"only trades {self.p['first_entry']}-{self.p['last_entry']}", almost=sig)
        day_open = view.ind["day_open"][-1]
        if bars[-1].c <= day_open:
            return NoTrade(f"price {bars[-1].c:.2f} is not above today's open {day_open:.2f}", almost=sig)
        return sig or NoTrade("no inside-candle breakout on this candle")

    def exit(self, view, pos):
        if view.last.t.time() >= time.fromisoformat(self.p["time_exit"]):
            return Exit(f"time exit at {self.p['time_exit']}")
        return None
