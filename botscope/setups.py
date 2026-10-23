"""Screenshot confidence check: how did setups like the one in a screenshot REALLY do in the past?

Claude reads the screenshot (ticker, timeframe, date, what the setup is) and maps it to one of the SETUPS below. This
module finds every past bar where that setup fired (only bars BEFORE the screenshot's date, so it never peeks),
plays each one out the same simple way (stop 1 ATR away, target 1.5 ATR, out after 10 bars, costs paid), and turns
the results into a confidence level from very low to very high, with the sample size and the data source.

Wins only as a count (never a percentage), never a promise: a fixed, simple trade plan on past matches. Not financial advice.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from . import backtest, data

LEVELS = ("very low", "low", "medium", "high", "very high")
STOP_ATR, TARGET_ATR, HOLD_BARS, ATR_N = 1.0, 1.5, 10, 14
HISTORY_DAYS = {"1Day": 365 * 10, "1Hour": 365 * 2, "15Min": 180}
MIN_FOR_ANY = 30


def _sma(xs, n, i):
    return sum(xs[i - n + 1:i + 1]) / n if i >= n - 1 else None


def _atr(bs, i, n=ATR_N):
    if i < n:
        return None
    trs = [max(bs[k].h, bs[k - 1].c) - min(bs[k].l, bs[k - 1].c) for k in range(i - n + 1, i + 1)]
    return sum(trs) / n


def _breakout(bs, c, i):   return i >= 21 and c[i] > max(b.h for b in bs[i - 20:i])
def _breakdown(bs, c, i):  return i >= 21 and c[i] < min(b.l for b in bs[i - 20:i])
def _gap_up(bs, c, i):     return i >= 1 and bs[i].o > bs[i - 1].h * 1.01
def _gap_down(bs, c, i):   return i >= 1 and bs[i].o < bs[i - 1].l * 0.99


def _dip_in_uptrend(bs, c, i):
    s20, s50 = _sma(c, 20, i), _sma(c, 50, i)
    return bool(s20 and s50) and s20 > s50 and c[i] < s20 and c[i] > s50 and c[i - 1] >= _sma(c, 20, i - 1)


def _rally_in_downtrend(bs, c, i):
    s20, s50 = _sma(c, 20, i), _sma(c, 50, i)
    return bool(s20 and s50) and s20 < s50 and c[i] > s20 and c[i] < s50 and c[i - 1] <= _sma(c, 20, i - 1)


def _oversold(bs, c, i):
    return i >= 10 and c[i] < c[i - 1] < c[i - 2] < c[i - 3] and c[i] < max(b.h for b in bs[i - 10:i]) * 0.95


def _tight_range(bs, c, i):          # NR7: the narrowest bar of the last 7, in an uptrend (long on the squeeze)
    s50 = _sma(c, 50, i)
    rng = [b.h - b.l for b in bs[i - 6:i + 1]] if i >= 6 else []
    return bool(rng and s50) and rng[-1] == min(rng) and c[i] > s50


SETUPS = {
    "breakout": ("long", _breakout, "close above the highest high of the last 20 bars"),
    "breakdown": ("short", _breakdown, "close below the lowest low of the last 20 bars"),
    "gap_up": ("long", _gap_up, "opens 1%+ above the last bar's high"),
    "gap_down": ("short", _gap_down, "opens 1%+ below the last bar's low"),
    "dip_in_uptrend": ("long", _dip_in_uptrend, "20-average above the 50, price dips under the 20 but stays above the 50"),
    "rally_in_downtrend": ("short", _rally_in_downtrend, "20-average below the 50, price pops over the 20 but stays under the 50"),
    "oversold_bounce": ("long", _oversold, "4 lower closes in a row, 5%+ under the 10-bar high"),
    "tight_range_uptrend": ("long", _tight_range, "narrowest bar of the last 7, above the 50-average"),
}


def play(bs, i, side, cost_bps):
    """One match played out: entry at the signal bar's close, stop 1 ATR, target 1.5 ATR, out after 10 bars."""
    atr = _atr(bs, i)
    if not atr or i + 1 >= len(bs):
        return None
    d, e = (1 if side == "long" else -1), bs[i].c
    stop, tgt = e - d * STOP_ATR * atr, e + d * TARGET_ATR * atr
    out = None
    for b in bs[i + 1:i + 1 + HOLD_BARS]:
        hit_stop = b.l <= stop if d == 1 else b.h >= stop
        hit_tgt = b.h >= tgt if d == 1 else b.l <= tgt
        if hit_stop:                                  # both in one bar: assume the stop (the honest worst case)
            out = stop; break
        if hit_tgt:
            out = tgt; break
    if out is None:
        out = bs[min(i + HOLD_BARS, len(bs) - 1)].c
    risk = STOP_ATR * atr
    return round((d * (out - e) - e * 2 * cost_bps / 1e4) / risk, 3)


def level(rs: list[float]) -> tuple[int, list[str]]:
    n = len(rs)
    if n < MIN_FOR_ANY:
        return 0, [f"only {n} past matches (need {MIN_FOR_ANY}+ to say anything)"]
    avg = sum(rs) / n
    if avg <= 0:
        return 0, [f"past matches lost money on average ({avg:+.2f}R each after costs)"]
    rng = random.Random(7)
    lo = sorted(sum(rng.choice(rs) for _ in rs) for _ in range(1000))[50]
    if lo <= 0:
        return 1, [f"made money over {n} past matches, but the bad end of the reshuffle range is a loss (could be luck)"]
    step = 2 if n < 100 else 3 if n < 300 else 4
    return step, [f"made money over {n} past matches ({avg:+.2f}R each), even at the bad end of the range"]


def check(symbol: str, setup: str, timeframe: str = "1Day", as_of: str | None = None, fetch=None) -> dict:
    if setup not in SETUPS:
        return {"confidence": "very low", "why": ["not enough to go on: the setup couldn't be matched to a known "
                                                  "pattern"], "known_setups": {k: v[2] for k, v in SETUPS.items()},
                "note": "Not financial advice."}
    if timeframe not in HISTORY_DAYS:
        raise ValueError(f"timeframe must be one of {', '.join(HISTORY_DAYS)}")
    side, fired, plain = SETUPS[setup]
    end = date.fromisoformat(as_of) if as_of else date.today()
    end -= timedelta(days=1)                         # only bars before the screenshot's day: never peek
    bs, _ = data.clean((fetch or data.bars)(symbol.upper(), end - timedelta(days=HISTORY_DAYS[timeframe]), end,
                                            timeframe, "sip"))
    c = [b.c for b in bs]
    cost = backtest.COSTS["swing"]["entry_bps"] if timeframe == "1Day" else backtest.COSTS["stock_intraday"]["entry_bps"]
    rs, last_i = [], -HOLD_BARS
    for i in range(len(bs) - 1):
        if i - last_i < HOLD_BARS or not fired(bs, c, i):     # one match at a time, no overlapping trades
            continue
        r = play(bs, i, side, cost)
        if r is not None:
            rs.append(r); last_i = i
    step, why = level(rs)
    return {"symbol": symbol.upper(), "setup": setup, "setup_means": plain, "side": side, "timeframe": timeframe,
            "confidence": LEVELS[step], "step": step, "levels": list(LEVELS), "why": why,
            "sample": {"matches": len(rs), "wins": sum(r > 0 for r in rs), "total_r": round(sum(rs), 2),
                       "from": str(bs[0].t.date()) if bs else None, "to": str(bs[-1].t.date()) if bs else None},
            "how": f"each past match: in at the close, stop {STOP_ATR:g} ATR, target {TARGET_ATR:g} ATR, out after "
                   f"{HOLD_BARS} bars, costs paid; one match at a time",
            "source": "Alpaca SIP bars (all US exchanges), your own keys",
            "note": "How similar setups did in the past, on this one stock. Not a prediction and not a promise, "
                    "not financial advice."}
