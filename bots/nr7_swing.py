"""Example bot: NR7 breakout swing on daily candles (holds for days).

Inspired by the prototype's CEX setup (Crabel contraction -> expansion, from the 2026-10-01 research pack), which
traded the day after a narrow-range day intraday. This version trades it on daily candles to test the format on a
multi-day timeframe. Its settings were never tuned, so every year is untested.

Honest report (2026-10-15, Alpaca SIP daily data, 2016 to 2026-10-14, all UNTESTED years, swing costs, $10k a trade):
-77.8R over 963 trades (-0.08R a trade), range -155.6R to -3.8R (5th/95th of 1,000 resamples), so even the good end
of the range loses; costs took 67.7R, so the setup roughly breaks even before costs and loses after them; losing
money in 8 of 11 years; worst drop -103.2R. Kept as an example of a daily long-and-short bot, not as one to trade.
(That report came before the "without its 3 best trades" and "beat just holding SPY?" rows: run honest_report again
to fill them.)
"""
from botscope.bot import Bot, Entry, Exit, NoTrade


class NR7Swing(Bot):
    name = "NR7 swing"
    version = "1.0"
    description = "After the quietest day of the last 7, follows the breakout and holds up to 10 days."
    rules = [
        "NR7 day: a day whose high-low range is the smallest of the last 7 days.",
        "Next day: a close above the NR7 day's high buys; a close below its low shorts. Only that one day counts.",
        "Stop: the other side of the NR7 day. Target: 2x the risk.",
        "Sell after 10 trading days if neither the stop nor the target was hit.",
    ]
    symbols = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]
    timeframe = "1Day"
    sides = "both"
    asset = "swing"
    max_trades_per_day = 1
    flat_by_close = False
    params = {"nr_days": 7, "r_multiple": 2.0, "max_hold_days": 10}
    tuned_on = None
    status = "untested"
    notes = "Daily-timeframe example. Swing costs; overnight gaps can jump past the stop."

    def _is_nr(self, bars, i):
        n = self.p["nr_days"]
        if i < n - 1:
            return False
        return bars[i].h - bars[i].l <= min(b.h - b.l for b in bars[i - n + 1:i + 1])

    def indicators(self, bars):
        hi, lo = [], []
        for i in range(len(bars)):
            nr = i >= 1 and self._is_nr(bars, i - 1)            # levels of yesterday's NR7 day (no look-ahead)
            hi.append(bars[i - 1].h if nr else None); lo.append(bars[i - 1].l if nr else None)
        return {"nr7_high": hi, "nr7_low": lo}

    def entry(self, view):
        bars = view.bars
        if len(bars) < self.p["nr_days"] + 1:
            return NoTrade("not enough days of history yet")
        prev, c = bars[-2], view.last.c
        brk = None
        if not prev.l <= c <= prev.h:
            side = "long" if c > prev.h else "short"
            stop = prev.l if side == "long" else prev.h
            risk = abs(c - stop)
            target = c + self.p["r_multiple"] * risk if side == "long" else c - self.p["r_multiple"] * risk
            brk = Entry(side, stop, target, f"closed {'above' if side == 'long' else 'below'} the NR7 day "
                                            f"({prev.l:.2f}-{prev.h:.2f})")
        if not self._is_nr(bars, len(bars) - 2):
            n4 = bars[-2].h - bars[-2].l <= min(b.h - b.l for b in bars[-5:-1])     # near miss: quietest of 4
            return NoTrade(f"yesterday was not the quietest of the last {self.p['nr_days']} days",
                           almost=brk if n4 else None)
        if brk is None:
            return NoTrade(f"closed inside the NR7 day's range ({prev.l:.2f}-{prev.h:.2f})")
        return brk

    def exit(self, view, pos):
        held = sum(1 for b in view.bars if b.t > pos.entry_time)
        if held >= self.p["max_hold_days"]:
            return Exit(f"held {held} trading days")
        return None
