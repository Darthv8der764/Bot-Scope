"""Example bot: "Double 7s" dip buy on index ETFs (daily candles, long only).

A widely published short-term pullback rule (Larry Connors and Cesar Alvarez, "Short Term Trading Strategies That
Work", 2008): in an uptrend, buy a close at a 7-day low and sell at a 7-day high. Textbook settings, none changed here.
Tested on index ETFs only (SPY, QQQ, IWM, DIA), so no stock was picked knowing it did well.

Honest report (2026-11-12, Alpaca SIP daily bars cached on this computer, swing costs, $10k a trade): 2016-2020
were used to choose which of several new example ideas to carry forward, so those years are marked TUNED (no setting
was changed). 2021 to 2026-11-11 are UNTESTED.
- TUNED 2016-2020: +8.5R over 204 trades (+0.04R a trade), lost money in 3 of 5 years: a weak start.
- UNTESTED 2021-2026: +23.7R over 271 trades (+0.09R a trade), range +2R to +44R (5th/95th of 1,000 resamples),
  +15.1R with costs doubled, +19.9R without its 3 best trades; losing years 2022 and 2023; worst drop -9.5R.
  It made $7,237 against $8,102 for just holding SPY over the same days (beat SPY in 3 of 6 years).
- Robustness check: 10 of 10 (settings 20% smaller and bigger still made money; beat 48 of 50 random-entry twins on
  the luck meter). Held-out last year (2025-11-12 to 2026-11-11): +8.5R over 60 trades.
- Crashes: lost -5.1R in the Q4 2018 sell-off and -8.2R in the 2020 covid crash (the 200-day filter is slow to
  switch off), -1.0R in the 2022 bear market.
Caveats: the rule is famous because it looked good on older data, so "untested here" isn't "never fitted by anyone";
2021-2026 was mostly a rising market, which dip buying likes; it is close in spirit to the pullback swing example
(both buy dips above the 200-day average). Paper trade it before trusting it.
"""
from botscope.bot import Bot, Entry, Exit, NoTrade


class DoubleSevens(Bot):
    name = "Double 7s"
    version = "1.0"
    description = "In an uptrend, buys a close at a 7-day low and sells at the next 7-day high close."
    rules = [
        "Uptrend: the close is above the 200-day average close.",
        "Buy when the close is the lowest close of the last 7 days.",
        "Sell when a close is the highest close of the last 7 days.",
        "Stop: 3x the 10-day average daily range below the entry.",
    ]
    symbols = ["SPY", "QQQ", "IWM", "DIA"]
    timeframe = "1Day"
    sides = "long"
    asset = "swing"
    max_trades_per_day = 1
    flat_by_close = False
    lookback_days = 200
    params = {"trend_days": 200, "window_days": 7, "stop_ranges": 3.0, "range_days": 10}
    tuned_on = ("2016-01-01", "2020-12-31")
    status = "untested"
    notes = "Textbook settings (Connors/Alvarez). Index ETFs only. Swing costs; overnight gaps can jump past the stop."

    def entry(self, view):
        bars, t = view.bars, self.p["trend_days"]
        if len(bars) < t:
            return NoTrade("not enough days of history yet")
        closes = [b.c for b in bars]
        c, avg = closes[-1], sum(closes[-t:]) / t
        w = self.p["window_days"]
        k = self.p["range_days"]
        rng = sum(b.h - b.l for b in bars[-k:]) / k
        dip = Entry("long", c - self.p["stop_ranges"] * rng, None, f"close {c:.2f} is the lowest of 7 days") \
            if c <= min(closes[-w:]) else None
        if c <= avg:
            return NoTrade(f"below the 200-day average ({avg:.2f}): not an uptrend", almost=dip)
        return dip or NoTrade("close is not the lowest of the last 7 days")

    def exit(self, view, pos):
        closes = [b.c for b in view.bars]
        if view.last.t > pos.entry_time and closes[-1] >= max(closes[-self.p["window_days"]:]):
            return Exit("close is the highest of the last 7 days")
        return None
