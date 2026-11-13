"""Example bot: crypto 4-week time-series momentum, checked once a week (BTC and ETH, daily candles, long only).

Time-series momentum (is it up over the last few weeks?) is the best-documented pattern in crypto prices (Liu and
Tsyvinski, "Risks and Returns of Cryptocurrency", Review of Financial Studies 2021). Round-number settings picked by
hand (28 days = 4 weeks, one decision a week to keep the high crypto costs down); none were changed after testing.

Honest report (2026-11-12, Coinbase public daily candles (BOTSCOPE_CRYPTO_DATA=coinbase; Alpaca's crypto history only
starts in 2021), crypto costs, $10k a trade): 2016-2020 were used to choose which new example ideas to carry forward,
so they are marked TUNED (no setting was changed). 2021 to 2026-11-11 are UNTESTED.
- TUNED 2016-2020: +85.1R over 52 trades. Crypto's giant bull years: expect any trend rule to look great there.
- UNTESTED 2021-2026: +38.7R over 71 trades (+0.55R a trade), range +9R to +66R (5th/95th of 1,000 resamples),
  +31.3R with costs doubled, +17.1R without its 3 best trades; losing years 2022 and 2026; worst drop -6.5R; no
  trades in the 2022 bear market quarter. It made $37,398 against $24,715 for just holding BTC (beat BTC in 4 of 6
  years) and $8,102 for holding SPY.
- Robustness check: 10 of 10 (beat 50 of 50 random-entry twins on the luck meter). Held-out last year (2025-11-12 to
  2026-11-11): -0.8R over 12 trades, so it has gone flat lately. Most of the untested gain came from 2023 on.
Caveats: 71 trades is a small sample; crypto moves fast and gaps through stops; costs are guesses from few fills.
It is close in spirit to the crypto trend example (both follow the trend), with a weekly check instead of a daily one.
Paper trade it before trusting it.
"""
from datetime import timezone

from botscope.bot import Bot, Entry, Exit, NoTrade


class CryptoWeeklyMomentum(Bot):
    name = "Crypto weekly momentum"
    version = "1.0"
    description = "Every Sunday: holds BTC or ETH while it is up over the last 28 days, otherwise stays out."
    rules = [
        "Only decides on Sunday candles (crypto trades every day; the candle starts at midnight UTC).",
        "Buy when the close is above the close 28 days earlier (up over the last 4 weeks).",
        "Sell on a Sunday close that is below the close 28 days earlier.",
        "Stop: 3x the 20-day average daily range below the entry. Crypto cost profile.",
    ]
    symbols = ["BTC/USD", "ETH/USD"]
    timeframe = "1Day"
    sides = "long"
    asset = "crypto"
    max_trades_per_day = 1
    flat_by_close = False
    lookback_days = 28
    params = {"lookback": 28, "stop_ranges": 3.0, "range_days": 20}
    tuned_on = ("2016-01-01", "2020-12-31")
    status = "untested"
    notes = "Weekly decisions (Sunday UTC candle) keep trades few; crypto costs are high. BTC and ETH only."

    def _sunday(self, view):
        return view.last.t.astimezone(timezone.utc).weekday() == 6        # the candle that starts Sunday 00:00 UTC

    def entry(self, view):
        bars, n = view.bars, self.p["lookback"]
        if len(bars) < max(n, self.p["range_days"]) + 1:
            return NoTrade("not enough days of history yet")
        if not self._sunday(view):
            return NoTrade("only decides on Sundays")
        c, then = bars[-1].c, bars[-1 - n].c
        if c <= then:
            return NoTrade(f"down over 28 days ({then:.2f} -> {c:.2f})")
        k = self.p["range_days"]
        rng = sum(b.h - b.l for b in bars[-k:]) / k
        return Entry("long", c - self.p["stop_ranges"] * rng, None, f"up over 28 days ({then:.2f} -> {c:.2f})")

    def exit(self, view, pos):
        bars, n = view.bars, self.p["lookback"]
        if view.last.t <= pos.entry_time or not self._sunday(view) or len(bars) <= n:
            return None
        if bars[-1].c < bars[-1 - n].c:
            return Exit("Sunday close is below the close 28 days earlier")
        return None
