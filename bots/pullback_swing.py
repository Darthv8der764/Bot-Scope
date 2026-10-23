"""Example bot: 2-day pullback swing on daily candles (buy a short dip in a long uptrend, long only).

The rules are the widely published RSI(2) pullback idea (Larry Connors) with its usual textbook settings, not
tuned here: no settings were picked on BotScope's data, so every year is untested.

Honest report (2026-10-17, Alpaca SIP daily data, 2016 to 2026-10-16, all UNTESTED years, swing costs, $10k a trade):
+44.15R over 435 trades (+0.10R a trade), range +24.2R to +61.8R (5th/95th of 1,000 resamples), +33.9R with costs
doubled, +40.2R without its 3 best trades; losing years 2018 and 2022; worst drop -8.95R. It made $27,913 against
$15,141 for just holding SPY over the same days (beat SPY in 8 of 11 years). 2016 has few trades: the data starts
that year, so the 200-day average only fills late in it.
(An earlier report the same night showed 130 trades: BotScope fetched only 30 days before each year, so the 200-day
average was missing for most of every year. Fixed with `lookback_days`.)
Same rules on index ETFs only (SPY, IWM, DIA; a direct backtest, not saved): +20.8R over 265 trades (+0.08R a trade),
so part of the result above comes from stocks picked knowing they did well.
Caveat: the idea itself is famous because it looked good on older data, so "untested here" isn't the same as never
fitted by anyone, and its stocks were picked knowing they did well (see docs/hindsight-in-the-symbol-list.md).
Paper trade it before trusting it.
"""
from botscope.bot import Bot, Entry, Exit, NoTrade


def _rsi(closes, n):
    """Wilder's RSI over n days, or None until there is enough history."""
    if len(closes) <= n:
        return None
    gains = losses = 0.0
    for a, b in zip(closes[:n], closes[1:n + 1]):
        gains += max(b - a, 0.0); losses += max(a - b, 0.0)
    g, l = gains / n, losses / n
    for a, b in zip(closes[n:], closes[n + 1:]):
        g = (g * (n - 1) + max(b - a, 0.0)) / n
        l = (l * (n - 1) + max(a - b, 0.0)) / n
    return 100.0 if l == 0 else 100 - 100 / (1 + g / l)


class PullbackSwing(Bot):
    name = "Pullback swing"
    version = "1.0"
    description = "Buys a sharp 2-day dip when the stock is above its 200-day average; sells on the bounce."
    rules = [
        "Uptrend: today's close is above the 200-day average close.",
        "Dip: the 2-day RSI closes under 10 (two or so sharp down days).",
        "Buy at that close. Stop: 3x the 10-day average daily range below the entry. No fixed target.",
        "Sell when a close is above the 5-day average close, or after 10 trading days.",
    ]
    symbols = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]
    timeframe = "1Day"
    sides = "long"
    asset = "swing"
    max_trades_per_day = 1
    flat_by_close = False
    lookback_days = 200
    params = {"trend_days": 200, "rsi_days": 2, "rsi_below": 10, "exit_avg_days": 5, "stop_ranges": 3.0,
              "range_days": 10, "max_hold_days": 10}
    tuned_on = None
    status = "untested"
    notes = "Textbook settings, never tuned on this data. Swing costs; overnight gaps can jump past the stop."

    def _avg(self, closes, n):
        return sum(closes[-n:]) / n if len(closes) >= n else None

    def indicators(self, bars):
        closes, sma, rsi = [], [], []
        for b in bars:
            closes.append(b.c)
            sma.append(self._avg(closes, self.p["trend_days"]))
            rsi.append(_rsi(closes[-60:], self.p["rsi_days"]))
        return {"avg_200": sma, "rsi_2": rsi}

    def entry(self, view):
        bars = view.bars
        if len(bars) < self.p["trend_days"]:
            return NoTrade("not enough days of history yet")
        closes = [b.c for b in bars]
        c, trend = closes[-1], self._avg(closes, self.p["trend_days"])
        rsi = _rsi(closes[-60:], self.p["rsi_days"])
        if c <= trend:
            return NoTrade(f"below the 200-day average ({trend:.2f}): not an uptrend")
        if rsi is None or rsi >= self.p["rsi_below"]:
            return NoTrade(f"no sharp dip (2-day RSI {rsi:.0f})" if rsi is not None else "no RSI yet")
        n = self.p["range_days"]
        rng = sum(b.h - b.l for b in bars[-n:]) / n
        return Entry("long", c - self.p["stop_ranges"] * rng, None,
                     f"2-day RSI {rsi:.0f} in an uptrend (close {c:.2f} > 200-day {trend:.2f})")

    def exit(self, view, pos):
        closes = [b.c for b in view.bars]
        avg = self._avg(closes, self.p["exit_avg_days"])
        if avg is not None and view.bars[-1].t > pos.entry_time and closes[-1] > avg:
            return Exit(f"bounced: close {closes[-1]:.2f} above the 5-day average {avg:.2f}")
        held = sum(1 for b in view.bars if b.t > pos.entry_time)
        if held >= self.p["max_hold_days"]:
            return Exit(f"held {held} trading days")
        return None
