"""Example bot: daily crypto trend (BTC and ETH trade 24/7, every day of the week).

Shows the bot format working on crypto: Alpaca's crypto history needs no keys, days include weekends, and the
"crypto" cost profile in costs.json is much higher than for stocks (wider spreads). Textbook settings, never tuned
here, so every year is untested.

Honest report (2026-10-17, Alpaca crypto history (it starts in 2021), 2021 to 2026-10-16, all UNTESTED years, crypto
costs, $10k a trade): +26.6R over 115 trades (+0.23R a trade), range +3.7R to +52.7R (5th/95th of 1,000 resamples);
only +7.8R without its 3 best trades, so a few big trends carried most of it; costs took 10.6R; losing year 2022;
worst drop -11.4R. It made $20,221 against $8,152 for just holding SPY (beat SPY in 4 of 6 years) but less than
just holding BTC ($23,534; beat BTC in 2 of 6). Six years and 115 trades is a small sample: paper trade it before
trusting it.
"""
from botscope.bot import Bot, Entry, Exit, NoTrade


def _avg(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


class CryptoTrend(Bot):
    name = "Crypto trend"
    version = "1.0"
    description = "Buys BTC or ETH when the daily close crosses above its 50-day average; sells on a close below it."
    rules = [
        "Buy when the daily close crosses above the 50-day average close (the day before it was at or below).",
        "Stop: 3x the 20-day average daily range below the entry.",
        "Sell when a daily close is back below the 50-day average.",
        "Crypto trades every day, weekends included; costs use the crypto profile.",
    ]
    symbols = ["BTC/USD", "ETH/USD"]
    timeframe = "1Day"
    sides = "long"
    asset = "crypto"
    max_trades_per_day = 1
    flat_by_close = False
    lookback_days = 50
    params = {"avg_days": 50, "stop_ranges": 3.0, "range_days": 20}
    tuned_on = None
    status = "untested"
    notes = "Example of a 24/7 crypto bot. Long only, daily candles."

    def indicators(self, bars):
        closes, avg = [], []
        for b in bars:
            closes.append(b.c)
            avg.append(_avg(closes, self.p["avg_days"]))
        return {"50-day avg": avg}

    def entry(self, view):
        closes = [b.c for b in view.bars]
        n = self.p["avg_days"]
        now, before = _avg(closes, n), _avg(closes[:-1], n)
        if now is None or before is None:
            return NoTrade("not enough days of history yet")
        if not (closes[-2] <= before and closes[-1] > now):
            return NoTrade("no fresh cross above the 50-day average")
        k = self.p["range_days"]
        rng = sum(b.h - b.l for b in view.bars[-k:]) / k
        return Entry("long", closes[-1] - self.p["stop_ranges"] * rng, None, "crossed above the 50-day average")

    def exit(self, view, pos):
        closes = [b.c for b in view.bars]
        avg = _avg(closes, self.p["avg_days"])
        if avg is not None and view.bars[-1].t > pos.entry_time and closes[-1] < avg:
            return Exit("closed back below the 50-day average")
        return None
