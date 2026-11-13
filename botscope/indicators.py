"""Shared indicators any bot can use in its indicators(), entry() or exit().

Each function takes a list of finished bars (BarData, oldest first) and returns one value per bar, None where the
value is not defined yet (short history, no volume, nothing to anchor to). The no-peeking rule from bot.py holds for
every one of them: value i only ever uses bars[0..i], so adding later bars never changes an earlier value (the tests
check this for each indicator).

Intraday bots: view.bars is today only. For the ones that need earlier days (relative volume, a gap anchor), pass
view.history + view.bars and set history_days on the bot. Days are told apart by the bar's date (New York time for
stocks), so a missing candle or a half day is fine.

    from botscope import indicators as ind
    def indicators(self, bars):
        return {"vwap": ind.anchored_vwap(bars, "day")}

CATALOG is the plain-English list the Rule playground shows.
"""
from __future__ import annotations

import math
from bisect import bisect_right
from datetime import datetime, time, timedelta

CATALOG = [
    {"name": "rvol", "call": "rvol(bars, days=10)",
     "what": "Relative volume: today's volume so far vs the usual volume by this same time of day over the last 10 "
             "days (2.0 = twice as busy as normal for this time)."},
    {"name": "anchored_vwap", "call": "anchored_vwap(bars, anchor='day' | 'gap' | 'swing_high' | 'swing_low' | bar)",
     "what": "The average price paid (volume-weighted) since a chosen moment: today's open, the last gap, the last "
             "swing high or low, or a bar you pick."},
    {"name": "vwap_bands", "call": "vwap_bands(bars, anchor='day', k=2)",
     "what": "Anchored VWAP with bands 2 standard deviations above and below: how stretched price is from the "
             "average price paid since the anchor."},
    {"name": "adx", "call": "adx(bars, n=14)",
     "what": "Trend strength from 0 to 100 (ADX), with +DI and -DI saying which way: over 25 is a strong trend, "
             "under 20 is weak, whichever DI is higher is winning."},
    {"name": "chop", "call": "chop(bars, n=14)",
     "what": "Choppiness Index from 0 to 100: low (under about 38) means price is trending, high (over about 62) "
             "means it is going sideways and chopping around."},
    {"name": "opening_range", "call": "opening_range(bars, minutes=30)",
     "what": "The high and low of the first minutes of each day (9:30 to 10:00 by default), shown once that "
             "window has finished."},
    {"name": "atr", "call": "atr(bars, n=14)",
     "what": "Average true range: how far price usually moves in one candle, gaps included. Handy for stops that "
             "fit how wild the stock is right now."},
    {"name": "keltner", "call": "keltner(bars, n=20, mult=2, atr_n=10)",
     "what": "Keltner channels: a moving average with bands 2 ATRs above and below. Closing outside a band is an "
             "unusually strong push."},
    {"name": "supertrend", "call": "supertrend(bars, n=10, mult=3)",
     "what": "A trailing line 3 ATRs from price that flips sides when price closes through it: under price = up "
             "trend, over price = down trend."},
    {"name": "obv", "call": "obv(bars)",
     "what": "On-balance volume: adds volume on up closes and subtracts it on down closes. Rising OBV means buyers "
             "are doing more of the trading."},
    {"name": "ad_line", "call": "ad_line(bars)",
     "what": "Accumulation/distribution: adds more volume the closer each candle closes to its high. Rising = "
             "candles keep closing near their highs."},
    {"name": "zscore", "call": "zscore(bars, n=20)",
     "what": "How unusual the close is next to the last 20: 0 is average, +2 or -2 is a stretch of about two "
             "normal wiggles."},
    {"name": "gaps", "call": "gaps(bars)",
     "what": "How far each day opened from the day before's close (+0.02 = 2% higher), and whether price has "
             "come back to fill that gap yet."},
    {"name": "rsi", "call": "rsi(bars, n=14)",
     "what": "RSI from 0 to 100: compares recent up closes with down closes. Under 30 = sold hard lately, over 70 = "
             "bought hard lately (not a signal by itself)."},
    {"name": "bollinger", "call": "bollinger(bars, n=20, k=2)",
     "what": "Bollinger bands: a 20-candle average with bands 2 standard deviations away, plus %B (where the close "
             "sits) and width (a small width = a quiet squeeze)."},
    {"name": "macd", "call": "macd(bars, fast=12, slow=26, signal=9)",
     "what": "MACD: the fast average minus the slow one, a signal line and a histogram. Above 0 = the short-term "
             "trend is above the long-term one."},
    {"name": "donchian", "call": "donchian(bars, n=20)",
     "what": "The highest high and lowest low of the 20 candles before this one. A close above the high is a "
             "fresh 20-candle breakout."},
    {"name": "stochastic", "call": "stochastic(bars, n=14, smooth_k=3, d=3)",
     "what": "Where the close sits in the last 14 candles' range, 0 to 100 (100 = at the top), smoothed, with a "
             "slower signal line."},
    {"name": "prior_day", "call": "prior_day(bars)",
     "what": "Yesterday's high, low and close, shown all day today: levels many traders watch for a bounce or a "
             "break."},
    {"name": "pivots", "call": "pivots(bars)",
     "what": "Classic floor pivots worked out from yesterday's high, low and close: a middle pivot with two "
             "levels above (R1, R2) and two below (S1, S2)."},
    {"name": "roc", "call": "roc(bars, n=10)",
     "what": "Rate of change: how far the close moved over the last 10 candles (0.05 = up 5%)."},
    {"name": "williams_r", "call": "williams_r(bars, n=14)",
     "what": "Williams %R: where the close sits in the last 14 candles' range, 0 at the top down to -100 at the "
             "bottom."},
    {"name": "cci", "call": "cci(bars, n=20)",
     "what": "CCI: how far the typical price is from its 20-candle average, in units of its usual distance. "
             "Beyond +100 or -100 is an unusually strong move."},
    {"name": "mfi", "call": "mfi(bars, n=14)",
     "what": "Money Flow Index: like RSI but bigger-volume candles count more. Over 80 = heavy buying lately, "
             "under 20 = heavy selling."},
    {"name": "heikin_ashi", "call": "heikin_ashi(bars)",
     "what": "Heikin-Ashi candles: averaged candles that smooth the noise. Several green ones in a row with no "
             "lower wick = a steady up move."},
    {"name": "swing_levels", "call": "swing_levels(bars, strength=3)",
     "what": "The price of the last confirmed swing high and swing low. A common place for a stop: under the last "
             "swing low when buying."},
    {"name": "narrow_range", "call": "narrow_range(bars, n=7)",
     "what": "Flags quiet candles: the smallest range of the last 7 (NR7), or a candle inside the one before. "
             "Quiet often comes before a bigger move."},
    {"name": "hist_volatility", "call": "hist_volatility(bars, n=20, per_year=252)",
     "what": "Historical volatility: how much the price has been swinging, as a yearly number (0.20 = about 20% a "
             "year). Set per_year to candles per year."},
    {"name": "ema", "call": "ema(values, n=20)",
     "what": "Exponential moving average of any list of numbers (usually closes): an average that leans on the "
             "newest values, so it turns faster than a simple average."},
    {"name": "sma", "call": "sma(values, n=20)",
     "what": "Simple moving average: the plain average of the last 20 values."},
]

# Group and a one-line example for each (the examples run in the tests against a made-up view, so they stay right).
# Intraday examples that need earlier days use view.history + view.bars (set history_days on the bot).
KINDS = ["Volume", "Price levels", "Trend", "Momentum", "Volatility and stretch"]
_MORE = {
    "rvol": ("Volume", "ind.rvol(view.history + view.bars)[-1] > 2      # twice the usual volume for this time"),
    "obv": ("Volume", "ind.obv(view.bars)[-1] > ind.obv(view.bars)[-10]      # more volume on up closes lately"),
    "ad_line": ("Volume", "ind.ad_line(view.bars)[-1] > ind.ad_line(view.bars)[-10]"),
    "mfi": ("Volume", "ind.mfi(view.bars)[-1] < 20      # heavy selling lately"),
    "anchored_vwap": ("Price levels", "view.last.c > ind.anchored_vwap(view.bars, 'day')[-1]      # above today's VWAP"),
    "vwap_bands": ("Price levels", "view.last.c < ind.vwap_bands(view.bars)['vwap_lower'][-1]      # stretched below"),
    "opening_range": ("Price levels", "view.last.c > ind.opening_range(view.bars)['or_high'][-1]      # broke out up"),
    "prior_day": ("Price levels", "view.last.c > ind.prior_day(view.history + view.bars)['pdh'][-1]"),
    "pivots": ("Price levels", "ind.pivots(view.history + view.bars)['r1'][-1]      # first level above the pivot"),
    "donchian": ("Price levels", "view.last.c > ind.donchian(view.bars, 20)['dc_high'][-1]      # 20-candle high"),
    "gaps": ("Price levels", "ind.gaps(view.history + view.bars)['gap_pct'][-1] > 0.02      # opened 2%+ higher"),
    "adx": ("Trend", "ind.adx(view.bars)['adx'][-1] < 20      # no real trend: skip"),
    "chop": ("Trend", "ind.chop(view.bars)[-1] > 62      # choppy: skip breakouts"),
    "supertrend": ("Trend", "ind.supertrend(view.bars)['direction'][-1] == 1      # up trend"),
    "macd": ("Trend", "ind.macd(view.bars)['macd_hist'][-1] > 0"),
    "ema": ("Trend", "view.last.c > ind.ema([b.c for b in view.bars], 20)[-1]"),
    "sma": ("Trend", "view.last.c > ind.sma([b.c for b in view.bars], 50)[-1]"),
    "rsi": ("Momentum", "ind.rsi(view.bars, 2)[-1] < 10      # a sharp short dip"),
    "stochastic": ("Momentum", "ind.stochastic(view.bars)['stoch_k'][-1] > 80"),
    "williams_r": ("Momentum", "ind.williams_r(view.bars)[-1] < -80      # near the bottom of the range"),
    "cci": ("Momentum", "ind.cci(view.bars)[-1] > 100"),
    "roc": ("Momentum", "ind.roc(view.bars, 10)[-1] > 0.05      # up 5%+ in 10 candles"),
    "atr": ("Volatility and stretch", "view.last.c - 1.5 * ind.atr(view.bars)[-1]      # a stop 1.5 ATRs away"),
    "keltner": ("Volatility and stretch", "view.last.c > ind.keltner(view.bars)['kc_upper'][-1]"),
    "bollinger": ("Volatility and stretch", "ind.bollinger(view.bars)['bb_width'][-1] < 0.02      # a tight squeeze"),
    "heikin_ashi": ("Trend", "ind.heikin_ashi(view.bars)['ha_close'][-1] > ind.heikin_ashi(view.bars)['ha_open'][-1]"),
    "swing_levels": ("Price levels", "ind.swing_levels(view.bars)['swing_low'][-1]      # stop under it for a long"),
    "narrow_range": ("Volatility and stretch", "ind.narrow_range(view.bars, 7)['nr'][-1] is True      # an NR7 candle"),
    "hist_volatility": ("Volatility and stretch", "ind.hist_volatility(view.bars, 20, 252 * 390)[-1] > 0.4"),
    "zscore": ("Volatility and stretch", "ind.zscore(view.bars)[-1] < -2      # unusually far below average"),
}
for _row in CATALOG:
    _row["kind"], _row["example"] = _MORE[_row["name"]]
CATALOG.sort(key=lambda r: KINDS.index(r["kind"]))     # stable: keeps the order inside each group


def _day(b):
    return b.t.date()


def _day_starts(bars) -> list[int]:
    """Index of the first bar of each day (a day = one calendar date in the bars' own time zone)."""
    return [i for i, b in enumerate(bars) if i == 0 or _day(b) != _day(bars[i - 1])]


def _true_range(bars) -> list[float]:
    """High-low, stretched to the previous close when the bar gapped past it. The very first bar has no previous
    close, so it is just high-low."""
    return [b.h - b.l if i == 0 else max(b.h, bars[i - 1].c) - min(b.l, bars[i - 1].c) for i, b in enumerate(bars)]


# ---- relative volume by time of day ----

def rvol(bars, days: int = 10, min_days: int | None = None) -> list[float | None]:
    """Today's volume so far (up to and including this bar) divided by the average volume earlier days had traded
    by the same time of day, over the last `days` days before today. Comparing by time of day matters: the first
    half hour is always busy, so a plain daily average makes every morning look 'high volume'.

    None while fewer than `min_days` earlier days are in the bars (default: half of `days`, at least 1), or when
    those days traded nothing by this time. A day missing a candle simply counts the candles it has by then."""
    need = max(1, days // 2) if min_days is None else max(1, min_days)
    starts = _day_starts(bars) + [len(bars)]
    # per day: times of day (sorted, as in the bars) and running volume, for a fast "volume by this time" lookup
    times, cums = [], []
    for a, b in zip(starts, starts[1:]):
        ts, cs, run = [], [], 0.0
        for x in bars[a:b]:
            run += x.v
            ts.append(x.t.time()); cs.append(run)
        times.append(ts); cums.append(cs)
    out: list[float | None] = []
    for d, (a, b) in enumerate(zip(starts, starts[1:])):
        earlier = list(range(max(0, d - days), d))
        for k in range(b - a):
            if len(earlier) < need:
                out.append(None); continue
            t = times[d][k]
            usual = 0.0
            for e in earlier:
                j = bisect_right(times[e], t)
                usual += cums[e][j - 1] if j else 0.0
            usual /= len(earlier)
            out.append(cums[d][k] / usual if usual > 0 else None)
    return out


# ---- anchored VWAP ----

def _swings(bars, strength: int, high: bool) -> list[int | None]:
    """For each bar i: the newest swing high (or low) already CONFIRMED by bar i, else None. A swing high is a bar
    whose high is above the `strength` bars on each side; it can only be known `strength` bars later, so bar i
    never uses a pivot that needs bars after i."""
    out, last = [], None
    for i in range(len(bars)):
        p = i - strength
        if p - strength >= 0:
            v = bars[p].h if high else bars[p].l
            around = [x.h if high else x.l for x in bars[p - strength:p] + bars[p + 1:i + 1]]
            if all(v > w for w in around) if high else all(v < w for w in around):
                last = p
        out.append(last)
    return out


def anchors(bars, anchor="day", min_gap: float = 0.005, strength: int = 3) -> list[int | None]:
    """Which bar each bar's anchored VWAP starts from (an index <= i, so it never looks ahead), or None.
    anchor: 'day' (the day's first bar), 'gap' (the newest day that opened at least min_gap, 0.5%, away from the
    previous day's close), 'swing_high' / 'swing_low' (the newest confirmed swing, `strength` bars each side),
    or a bar index (an int) or a bar start time (a datetime)."""
    n = len(bars)
    if isinstance(anchor, datetime):
        hit = [i for i, b in enumerate(bars) if b.t >= anchor]
        anchor = hit[0] if hit else n
    if isinstance(anchor, int) and not isinstance(anchor, bool):
        return [anchor if 0 <= anchor <= i else None for i in range(n)]
    if anchor == "day":
        out, s = [], 0
        for i in range(n):
            if i == 0 or _day(bars[i]) != _day(bars[i - 1]):
                s = i
            out.append(s)
        return out
    if anchor == "gap":
        out, g = [], None
        for i in range(n):
            if i > 0 and _day(bars[i]) != _day(bars[i - 1]):
                prev = bars[i - 1].c
                if prev and abs(bars[i].o - prev) / prev >= min_gap:
                    g = i
            out.append(g)
        return out
    if anchor in ("swing_high", "swing_low"):
        return _swings(bars, strength, anchor == "swing_high")
    raise ValueError(f"unknown anchor {anchor!r}: use 'day', 'gap', 'swing_high', 'swing_low', a bar index or a time")


def anchored_vwap(bars, anchor="day", min_gap: float = 0.005, strength: int = 3) -> list[float | None]:
    """Volume-weighted average of the typical price (high+low+close)/3 from the anchor bar through this bar.
    None before there is an anchor, or while nothing has traded since it. See anchors() for the anchor choices.
    anchored_vwap(bars, 'day') is the usual intraday VWAP."""
    pv, vol = [0.0], [0.0]
    for b in bars:
        pv.append(pv[-1] + (b.h + b.l + b.c) / 3 * b.v)
        vol.append(vol[-1] + b.v)
    out = []
    for i, a in enumerate(anchors(bars, anchor, min_gap, strength)):
        v = None if a is None else vol[i + 1] - vol[a]
        out.append((pv[i + 1] - pv[a]) / v if v and v > 0 else None)
    return out


def vwap_bands(bars, anchor="day", k: float = 2.0, min_gap: float = 0.005, strength: int = 3) -> dict[str, list]:
    """Anchored VWAP with bands k volume-weighted standard deviations above and below: how far price has typically
    traded from the VWAP since the anchor. Same anchors and None rules as anchored_vwap()."""
    pv, pv2, vol = [0.0], [0.0], [0.0]
    for b in bars:
        tp = (b.h + b.l + b.c) / 3
        pv.append(pv[-1] + tp * b.v); pv2.append(pv2[-1] + tp * tp * b.v); vol.append(vol[-1] + b.v)
    mid: list[float | None] = []
    up: list[float | None] = []
    lo: list[float | None] = []
    for i, a in enumerate(anchors(bars, anchor, min_gap, strength)):
        v = None if a is None else vol[i + 1] - vol[a]
        if not v or v <= 0:
            mid.append(None); up.append(None); lo.append(None); continue
        m = (pv[i + 1] - pv[a]) / v
        sd = math.sqrt(max(0.0, (pv2[i + 1] - pv2[a]) / v - m * m))
        mid.append(m); up.append(m + k * sd); lo.append(m - k * sd)
    return {"vwap": mid, "vwap_upper": up, "vwap_lower": lo}


# ---- ADX / DMI ----

def adx(bars, n: int = 14) -> dict[str, list[float | None]]:
    """Wilder's ADX with +DI and -DI (J. Welles Wilder, 1978).
    +DM = today's high minus yesterday's high, -DM = yesterday's low minus today's low; only the bigger one counts,
    and only if it is above 0. True range includes gaps. All three are smoothed Wilder's way (first value = the sum
    of the first n, then prev - prev/n + new). +DI / -DI = 100 x smoothed DM / smoothed TR; DX = 100 x |+DI - -DI| /
    (+DI + -DI); ADX = the average of the first n DX values, then smoothed (prev x (n-1) + DX) / n.
    +DI / -DI start at bar n, ADX at bar 2n-1 (0-based): before that they are None."""
    m = len(bars)
    pdi: list[float | None] = [None] * m
    mdi: list[float | None] = [None] * m
    ax: list[float | None] = [None] * m
    if n < 1:
        raise ValueError("n must be at least 1")
    tr = _true_range(bars)
    str_ = spd = smd = 0.0
    dxs: list[float] = []
    a = None
    for i in range(1, m):
        up, dn = bars[i].h - bars[i - 1].h, bars[i - 1].l - bars[i].l
        pdm = up if up > dn and up > 0 else 0.0
        mdm = dn if dn > up and dn > 0 else 0.0
        if i <= n:                                   # building the first sums (bars 1..n)
            str_ += tr[i]; spd += pdm; smd += mdm
            if i < n:
                continue
        else:
            str_ += tr[i] - str_ / n; spd += pdm - spd / n; smd += mdm - smd / n
        p = 100 * spd / str_ if str_ > 0 else 0.0
        q = 100 * smd / str_ if str_ > 0 else 0.0
        pdi[i], mdi[i] = p, q
        dxs.append(100 * abs(p - q) / (p + q) if p + q > 0 else 0.0)
        if len(dxs) == n:
            a = sum(dxs) / n
        elif len(dxs) > n:
            a = (a * (n - 1) + dxs[-1]) / n
        ax[i] = a
    return {"adx": ax, "plus_di": pdi, "minus_di": mdi}


# ---- Choppiness Index ----

def chop(bars, n: int = 14) -> list[float | None]:
    """Choppiness Index (E. W. Dreiss): 100 x log10(sum of the last n true ranges / (highest high - lowest low of
    those n bars)) / log10(n). 0 = every bar moved price further in one direction (a clean trend), 100 = all the
    bars' movement happened inside the same box (pure chop). None for the first n-1 bars, or a flat window."""
    if n < 2:
        raise ValueError("n must be at least 2")
    tr = _true_range(bars)
    out: list[float | None] = []
    for i in range(len(bars)):
        if i < n - 1:
            out.append(None); continue
        w = bars[i - n + 1:i + 1]
        box = max(b.h for b in w) - min(b.l for b in w)
        total = sum(tr[i - n + 1:i + 1])
        out.append(100 * math.log10(total / box) / math.log10(n) if box > 0 and total > 0 else None)
    return out


# ---- opening range ----

def opening_range(bars, minutes: int = 30, start: time = time(9, 30)) -> dict[str, list[float | None]]:
    """Each day's opening range: the highest high and lowest low of the bars that START inside [start, start +
    minutes). The levels appear from the first bar after that window (while it is still forming there is no level
    yet, which is also what keeps it from peeking), and stay for the rest of the day. A day with no bars inside the
    window has no levels. Bars must be at least as fine as `minutes` for the window to mean anything."""
    end = (datetime.combine(datetime.min, start) + timedelta(minutes=minutes)).time()
    hi: list[float | None] = []
    lo: list[float | None] = []
    day = top = bottom = None
    for b in bars:
        if _day(b) != day:
            day, top, bottom = _day(b), None, None
        t = b.t.time()
        if start <= t < end:
            top = b.h if top is None else max(top, b.h)
            bottom = b.l if bottom is None else min(bottom, b.l)
            hi.append(None); lo.append(None)
        elif t >= end:
            hi.append(top); lo.append(bottom)
        else:                                        # before the open (premarket bars): no level
            hi.append(None); lo.append(None)
    return {"or_high": hi, "or_low": lo}


# ---- building blocks: moving averages and ATR ----

def sma(values, n: int) -> list[float | None]:
    """Simple average of the last n values (None until there are n, or while any of them is None)."""
    out: list[float | None] = []
    for i in range(len(values)):
        w = values[max(0, i - n + 1):i + 1]
        out.append(sum(w) / n if len(w) == n and None not in w else None)
    return out


def ema(values, n: int, alpha: float | None = None) -> list[float | None]:
    """Exponential average, started from the simple average of the first n values (the usual charting convention):
    then prev + alpha x (value - prev), alpha = 2/(n+1). A None value gives None there and is skipped."""
    a = 2 / (n + 1) if alpha is None else alpha
    out: list[float | None] = []
    seen: list[float] = []
    prev = None
    for v in values:
        if v is None:
            out.append(None); continue
        if prev is None:
            seen.append(v)
            if len(seen) == n:
                prev = sum(seen) / n
        else:
            prev += a * (v - prev)
        out.append(prev)
    return out


def atr(bars, n: int = 14) -> list[float | None]:
    """Average true range, Wilder's way: the first value (bar n-1) is the plain average of the first n true ranges,
    then (prev x (n-1) + true range) / n. True range includes overnight gaps."""
    return ema(_true_range(bars), n, alpha=1 / n)


# ---- Keltner channels and Supertrend ----

def keltner(bars, n: int = 20, mult: float = 2.0, atr_n: int = 10) -> dict[str, list[float | None]]:
    """Keltner channels: a middle line (n-bar exponential average of the close) with bands mult x ATR(atr_n) above
    and below. Price riding the upper band = strong up move; a close back inside = the push is fading."""
    mid = ema([b.c for b in bars], n)
    a = atr(bars, atr_n)
    up = [m + mult * x if m is not None and x is not None else None for m, x in zip(mid, a)]
    lo = [m - mult * x if m is not None and x is not None else None for m, x in zip(mid, a)]
    return {"kc_mid": [m if u is not None else None for m, u in zip(mid, up)], "kc_upper": up, "kc_lower": lo}


def supertrend(bars, n: int = 10, mult: float = 3.0) -> dict[str, list]:
    """Supertrend: a trailing line mult x ATR(n) away from the candle's middle (high+low)/2. In an up trend the line
    sits under price and only moves up; a close under it flips the trend down (the line jumps above price and then
    only moves down). direction: 1 = up, -1 = down, None until the ATR exists."""
    a = atr(bars, n)
    line: list[float | None] = []
    dirn: list[int | None] = []
    up = dn = None
    trend = 1
    for i, b in enumerate(bars):
        if a[i] is None:
            line.append(None); dirn.append(None); continue
        mid = (b.h + b.l) / 2
        u, d = mid - mult * a[i], mid + mult * a[i]
        if up is not None:
            prev_c = bars[i - 1].c
            u = max(u, up) if prev_c > up else u
            d = min(d, dn) if prev_c < dn else d
            if trend == -1 and b.c > dn:
                trend = 1
            elif trend == 1 and b.c < up:
                trend = -1
        up, dn = u, d
        line.append(up if trend == 1 else dn)
        dirn.append(trend)
    return {"supertrend": line, "direction": dirn}


# ---- volume flow ----

def obv(bars) -> list[float]:
    """On-balance volume: a running total that adds the candle's volume when it closes higher than the one before,
    and subtracts it when it closes lower. Starts at 0. Its slope matters, not its level."""
    out, run = [], 0.0
    for i, b in enumerate(bars):
        if i:
            run += b.v if b.c > bars[i - 1].c else -b.v if b.c < bars[i - 1].c else 0.0
        out.append(run)
    return out


def ad_line(bars) -> list[float]:
    """Accumulation/distribution line: each candle adds its volume times where it closed in its own range (+1 at
    the high, -1 at the low, 0 in the middle or for a candle with no range). Rising = closes near the highs."""
    out, run = [], 0.0
    for b in bars:
        rng = b.h - b.l
        run += ((b.c - b.l) - (b.h - b.c)) / rng * b.v if rng > 0 else 0.0
        out.append(run)
    return out


# ---- statistics ----

def zscore(bars, n: int = 20) -> list[float | None]:
    """How unusual this close is next to the last n closes (this one included): (close - their average) / their
    standard deviation (population, like Bollinger bands). +2 = about two 'normal wiggles' above average.
    None until n closes, or when all n are the same."""
    closes = [b.c for b in bars]
    out: list[float | None] = []
    for i in range(len(closes)):
        if i < n - 1:
            out.append(None); continue
        w = closes[i - n + 1:i + 1]
        m = sum(w) / n
        sd = math.sqrt(sum((x - m) ** 2 for x in w) / n)
        out.append((closes[i] - m) / sd if sd > 1e-12 * max(1.0, abs(m)) else None)
    return out


# ---- gaps ----

def gaps(bars) -> dict[str, list]:
    """For every bar: how far the day opened from the previous day's last close (gap_pct, +0.02 = opened 2%
    higher; None on the first day in the bars), and whether price has traded back to that close since the open,
    up to and including this bar (gap_filled). Works for intraday bars and for daily bars (one bar = one day)."""
    pct: list[float | None] = []
    filled: list[bool | None] = []
    g = prev = None
    done = False
    for i, b in enumerate(bars):
        if i == 0 or _day(b) != _day(bars[i - 1]):
            prev = bars[i - 1].c if i else None
            g = (b.o - prev) / prev if prev else None
            done = False
        if g is None:
            pct.append(None); filled.append(None); continue
        if not done:
            done = b.l <= prev if g > 0 else b.h >= prev if g < 0 else True
        pct.append(g); filled.append(done)
    return {"gap_pct": pct, "gap_filled": filled}


# ---- momentum and bands ----

def rsi(bars, n: int = 14) -> list[float | None]:
    """Wilder's RSI on closes: average up-move vs average down-move over n candles, scaled 0-100. The first value
    (bar n) uses plain averages of the first n moves, then Wilder smoothing (prev x (n-1) + new) / n.
    Only up-moves -> 100, only down-moves -> 0, no movement at all -> 50."""
    up = [None] + [max(b.c - a.c, 0.0) for a, b in zip(bars, bars[1:])] if bars else []
    dn = [None] + [max(a.c - b.c, 0.0) for a, b in zip(bars, bars[1:])] if bars else []
    g, lo = ema(up, n, 1 / n), ema(dn, n, 1 / n)
    out: list[float | None] = []
    for x, y in zip(g, lo):
        if x is None or y is None:
            out.append(None)
        elif x == 0 and y == 0:
            out.append(50.0)
        else:
            out.append(100.0 if y == 0 else 100 - 100 / (1 + x / y))
    return out


def bollinger(bars, n: int = 20, k: float = 2.0) -> dict[str, list[float | None]]:
    """Bollinger bands: the n-candle average close with bands k standard deviations (population) above and below.
    pct_b says where the close sits: 0 = on the lower band, 1 = on the upper band, above 1 = outside it.
    width = (upper - lower) / middle: low width = a quiet squeeze, often before a bigger move."""
    closes = [b.c for b in bars]
    mid = sma(closes, n)
    up: list[float | None] = []
    lo: list[float | None] = []
    pb: list[float | None] = []
    wd: list[float | None] = []
    for i, m in enumerate(mid):
        if m is None:
            up.append(None); lo.append(None); pb.append(None); wd.append(None); continue
        w = closes[i - n + 1:i + 1]
        sd = math.sqrt(sum((x - m) ** 2 for x in w) / n)
        u, d = m + k * sd, m - k * sd
        up.append(u); lo.append(d)
        pb.append((closes[i] - d) / (u - d) if u > d else None)
        wd.append((u - d) / m if m else None)
    return {"bb_mid": mid, "bb_upper": up, "bb_lower": lo, "bb_pct_b": pb, "bb_width": wd}


def macd(bars, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, list[float | None]]:
    """MACD: the fast exponential average of the close minus the slow one (positive = short-term above long-term),
    a signal line (exponential average of the MACD) and the histogram (MACD - signal)."""
    closes = [b.c for b in bars]
    f, s = ema(closes, fast), ema(closes, slow)
    line = [a - b if a is not None and b is not None else None for a, b in zip(f, s)]
    sig = ema(line, signal)
    sig = [x if m is not None else None for x, m in zip(sig, line)]
    hist = [m - x if m is not None and x is not None else None for m, x in zip(line, sig)]
    return {"macd": line, "macd_signal": sig, "macd_hist": hist}


def donchian(bars, n: int = 20, include_current: bool = False) -> dict[str, list[float | None]]:
    """Donchian channel: the highest high and lowest low of the last n candles. By default the candle that just
    closed is NOT included, so 'close > dc_high' means a fresh n-candle breakout (with it included that could
    never happen). None until there are n earlier candles."""
    hi: list[float | None] = []
    lo: list[float | None] = []
    for i in range(len(bars)):
        end = i + 1 if include_current else i
        w = bars[end - n:end] if end - n >= 0 else []
        hi.append(max(b.h for b in w) if w else None)
        lo.append(min(b.l for b in w) if w else None)
    return {"dc_high": hi, "dc_low": lo}


def stochastic(bars, n: int = 14, smooth_k: int = 3, d: int = 3) -> dict[str, list[float | None]]:
    """Stochastic oscillator: where the close sits in the last n candles' high-low range, 0-100 (100 = at the top).
    stoch_k is that, averaged over smooth_k candles; stoch_d is stoch_k averaged over d candles. None while the
    range is flat or history is short."""
    raw: list[float | None] = []
    for i, b in enumerate(bars):
        if i < n - 1:
            raw.append(None); continue
        w = bars[i - n + 1:i + 1]
        hh, ll = max(x.h for x in w), min(x.l for x in w)
        raw.append(100 * (b.c - ll) / (hh - ll) if hh > ll else None)
    k = sma(raw, smooth_k)
    return {"stoch_k": k, "stoch_d": sma(k, d)}


# ---- yesterday's levels and floor pivots ----

def _prev_day_hlc(bars) -> list[tuple[float, float, float] | None]:
    """For every bar: (high, low, close) of the previous day in the bars, or None on the first day."""
    out: list[tuple[float, float, float] | None] = []
    prev = cur = None
    for i, b in enumerate(bars):
        if i == 0 or _day(b) != _day(bars[i - 1]):
            prev, cur = cur, [b.h, b.l, b.c]
        else:
            cur[0], cur[1], cur[2] = max(cur[0], b.h), min(cur[1], b.l), b.c
        out.append(tuple(prev) if prev else None)
    return out


def prior_day(bars) -> dict[str, list[float | None]]:
    """Yesterday's high, low and close on every bar of today (None on the first day in the bars). With intraday
    bars, pass view.history + view.bars and set history_days = 1 so yesterday is there."""
    p = _prev_day_hlc(bars)
    return {"pdh": [x[0] if x else None for x in p], "pdl": [x[1] if x else None for x in p],
            "pdc": [x[2] if x else None for x in p]}


def pivots(bars) -> dict[str, list[float | None]]:
    """Classic floor-trader pivots from yesterday's high (H), low (L) and close (C): P = (H + L + C) / 3,
    R1 = 2P - L, S1 = 2P - H, R2 = P + (H - L), S2 = P - (H - L). Fixed for the whole day."""
    out: dict[str, list[float | None]] = {k: [] for k in ("pivot", "r1", "s1", "r2", "s2")}
    for x in _prev_day_hlc(bars):
        if x is None:
            for v in out.values():
                v.append(None)
            continue
        h, l, c = x  # noqa: E741
        p = (h + l + c) / 3
        for k, v in (("pivot", p), ("r1", 2 * p - l), ("s1", 2 * p - h), ("r2", p + (h - l)), ("s2", p - (h - l))):
            out[k].append(v)
    return out


# ---- more oscillators ----

def roc(bars, n: int = 10) -> list[float | None]:
    """Rate of change: how much the close moved over the last n candles, as a fraction (0.05 = up 5%)."""
    return [None if i < n or not bars[i - n].c else bars[i].c / bars[i - n].c - 1 for i in range(len(bars))]


def williams_r(bars, n: int = 14) -> list[float | None]:
    """Williams %R: where the close sits in the last n candles' range, from 0 (at the top) down to -100 (at the
    bottom). The stochastic upside down. None while the range is flat or history is short."""
    out: list[float | None] = []
    for i, b in enumerate(bars):
        if i < n - 1:
            out.append(None); continue
        w = bars[i - n + 1:i + 1]
        hh, ll = max(x.h for x in w), min(x.l for x in w)
        out.append(-100 * (hh - b.c) / (hh - ll) if hh > ll else None)
    return out


def cci(bars, n: int = 20) -> list[float | None]:
    """Commodity Channel Index (Lambert): (typical price - its n-candle average) / (0.015 x the mean absolute
    deviation). Mostly between -100 and +100; outside that is an unusually strong move."""
    tp = [(b.h + b.l + b.c) / 3 for b in bars]
    out: list[float | None] = []
    for i in range(len(tp)):
        if i < n - 1:
            out.append(None); continue
        w = tp[i - n + 1:i + 1]
        m = sum(w) / n
        md = sum(abs(x - m) for x in w) / n
        out.append((tp[i] - m) / (0.015 * md) if md > 0 else None)
    return out


def mfi(bars, n: int = 14) -> list[float | None]:
    """Money Flow Index: an RSI that weighs each candle by its volume (typical price x volume). 0-100; over 80 =
    heavy buying lately, under 20 = heavy selling. Candles whose typical price didn't change count for neither."""
    tp = [(b.h + b.l + b.c) / 3 for b in bars]
    out: list[float | None] = []
    for i in range(len(bars)):
        if i < n:
            out.append(None); continue
        pos = neg = 0.0
        for j in range(i - n + 1, i + 1):
            flow = tp[j] * bars[j].v
            if tp[j] > tp[j - 1]:
                pos += flow
            elif tp[j] < tp[j - 1]:
                neg += flow
        out.append(None if pos == neg == 0 else 100.0 if neg == 0 else 100 - 100 / (1 + pos / neg))
    return out


# ---- candle shapes, swings and volatility ----

def heikin_ashi(bars) -> dict[str, list[float]]:
    """Heikin-Ashi ('average bar') candles, which smooth out the noise: close = (open + high + low + close) / 4,
    open = halfway between the previous Heikin-Ashi open and close (the first one: halfway between the real open
    and close), high / low = the most extreme of the real high / low and the new open and close. A run of green
    Heikin-Ashi candles with no lower wick is a steady up move."""
    o: list[float] = []
    h: list[float] = []
    lo: list[float] = []
    c: list[float] = []
    for i, b in enumerate(bars):
        cl = (b.o + b.h + b.l + b.c) / 4
        op = (b.o + b.c) / 2 if i == 0 else (o[-1] + c[-1]) / 2
        o.append(op); c.append(cl); h.append(max(b.h, op, cl)); lo.append(min(b.l, op, cl))
    return {"ha_open": o, "ha_high": h, "ha_low": lo, "ha_close": c}


def swing_levels(bars, strength: int = 3) -> dict[str, list[float | None]]:
    """The price of the newest swing high and swing low already confirmed by this candle (a high above the
    `strength` candles on each side; it is only known `strength` candles later, so nothing peeks). Handy for
    stops: under the last swing low for a long, above the last swing high for a short."""
    hi = _swings(bars, strength, True)
    lo = _swings(bars, strength, False)
    return {"swing_high": [bars[i].h if i is not None else None for i in hi],
            "swing_low": [bars[i].l if i is not None else None for i in lo]}


def narrow_range(bars, n: int = 7) -> dict[str, list[bool | None]]:
    """Quiet-candle flags. nr: this candle's high-low range is the smallest of the last n (NR7 when n = 7; None
    until there are n candles). inside: this candle's high and low both stay inside the previous candle's (None
    on the first candle). Quiet candles often come before a bigger move, in either direction."""
    nr: list[bool | None] = []
    inside: list[bool | None] = []
    for i, b in enumerate(bars):
        rng = b.h - b.l
        nr.append(None if i < n - 1 else all(rng < x.h - x.l for x in bars[i - n + 1:i]))
        inside.append(None if i == 0 else b.h < bars[i - 1].h and b.l > bars[i - 1].l)
    return {"nr": nr, "inside": inside}


def hist_volatility(bars, n: int = 20, per_year: float = 252) -> list[float | None]:
    """Historical volatility: the standard deviation (sample, n - 1) of the last n close-to-close log returns,
    scaled to a year with sqrt(per_year). 0.20 = moves like a '20% a year' stock. per_year is candles per year:
    252 for daily candles, 252 x 78 for 5-minute candles in the regular session. None before n returns, or after
    a zero or negative price."""
    rets: list[float | None] = [None]
    for a, b in zip(bars, bars[1:]):
        rets.append(math.log(b.c / a.c) if a.c > 0 and b.c > 0 else None)
    out: list[float | None] = []
    for i in range(len(bars)):
        w = rets[i - n + 1:i + 1] if i >= n else []
        if len(w) != n or None in w or n < 2:
            out.append(None); continue
        m = sum(w) / n
        out.append(math.sqrt(sum((x - m) ** 2 for x in w) / (n - 1) * per_year))
    return out
