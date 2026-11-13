"""Offline checks of botscope/indicators.py: hand-computed reference values, the no-peeking rule, gaps and short
history. No keys, no network: every bar here is made up in the test."""
import math
import random
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from botscope import indicators as ind
from botscope.bot import BarData

NY = ZoneInfo("America/New_York")


def bar(h, l, c, v=100.0, o=None, t=None):  # noqa: E741
    return BarData(t or datetime(2026, 1, 5, 9, 30, tzinfo=NY), l if o is None else o, h, l, c, v)


def day_bars(day: int, rows, start=time(9, 30), step=1):
    """rows of (h, l, c, v[, o]) as one day's candles, `step` minutes apart, from `start` (January 2026)."""
    t0 = datetime(2026, 1, day, start.hour, start.minute, tzinfo=NY)
    out = []
    for k, r in enumerate(rows):
        h, l, c, v = r[:4]  # noqa: E741
        out.append(BarData(t0 + timedelta(minutes=step * k), r[4] if len(r) > 4 else c, h, l, c, v))
    return out


def daily(rows):
    """rows of (h, l, c) as consecutive daily candles."""
    return [BarData(datetime(2026, 1, 1, 9, 30, tzinfo=NY) + timedelta(days=k), c, h, l, c, 1000.0)
            for k, (h, l, c) in enumerate(rows)]  # noqa: E741


def messy_days(seed=3, days=8):
    """Several 1-minute sessions with gaps between days, missing candles and some zero-volume candles."""
    rng = random.Random(seed)
    bars, px = [], 100.0
    for d in range(days):
        px *= 1 + rng.uniform(-0.03, 0.03)                       # overnight gap
        t = datetime(2026, 2, 2 + d, 9, 30, tzinfo=NY)
        for k in range(60):
            if rng.random() < 0.1:
                continue                                         # a missing candle
            o = px
            px *= 1 + rng.uniform(-0.004, 0.004)
            h, l = max(o, px) * (1 + rng.uniform(0, 0.002)), min(o, px) * (1 - rng.uniform(0, 0.002))  # noqa: E741
            v = 0.0 if rng.random() < 0.05 else rng.uniform(50, 500) * (3 if k < 10 else 1)
            bars.append(BarData(t + timedelta(minutes=k), o, h, l, px, v))
    return bars


# ---- no peeking: value i never changes when later bars are added ----

def _series(out):
    return out.values() if isinstance(out, dict) else [out]


@pytest.mark.parametrize("fn", [
    lambda b: ind.rvol(b, days=3),
    lambda b: ind.anchored_vwap(b, "day"),
    lambda b: ind.anchored_vwap(b, "gap", min_gap=0.01),
    lambda b: ind.anchored_vwap(b, "swing_high", strength=2),
    lambda b: ind.anchored_vwap(b, "swing_low", strength=2),
    lambda b: ind.vwap_bands(b, "day"),
    lambda b: ind.adx(b, 5),
    lambda b: ind.chop(b, 5),
    lambda b: ind.opening_range(b, 15),
    lambda b: ind.atr(b, 5),
    lambda b: ind.keltner(b, 8, 2, 5),
    lambda b: ind.supertrend(b, 5, 2),
    ind.obv,
    ind.ad_line,
    lambda b: ind.zscore(b, 6),
    ind.gaps,
    lambda b: ind.rsi(b, 5),
    lambda b: ind.bollinger(b, 8),
    lambda b: ind.macd(b, 3, 6, 4),
    lambda b: ind.donchian(b, 5),
    lambda b: ind.stochastic(b, 5, 2, 2),
    ind.prior_day,
    ind.pivots,
    lambda b: ind.roc(b, 5),
    lambda b: ind.williams_r(b, 5),
    lambda b: ind.cci(b, 5),
    lambda b: ind.mfi(b, 5),
    ind.heikin_ashi,
    lambda b: ind.swing_levels(b, 2),
    lambda b: ind.narrow_range(b, 4),
    lambda b: ind.hist_volatility(b, 5),
], ids=["rvol", "avwap_day", "avwap_gap", "avwap_swing_high", "avwap_swing_low", "vwap_bands", "adx", "chop", "opening_range",
        "atr", "keltner", "supertrend", "obv", "ad_line", "zscore", "gaps", "rsi", "bollinger", "macd",
        "donchian", "stochastic", "prior_day", "pivots", "roc", "williams_r", "cci", "mfi", "heikin_ashi",
        "swing_levels", "narrow_range", "hist_volatility"])
def test_no_look_ahead(fn):
    bars = messy_days()
    full = [list(s) for s in _series(fn(bars))]
    for k in range(1, len(bars) + 1, 7):
        part = [list(s) for s in _series(fn(bars[:k]))]
        for p, f in zip(part, full):
            assert len(p) == k
            assert p == f[:k], f"value changed once bars after {k} were added"


@pytest.mark.parametrize("fn", [ind.rvol, ind.anchored_vwap, ind.adx, ind.chop, ind.opening_range, ind.atr, ind.keltner,
                                ind.supertrend, ind.obv, ind.ad_line, ind.zscore, ind.gaps, ind.rsi,
                                ind.bollinger, ind.macd, ind.donchian, ind.stochastic, ind.vwap_bands, ind.prior_day,
                                ind.pivots, ind.roc, ind.williams_r, ind.cci, ind.mfi,
                                ind.heikin_ashi, ind.swing_levels, ind.narrow_range, ind.hist_volatility])
def test_empty_and_one_bar(fn):
    for s in _series(fn([])):
        assert s == []
    for s in _series(fn([bar(11, 9, 10)])):
        assert len(s) == 1


# ---- relative volume by time of day ----

def test_rvol_hand_computed():
    d1 = day_bars(5, [(1, 1, 1, 100), (1, 1, 1, 50), (1, 1, 1, 50)])
    d2 = day_bars(6, [(1, 1, 1, 300), (1, 1, 1, 100), (1, 1, 1, 100)])
    d3 = day_bars(7, [(1, 1, 1, 400), (1, 1, 1, 0), (1, 1, 1, 200)])
    r = ind.rvol(d1 + d2 + d3, days=2, min_days=2)
    assert r[:6] == [None] * 6                       # days 1-2 don't have 2 earlier days yet
    assert r[6] == pytest.approx(400 / ((100 + 300) / 2))            # 2.0
    assert r[7] == pytest.approx(400 / ((150 + 400) / 2))            # 1.4545
    assert r[8] == pytest.approx(600 / ((200 + 500) / 2))            # 1.7143


def test_rvol_compares_same_time_of_day_not_the_daily_average():
    """Mornings are always busy: a normal morning must read about 1.0, not 'high volume'."""
    normal = [(1, 1, 1, 1000)] + [(1, 1, 1, 10)] * 9                  # every day: big first minute, then quiet
    bars = sum((day_bars(5 + d, normal) for d in range(4)), [])
    r = ind.rvol(bars, days=3)
    assert r[30] == pytest.approx(1.0) and r[39] == pytest.approx(1.0)


def test_rvol_only_uses_the_last_n_days():
    bars = day_bars(5, [(1, 1, 1, 10_000)]) + day_bars(6, [(1, 1, 1, 100)]) + day_bars(7, [(1, 1, 1, 200)])
    assert ind.rvol(bars, days=1)[2] == pytest.approx(2.0)          # day 5's huge volume is out of the window


def test_rvol_missing_candle_counts_what_the_day_had_by_then():
    d1 = day_bars(5, [(1, 1, 1, 100), (1, 1, 1, 100), (1, 1, 1, 100)])
    d1 = [d1[0], d1[2]]                                              # 9:31 candle missing
    d2 = day_bars(6, [(1, 1, 1, 100), (1, 1, 1, 100), (1, 1, 1, 100)])
    r = ind.rvol(d1 + d2, days=1)
    assert r[2:] == pytest.approx([1.0, 2.0, 1.5])                   # by 9:31 day 1 had only traded 100


def test_rvol_short_history_and_dead_volume():
    d1 = day_bars(5, [(1, 1, 1, 0), (1, 1, 1, 100)])
    d2 = day_bars(6, [(1, 1, 1, 50), (1, 1, 1, 50)])
    r = ind.rvol(d1 + d2, days=10)                                   # needs 5 earlier days by default
    assert r == [None] * 4
    r = ind.rvol(d1 + d2, days=10, min_days=1)
    assert r[2] is None and r[3] == pytest.approx(1.0)               # day 1 traded nothing by 9:30: no ratio


# ---- anchored VWAP ----

def test_vwap_day_anchor_hand_computed():
    d1 = day_bars(5, [(12, 9, 9, 100), (13, 10, 13, 300)])           # typical 10 and 12
    d2 = day_bars(6, [(21, 18, 21, 50)])                             # typical 20: a new day starts over
    v = ind.anchored_vwap(d1 + d2, "day")
    assert v == pytest.approx([10.0, (10 * 100 + 12 * 300) / 400, 20.0])   # 11.5 in the middle


def test_vwap_no_volume_yet_is_none():
    v = ind.anchored_vwap(day_bars(5, [(11, 9, 10, 0), (13, 11, 12, 10)]), "day")
    assert v[0] is None and v[1] == pytest.approx(12.0)


def test_vwap_fixed_bar_and_time_anchor():
    bars = day_bars(5, [(10, 10, 10, 1), (20, 20, 20, 1), (30, 30, 30, 3)])
    assert ind.anchored_vwap(bars, 1) == [None, 20.0, pytest.approx(27.5)]
    assert ind.anchored_vwap(bars, bars[1].t) == ind.anchored_vwap(bars, 1)
    assert ind.anchored_vwap(bars, bars[2].t + timedelta(hours=1)) == [None, None, None]
    with pytest.raises(ValueError):
        ind.anchored_vwap(bars, "week")


def test_vwap_gap_anchor():
    d1 = day_bars(5, [(10, 10, 10, 1)])
    d2 = day_bars(6, [(10.02, 10.02, 10.02, 1, 10.02)])             # 0.2% gap: too small to anchor
    d3 = day_bars(7, [(11, 11, 11, 1, 11), (12, 12, 12, 1)])        # 9.8% gap up: anchors here
    bars = d1 + d2 + d3
    assert ind.anchors(bars, "gap") == [None, None, 2, 2]
    assert ind.anchored_vwap(bars, "gap") == [None, None, 11.0, pytest.approx(11.5)]


def test_vwap_swing_anchor_waits_for_confirmation():
    hs = [10, 11, 15, 12, 11, 13, 14]                                # swing high at bar 2, known only at bar 4
    bars = daily([(h, h - 1, h - 0.5) for h in hs])
    a = ind.anchors(bars, "swing_high", strength=2)
    assert a == [None, None, None, None, 2, 2, 2]
    lows = daily([(h, h - 1, h - 0.5) for h in [15, 14, 10, 13, 14]])
    assert ind.anchors(lows, "swing_low", strength=2) == [None, None, None, None, 2]


def test_vwap_bands_hand_computed():
    """Typical prices 10 (volume 1) and 20 (volume 3): VWAP 17.5; weighted variance (1 x 7.5^2 + 3 x 2.5^2) / 4
    = 18.75, so one standard deviation is 4.33 and k = 2 bands sit 8.66 away."""
    bars = day_bars(5, [(10, 10, 10, 1), (20, 20, 20, 3)])
    b = ind.vwap_bands(bars, "day", 2)
    assert b["vwap"] == pytest.approx([10, 17.5]) and b["vwap"] == pytest.approx(ind.anchored_vwap(bars, "day"))
    assert b["vwap_upper"] == pytest.approx([10, 17.5 + 2 * math.sqrt(18.75)])
    assert b["vwap_lower"][1] == pytest.approx(17.5 - 2 * math.sqrt(18.75))
    assert ind.vwap_bands(day_bars(5, [(10, 10, 10, 0)]))["vwap"] == [None]


# ---- ADX / DMI ----

ADX_BARS = daily([(10, 8, 9), (11, 9, 10), (12, 9, 11), (11, 7, 8), (10, 8, 9)])


def test_adx_hand_computed():
    """n = 2, worked by hand:
    bar 1: TR 2, +DM 1, -DM 0.   bar 2: TR 3, +DM 1.   bar 3: TR 4, -DM 2.   bar 4: TR 2, no DM.
    bar 2: sums TR 5, +DM 2, -DM 0  -> +DI 40, -DI 0, DX 100.
    bar 3: TR 5-2.5+4 = 6.5, +DM 2-1 = 1, -DM 0+2 = 2 -> +DI 15.38, -DI 30.77, DX 33.33; ADX (100+33.33)/2 = 66.67.
    bar 4: TR 6.5-3.25+2 = 5.25, +DM 0.5, -DM 1 -> +DI 9.52, -DI 19.05, DX 33.33; ADX (66.67+33.33)/2 = 50."""
    r = ind.adx(ADX_BARS, 2)
    assert r["plus_di"] == pytest.approx([None, None, 40.0, 100 / 6.5, 50 / 5.25])
    assert r["minus_di"] == pytest.approx([None, None, 0.0, 200 / 6.5, 100 / 5.25])
    assert r["adx"] == pytest.approx([None, None, None, 200 / 3, 50.0])


def test_adx_straight_up_trend_is_100():
    """The textbook extreme: every day a higher high and a higher low -> +DI 100, -DI 0, ADX 100."""
    r = ind.adx(daily([(i + 1, i, i + 1) for i in range(40)]), 14)   # closes at the high: TR = 1 = +DM
    assert r["adx"][26] is None and r["adx"][27] == pytest.approx(100.0)
    assert r["plus_di"][14] == pytest.approx(100.0) and r["minus_di"][-1] == 0.0
    assert r["plus_di"][13] is None


def test_adx_flat_and_short_history():
    flat = ind.adx(daily([(10, 10, 10)] * 10), 3)
    assert flat["adx"][-1] == 0.0 and flat["plus_di"][-1] == 0.0          # no range at all: no trend, no crash
    short = ind.adx(daily([(10, 9, 9.5)] * 5), 14)
    assert all(v is None for s in short.values() for v in s)


def test_adx_true_range_includes_gaps():
    """A gap up whose candle has a tiny range still counts the gap in the true range."""
    r = ind.adx(daily([(10, 9, 10), (20, 19.9, 20)]), 1)
    assert r["plus_di"][1] == pytest.approx(100 * 10 / (20 - 10))


# ---- Choppiness Index ----

def test_chop_hand_computed():
    """n = 2 on ADX_BARS: bar 1 window is bars 0-1, TR 2 + 2 = 4, box 11 - 8 = 3 -> 100 log10(4/3) / log10(2)."""
    c = ind.chop(ADX_BARS, 2)
    assert c[0] is None
    assert c[1] == pytest.approx(100 * math.log10(4 / 3) / math.log10(2))       # 41.50
    assert c[3] == pytest.approx(100 * math.log10((3 + 4) / (12 - 7)) / math.log10(2))


def test_chop_extremes():
    """Well-known bounds: a staircase with no overlap is 0 (all trend); bars stuck in one box are 100 (all chop)."""
    stairs = daily([(i + 1, i, i + 1) for i in range(20)])
    assert ind.chop(stairs, 14)[-1] == pytest.approx(0.0, abs=1e-9)
    box = daily([(11, 9, 10)] * 20)
    assert ind.chop(box, 14)[-1] == pytest.approx(100.0)
    assert ind.chop(daily([(10, 10, 10)] * 5), 3)[-1] is None              # flat: undefined, not a crash
    with pytest.raises(ValueError):
        ind.chop(box, 1)


# ---- opening range ----

def test_opening_range_levels_appear_after_the_window():
    rows = [(101, 99, 100, 1), (103, 100, 102, 1), (102, 98, 99, 1), (104, 101, 103, 1)]
    d1 = day_bars(5, rows, step=10)                                  # 9:30, 9:40, 9:50, 10:00
    d2 = day_bars(6, [(50, 49, 50, 1), (52, 48, 51, 1)], step=30)    # 9:30, 10:00
    r = ind.opening_range(d1 + d2, minutes=30)
    assert r["or_high"] == [None, None, None, 103, None, 50]
    assert r["or_low"] == [None, None, None, 98, None, 49]


def test_opening_range_premarket_missing_open_and_custom_start():
    pre = day_bars(5, [(200, 1, 100, 1)], start=time(8, 0))          # premarket bar: never part of the range
    late = day_bars(5, [(105, 95, 100, 1)], start=time(10, 5))       # no candle in 9:30-10:00 that day
    r = ind.opening_range(pre + late, minutes=30)
    assert r == {"or_high": [None, None], "or_low": [None, None]}
    crypto = day_bars(5, [(10, 9, 9.5, 1), (11, 9.5, 10, 1)], start=time(0, 0), step=60)
    assert ind.opening_range(crypto, 60, start=time(0, 0))["or_high"] == [None, 10]


def test_catalog_is_plain_and_matches_the_functions():
    names = [r["name"] for r in ind.CATALOG]
    assert len(names) == len(set(names))
    for row in ind.CATALOG:
        assert callable(getattr(ind, row["name"]))
        assert row["what"] and len(row["what"]) < 220 and row["call"].startswith(row["name"] + "(")
        assert row["kind"] in ind.KINDS and f"ind.{row['name']}(" in row["example"]
    kinds = [r["kind"] for r in ind.CATALOG]
    assert kinds == sorted(kinds, key=ind.KINDS.index)                  # grouped, in the KINDS order


def test_every_catalog_example_runs_on_a_bot_view():
    """The examples are code a bot would copy, so each one runs here on a made-up view with enough history."""
    from botscope.bot import View
    bars = messy_days(days=8)
    today = [b for b in bars if b.t.date() == bars[-1].t.date()]
    view = View("SPY", today, {}, history=bars[:len(bars) - len(today)])
    for row in ind.CATALOG:
        value = eval(row["example"], {"ind": ind, "view": view})       # noqa: S307 - our own fixed strings
        assert value is not None, row["name"]


# ---- moving averages and ATR ----

def test_sma_and_ema_hand_computed():
    assert ind.sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
    assert ind.sma([None, 2, 4], 2) == [None, None, 3.0]
    assert ind.ema([1, 2, 3, 4], 2) == pytest.approx([None, 1.5, 2.5, 3.5])      # seed 1.5, then +2/3 of the gap
    assert ind.ema([None, None, 4, 6, 6], 2) == pytest.approx([None, None, None, 5.0, 5 + 2 / 3])


def test_atr_hand_computed():
    """n = 2: true ranges 2, 2, 3, 4, 2 -> seed (2+2)/2 = 2, then half-way steps: 2.5, 3.25, 2.625."""
    assert ind.atr(ADX_BARS, 2) == pytest.approx([None, 2.0, 2.5, 3.25, 2.625])
    assert ind.atr(ADX_BARS, 14) == [None] * 5


# ---- Keltner and Supertrend ----

def test_keltner_is_ema_plus_minus_atr():
    bars = messy_days(days=2)
    k = ind.keltner(bars, 20, 2.0, 10)
    mid, a = ind.ema([b.c for b in bars], 20), ind.atr(bars, 10)
    assert k["kc_mid"][18] is None and k["kc_upper"][18] is None
    for i in range(19, len(bars)):
        assert k["kc_mid"][i] == pytest.approx(mid[i])
        assert k["kc_upper"][i] - k["kc_mid"][i] == pytest.approx(2 * a[i])
        assert k["kc_mid"][i] - k["kc_lower"][i] == pytest.approx(2 * a[i])


SUPER_BARS = daily([(10, 8, 9), (11, 9, 10), (10, 6, 6.5), (8, 6, 7), (13, 11, 12.5)])


def test_supertrend_hand_computed():
    """n = 1, mult = 1, so the ATR is just each candle's true range (2, 2, 4, 2, 6):
    bar 0: middle 9 -> lower 7, upper 11; up trend, line 7.
    bar 1: lower 8 (may only rise: 8), upper 12 -> kept at 11; line 8.
    bar 2: lower 4 -> kept at 8; close 6.5 is under 8: flips DOWN, line = upper 11.
    bar 3: lower 5 (the last close 6.5 was under 8, so it resets to 5); upper 9 (may only fall: 9); line 9.
    bar 4: close 12.5 is over 9: flips UP; lower 6 (the last close 7 was over 5, so max(6, 5) = 6); line 6."""
    s = ind.supertrend(SUPER_BARS, 1, 1.0)
    assert s["supertrend"] == pytest.approx([7, 8, 11, 9, 6])
    assert s["direction"] == [1, 1, -1, -1, 1]


def test_supertrend_trails_an_up_trend_and_flips_on_a_crash():
    up = [(i + 1, i, i + 0.8) for i in range(30)]
    s = ind.supertrend(daily(up + [(25, 10, 11)]), 10, 3.0)
    assert s["direction"][8] is None and s["direction"][9] == 1
    line = s["supertrend"][9:30]
    assert all(b >= a for a, b in zip(line, line[1:]))              # in an up trend the line only moves up
    assert all(x < lo for x, (_, lo, _) in zip(line, up[9:30]))     # and stays under the candles
    assert s["direction"][30] == -1 and s["supertrend"][30] > 11


# ---- volume flow ----

def test_obv_hand_computed():
    bars = daily([(10, 8, 9), (11, 9, 10), (12, 9, 10), (11, 7, 8), (10, 8, 9)])
    bars = [BarData(b.t, b.o, b.h, b.l, b.c, v) for b, v in zip(bars, [500, 100, 200, 300, 50])]
    assert ind.obv(bars) == [0, 100, 100, -200, -150]                # up, flat, down, up


def test_ad_line_hand_computed():
    bars = [bar(10, 8, 9, 100), bar(11, 9, 11, 100), bar(12, 9, 9, 30), bar(5, 5, 5, 999)]
    assert ind.ad_line(bars) == pytest.approx([0, 100, 70, 70])     # middle, at the high, at the low, no range


# ---- z-score ----

def test_zscore_hand_computed():
    z = ind.zscore(daily([(c, c, c) for c in [1, 2, 3, 3, 3, 3]]), 3)
    assert z[:2] == [None, None]
    assert z[2] == pytest.approx(1 / math.sqrt(2 / 3))              # (3 - 2) / 0.8165 = 1.2247
    assert z[3] == pytest.approx((3 - 8 / 3) / math.sqrt(2 / 9))     # 0.7071
    assert z[5] is None                                              # 3, 3, 3: no spread, no z-score


# ---- gaps ----

def test_gaps_up_down_filled_and_first_day():
    d1 = day_bars(5, [(100, 99, 100, 1)])
    d2 = day_bars(6, [(103, 101.5, 102, 1, 102), (102, 99.9, 100.5, 1)])   # +2% gap, filled on the 2nd candle
    d3 = day_bars(7, [(99, 97, 98, 1, 98)])                                # -2.49% gap down from 100.5, not filled
    g = ind.gaps(d1 + d2 + d3)
    assert g["gap_pct"] == pytest.approx([None, 0.02, 0.02, (98 - 100.5) / 100.5])
    assert g["gap_filled"] == [None, False, True, False]


def test_gaps_on_daily_bars_and_a_flat_open():
    g = ind.gaps(daily([(10, 9, 10), (11, 10, 11)]))                 # opened at 11 (the close), low touched 10
    assert g["gap_pct"][1] == pytest.approx(0.1) and g["gap_filled"][1] is True
    flat = ind.gaps(day_bars(5, [(10, 9, 10, 1)]) + day_bars(6, [(11, 10, 11, 1, 10)]))
    assert flat["gap_pct"][1] == 0.0 and flat["gap_filled"][1] is True


# ---- momentum and bands ----

def closes_only(cs):
    return daily([(c, c, c) for c in cs])


def test_rsi_hand_computed_and_extremes():
    """n = 2, closes 1, 2, 3, 2: moves +1, +1, -1. Bar 2: average up 1, down 0 -> 100.
    Bar 3: up 1 + (0 - 1)/2 = 0.5, down 0 + (1 - 0)/2 = 0.5 -> RSI 50."""
    assert ind.rsi(closes_only([1, 2, 3, 2]), 2) == [None, None, 100.0, 50.0]
    assert ind.rsi(closes_only([5, 4, 3, 2]), 2)[-1] == 0.0
    assert ind.rsi(closes_only([5, 5, 5]), 2)[-1] == 50.0                # no movement: middle, not 100


def test_rsi_matches_the_pine_runtime_rsi():
    """Two separate implementations in BotScope agree (Pine scripts imported with ta.rsi use the other one)."""
    from botscope import pine_runtime
    bars = messy_days(days=2)
    mine, theirs = ind.rsi(bars, 14), pine_runtime._rsi([b.c for b in bars], 14)
    assert mine == pytest.approx(theirs)


def test_bollinger_hand_computed():
    """Closes 1, 2, 3 with n = 3: average 2, population standard deviation sqrt(2/3) = 0.8165, so the bands are
    2 +- 1.633 = 0.367 and 3.633; %B of the close 3 = (3 - 0.367) / 3.266 = 0.806; width = 3.266 / 2 = 1.633."""
    b = ind.bollinger(closes_only([1, 2, 3]), 3, 2)
    sd = math.sqrt(2 / 3)
    assert b["bb_mid"] == [None, None, 2.0]
    assert b["bb_upper"][2] == pytest.approx(2 + 2 * sd) and b["bb_lower"][2] == pytest.approx(2 - 2 * sd)
    assert b["bb_pct_b"][2] == pytest.approx((3 - (2 - 2 * sd)) / (4 * sd))
    assert b["bb_width"][2] == pytest.approx(4 * sd / 2)
    flat = ind.bollinger(closes_only([5, 5, 5]), 3)
    assert flat["bb_upper"][2] == 5.0 and flat["bb_pct_b"][2] is None     # no spread: no %B, no crash


def test_macd_hand_computed():
    """fast 1 (= the close itself), slow 2 on closes 1, 2, 3, 4: slow average 1.5, 2.5, 3.5 -> MACD 0.5 each bar;
    a signal of 1 is the MACD itself, so the histogram is 0."""
    m = ind.macd(closes_only([1, 2, 3, 4]), 1, 2, 1)
    assert m["macd"] == pytest.approx([None, 0.5, 0.5, 0.5])
    assert m["macd_signal"] == pytest.approx([None, 0.5, 0.5, 0.5])
    assert m["macd_hist"] == pytest.approx([None, 0, 0, 0])
    std = ind.macd(messy_days(days=2))
    assert std["macd"][24] is None and std["macd"][25] is not None
    assert std["macd_signal"][32] is None and std["macd_signal"][33] is not None   # 9 MACD values needed


def test_donchian_uses_the_candles_before_this_one():
    bars = daily([(10, 8, 9), (12, 9, 11), (11, 7, 8), (13, 10, 12.5)])
    d = ind.donchian(bars, 2)
    assert d["dc_high"] == [None, None, 12, 12] and d["dc_low"] == [None, None, 8, 7]
    assert bars[3].c > d["dc_high"][3]                                     # a breakout can be seen
    assert ind.donchian(bars, 2, include_current=True)["dc_high"] == [None, 12, 12, 13]


def test_stochastic_hand_computed():
    """n = 2, no smoothing: bar 1 range 8-12, close 11 -> 75; bar 2 range 7-12, close 8 -> 20; bar 3 range 7-13,
    close 12.5 -> 91.7. stoch_d over 2: (75 + 20)/2, (20 + 91.7)/2."""
    bars = daily([(10, 8, 9), (12, 9, 11), (11, 7, 8), (13, 10, 12.5)])
    s = ind.stochastic(bars, 2, 1, 2)
    assert s["stoch_k"] == pytest.approx([None, 75, 20, 5.5 / 6 * 100])
    assert s["stoch_d"] == pytest.approx([None, None, 47.5, (20 + 5.5 / 6 * 100) / 2])
    assert ind.stochastic(closes_only([5, 5, 5]), 2, 1, 1)["stoch_k"] == [None, None, None]


# ---- yesterday's levels and pivots ----

def test_prior_day_on_intraday_bars():
    d1 = day_bars(5, [(101, 99, 100, 1), (104, 100, 103, 1), (103, 97, 98, 1)])   # H 104, L 97, last close 98
    d2 = day_bars(6, [(99, 98, 98.5, 1), (100, 98, 99, 1)])
    p = ind.prior_day(d1 + d2)
    assert p["pdh"] == [None, None, None, 104, 104]
    assert p["pdl"] == [None, None, None, 97, 97] and p["pdc"] == [None, None, None, 98, 98]


def test_prior_day_on_daily_bars_is_the_bar_before():
    bars = daily([(10, 8, 9), (12, 9, 11), (11, 7, 8)])
    assert ind.prior_day(bars)["pdh"] == [None, 10, 12]


def test_pivots_hand_computed():
    """Yesterday H 12, L 8, C 11: P = 31/3 = 10.33, R1 = 2P - 8 = 12.67, S1 = 2P - 12 = 8.67, R2 = P + 4 = 14.33,
    S2 = P - 4 = 6.33."""
    bars = daily([(12, 8, 11), (13, 10, 12)])
    p = ind.pivots(bars)
    P = 31 / 3
    assert p["pivot"] == [None, pytest.approx(P)]
    assert p["r1"][1] == pytest.approx(2 * P - 8) and p["s1"][1] == pytest.approx(2 * P - 12)
    assert p["r2"][1] == pytest.approx(P + 4) and p["s2"][1] == pytest.approx(P - 4)


# ---- more oscillators ----

def test_roc_hand_computed():
    assert ind.roc(closes_only([100, 110, 99]), 1) == pytest.approx([None, 0.1, -0.1])
    assert ind.roc(closes_only([0, 5]), 1) == [None, None]                       # no division by zero


def test_williams_r_is_the_stochastic_upside_down():
    bars = daily([(10, 8, 9), (12, 9, 11), (11, 7, 8), (13, 10, 12.5)])
    w = ind.williams_r(bars, 2)
    assert w == pytest.approx([None, -25, -80, -0.5 / 6 * 100])                # bar 1: range 8-12, close 11
    k = ind.stochastic(bars, 2, 1, 1)["stoch_k"]
    assert all(a == pytest.approx(b - 100) for a, b in zip(w[1:], k[1:]))


def test_cci_hand_computed():
    """Typical prices 1, 2, 3 with n = 3: average 2, mean absolute deviation 2/3 -> (3 - 2) / (0.015 x 2/3) = 100."""
    c = ind.cci(closes_only([1, 2, 3, 3, 3, 3]), 3)
    assert c[:2] == [None, None] and c[2] == pytest.approx(100.0)
    assert c[5] is None                                                          # no deviation at all


def test_mfi_hand_computed():
    """n = 2, volume 1000 a day, typical prices 10, 11, 10.5, 12.
    Day 2: up flow 11 x 1000, down flow 10.5 x 1000 -> 100 x 11000 / 21500 = 51.16.
    Day 3: down 10500, up 12000 -> 100 x 12000 / 22500 = 53.33."""
    m = ind.mfi(closes_only([10, 11, 10.5, 12]), 2)
    assert m == pytest.approx([None, None, 100 * 11000 / 21500, 100 * 12000 / 22500])
    assert ind.mfi(closes_only([1, 2, 3]), 2)[-1] == 100.0
    assert ind.mfi(closes_only([5, 5, 5]), 2)[-1] is None


# ---- cross-checks and robustness ----

def test_building_blocks_match_the_pine_runtime():
    """BotScope's Pine importer has its own ta.sma / ta.ema / ta.atr / ta.stdev / ta.highest; both must agree."""
    from botscope import pine_runtime as pr
    bars = messy_days(days=3)
    n = len(bars)
    cols = {"high": [b.h for b in bars], "low": [b.l for b in bars], "close": [b.c for b in bars]}
    closes = cols["close"]
    assert ind.sma(closes, 20) == pytest.approx(pr.call("sma", [closes, 20], cols, n))
    assert ind.ema(closes, 20) == pytest.approx(pr.call("ema", [closes, 20], cols, n))
    assert ind.atr(bars, 14) == pytest.approx(pr.call("atr", [14], cols, n))
    sd = pr.call("stdev", [closes, 20], cols, n)
    bb = ind.bollinger(bars, 20, 2)
    assert [u - m if u is not None else None for u, m in zip(bb["bb_upper"], bb["bb_mid"])] == \
        pytest.approx([2 * x if x is not None else None for x in sd])
    dc = ind.donchian(bars, 20, include_current=True)
    assert dc["dc_high"] == pr.call("highest", [cols["high"], 20], cols, n)
    assert dc["dc_low"] == pr.call("lowest", [cols["low"], 20], cols, n)


def _odd_bars(rng, kind):
    t0 = datetime(2026, 3, 2, 9, 30, tzinfo=NY)
    out = []
    for k in range(rng.randint(0, 120)):
        t = t0 + timedelta(minutes=k * rng.choice([1, 1, 1, 7, 400]))          # some jumps into later days
        if kind == "flat":
            o = h = l = c = 50.0  # noqa: E741
        elif kind == "zero":
            o = h = l = c = 0.0  # noqa: E741
        else:
            o, c = rng.uniform(1, 1e6), rng.uniform(1, 1e6)
            h, l = max(o, c) * rng.uniform(1, 1.01), min(o, c) * rng.uniform(0.99, 1)  # noqa: E741
        out.append(BarData(t, o, h, l, c, rng.choice([0.0, rng.uniform(0, 1e9)])))
        t0 = t
    return out


def _all_outputs(bars):
    yield from _series(ind.rvol(bars, 3, 1))
    for a in ("day", "gap", "swing_high", "swing_low", 5):
        yield ind.anchored_vwap(bars, a)
        yield from _series(ind.vwap_bands(bars, a))
    for f in (ind.adx, ind.chop, ind.opening_range, ind.atr, ind.keltner, ind.supertrend, ind.obv, ind.ad_line,
              ind.zscore, ind.gaps, ind.rsi, ind.bollinger, ind.macd, ind.donchian, ind.stochastic, ind.prior_day,
              ind.pivots, ind.roc, ind.williams_r, ind.cci, ind.mfi, ind.heikin_ashi, ind.swing_levels,
              ind.narrow_range, ind.hist_volatility):
        yield from _series(f(bars))


@pytest.mark.parametrize("kind", ["random", "flat", "zero"])
def test_odd_input_never_crashes_or_gives_nan(kind):
    rng = random.Random(11)
    for _ in range(25):
        bars = _odd_bars(rng, kind)
        for s in _all_outputs(bars):
            assert len(s) == len(bars)
            for v in s:
                assert v is None or isinstance(v, bool) or math.isfinite(v), (kind, v)


# ---- candle shapes, swings and volatility ----

def test_heikin_ashi_hand_computed():
    """Candle 0 (10, 12, 9, 11): close (10+12+9+11)/4 = 10.5, open (10+11)/2 = 10.5, high 12, low 9.
    Candle 1 (11, 13, 10, 12): close 11.5, open (10.5+10.5)/2 = 10.5, high 13, low 10."""
    bars = [bar(12, 9, 11, o=10), bar(13, 10, 12, o=11)]
    ha = ind.heikin_ashi(bars)
    assert ha == {"ha_open": [10.5, 10.5], "ha_high": [12, 13], "ha_low": [9, 10], "ha_close": [10.5, 11.5]}


def test_swing_levels_are_the_confirmed_prices():
    hs = [10, 11, 15, 12, 11, 13, 14]                                # swing high 15 at bar 2, known at bar 4
    s = ind.swing_levels(daily([(h, h - 1, h - 0.5) for h in hs]), 2)
    assert s["swing_high"] == [None, None, None, None, 15, 15, 15]
    lows = ind.swing_levels(daily([(h, h - 1, h - 0.5) for h in [15, 14, 10, 13, 14]]), 2)
    assert lows["swing_low"] == [None, None, None, None, 9]


def test_narrow_range_and_inside_candles():
    bars = daily([(15, 10, 12), (14, 10, 12), (13, 10, 12), (12.5, 10.5, 12), (12.6, 10.6, 12)])  # ranges 5,4,3,2,2
    f = ind.narrow_range(bars, 3)
    assert f["nr"] == [None, None, True, True, False]                # a tie isn't the narrowest
    assert f["inside"] == [None, False, False, True, False]          # bar 2 shares bar 1's low: not inside


def test_hist_volatility_hand_computed():
    """Closes 100, 110, 99 with n = 2: log returns ln(1.1) and ln(0.9); sample variance of the two, times 252."""
    a, b = math.log(1.1), math.log(0.9)
    m = (a + b) / 2
    hv = ind.hist_volatility(closes_only([100, 110, 99]), 2, 252)
    assert hv[:2] == [None, None]
    assert hv[2] == pytest.approx(math.sqrt(((a - m) ** 2 + (b - m) ** 2) / 1 * 252))      # 2.25
    steady = ind.hist_volatility(closes_only([100 * 1.01 ** k for k in range(30)]), 20)
    assert steady[-1] == pytest.approx(0.0, abs=1e-9)                # the same move every day: no volatility
    assert ind.hist_volatility(closes_only([100, 0, 100, 101]), 2)[-1] is None
