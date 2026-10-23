"""Strategy factory: describe a goal ("a calm daily ETF bot"), get up to 5 candidate bots in the normal bot format,
each run through the honest pipeline, and keep only the survivors.

Pipeline per candidate, one at a time: check_bot (made-up bars) -> honest report (every year since 2016, all years
UNTESTED because the candidates use textbook settings never tuned here) -> costs doubled -> without its 3 best
trades -> losing years -> the goal's own limits (e.g. "calm") -> still works in the later half of the years ->
settings 20% smaller and bigger (no knife edges) -> luck meter (random twins). The first failure drops
the candidate with a plain-English reason. Survivors are ranked by confidence level, never by profit alone.

Picking the best of several candidates on the same years makes the winner look better than it is, so every run
says how many were tried. Candidate files live in data/factory/<run>/ until the user adopts one (adopt_candidate).
Not financial advice.
"""
from __future__ import annotations

import importlib.util
import inspect
import os
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from . import backtest, checkpoints, confidence, journal, loader, luck, report, scaffold
from .bot import Bot
from .env import ROOT

PROGRESS: dict = {}     # the run in progress, for Studio's progress line: {goal, done, total, now}
MAX_CANDIDATES = 5
HOLDOUT_DAYS = 365       # the last year is never used to keep or drop a candidate, then shown for survivors only
LUCK_TWINS = 50          # lighter than the full luck meter's 100; enough to call "looks like luck"
LUCK_SHUFFLES = 5
CALM_MAX_DROP_R = 15.0   # "calm": deepest drop on untested years, in R
CALM_MAX_STREAK = 8      # "calm": longest losing streak
ACTIVE_MIN_PER_YEAR = 25  # "active": trades a year across its symbols
HANDS_OFF_MAX_PER_YEAR = 15  # "part-time / hands-off": trades a year across its symbols


def factory_dir() -> Path:
    if os.getenv("BOTSCOPE_FACTORY_DIR"):
        return Path(os.path.expanduser(os.environ["BOTSCOPE_FACTORY_DIR"]))
    from . import userdata
    from .env import demo_mode
    rel = "demo/factory" if demo_mode() else "factory"
    return userdata.place(ROOT / "data" / rel, rel)


# ---------------------------------------------------------------- reading the goal

ETFS = ["SPY", "QQQ", "IWM", "DIA"]
TECH = ["QQQ", "AAPL", "MSFT", "NVDA"]
STOCKS = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]
CRYPTO = ["BTC/USD", "ETH/USD"]
_NOT_TICKERS = {"ETF", "ETFS", "I", "A", "AN", "RSI", "AND", "OR", "THE", "BOT", "MY", "NO", "US", "USA", "VWAP",
                "SMA", "EMA", "ATR", "ORB", "AI", "OK", "IPO", "CPI", "FED", "S", "P"}


_WISHES = r"retire|\bsafe\b|rich quick|fast money|money fast|quick money|double (my|your)|" \
          r"passive income|replace my (job|income)|college fund|savings"


def caution(g: str) -> str | None:
    """A plain answer when the goal asks for something no trading bot can give (safety, fast money, retirement).
    The promise words themselves are read with the scam checker's own patterns."""
    from . import scam
    if not re.search(_WISHES, g) and not any(w >= 3 and re.search(p, g, re.I) for _, _, w, p in scam.FLAGS):
        return None
    return ("A word on the goal: no trading bot is safe, and none makes money fast on purpose; every one here can lose. "
            "This only shows how simple ideas did on past untested days, after costs, on paper. Money you need (for "
            "retirement, school or bills) is a question for a licensed adviser, not a bot.")


def understand(goal: str, symbols: list[str] | None = None) -> dict:
    """The goal in BotScope terms: timeframe, sides, symbols, style, calm. Plain keyword reading, shown back to the
    user so they can correct it."""
    g = goal.lower()
    crypto = bool(re.search(r"crypto|bitcoin|\bbtc\b|\bether(eum)?\b|\beth\b|\bcoins?\b", g)) or any(
        "/" in s for s in symbols or [])
    intraday = not crypto and any(w in g for w in ("intraday", "day trad", "daytrad", "minute", "scalp", "opening range", "same day",
                                    "5-min", "5 min"))
    timeframe = "5Min" if intraday else "1Day"
    if crypto:
        sides = "long"                                   # Alpaca paper can't short crypto
    elif re.search(r"short[- ]only|only short", g):
        sides = "short"
    elif re.search(r"long[- ]only|only long|no short|never short|calm|safe|quiet|steady|beginner", g):
        sides = "long"
    elif re.search(r"long and short|both|short", g):
        sides = "both"
    else:
        sides = "both" if intraday else "long"
    named = [t for t in re.findall(r"\b[A-Z]{1,5}\b", goal) if t not in _NOT_TICKERS]
    if crypto:
        named = [{"BTC": "BTC/USD", "ETH": "ETH/USD"}[t] for t in named if t in ("BTC", "ETH")] or (
            ["BTC/USD"] if re.search(r"bitcoin|\bbtc\b", g) and not re.search(r"ether|\beth\b", g) else
            ["ETH/USD"] if re.search(r"ether|\beth\b", g) and not re.search(r"bitcoin|\bbtc\b", g) else CRYPTO)
    syms = [s.upper() for s in (symbols or named)][:backtest.MAX_SYMBOLS]
    if not syms:
        syms = ETFS if re.search(r"\betfs?\b|index|indexes|indices", g) else TECH if "tech" in g else STOCKS
    if intraday:
        syms = syms[:3]                                        # intraday reports download a lot: keep it light
    asked = list(dict.fromkeys(x.upper() for x in (symbols or named)))
    dropped = [x for x in asked if x not in syms]               # say it, never shrink the goal quietly
    style = ("dip" if re.search(r"dip|pullback|revers|bounce|oversold", g) else
             "breakout" if re.search(r"breakout|momentum|trend|break out", g) else "any")
    calm = bool(re.search(r"calm|safe|steady|quiet|low[- ]stress|smooth|beginner|chill", g))
    busy = (("active", ACTIVE_MIN_PER_YEAR) if re.search(r"\bactive\b|lots of trades|many trades|busy|frequent", g) else
            ("hands-off", HANDS_OFF_MAX_PER_YEAR) if re.search(r"part[- ]time|hands[- ]off|few trades|lazy|set and forget|"
                                                                r"rarely|low[- ]maintenance", g) else None)
    return {"timeframe": timeframe, "sides": sides, "symbols": syms, "style": style, "calm": calm,
            "busy": busy, "asset": "crypto" if crypto else None, "caution": caution(g),
            "read_as": f"{'intraday 5-minute' if intraday else 'daily'} {'crypto ' if crypto else ''}bot"
                       f"{' (24/7 days, crypto trading costs)' if crypto else ''}, "
                       f"{sides} side{'s' if sides == 'both' else ''}"
                       f", on {', '.join(syms)}"
                       + (f" ({', '.join(dropped)} left out: {len(syms)} symbols at most{' intraday' if intraday else ''})"
                          if dropped else "") + (", calm (small drops and short losing streaks)" if calm else "")
                       + (f", {style} style" if style != "any" else "")
                       + (f", {busy[0]} ({'at least' if busy[0] == 'active' else 'at most'} {busy[1]} trades a year)"
                          if busy else "")}


# ---------------------------------------------------------------- the candidate templates

_HELPERS = '''

def _avg(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


def _range(bars, n):
    return sum(b.h - b.l for b in bars[-n:]) / n if len(bars) >= n else None


def _rsi(closes, n):
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
'''

TEMPLATES = {
    "dip_buy": {
        "lines": ['trend_days', 'exit_avg_days'],
        "timeframe": "1Day", "sides": ("long",), "style": "dip", "calm": True, "name": "Dip buy",
        "description": "Buys a sharp 2-day dip when the price is above its 200-day average; sells on the bounce.",
        "params": {"trend_days": 200, "rsi_days": 2, "rsi_below": 10, "exit_avg_days": 5, "stop_ranges": 3.0,
                   "range_days": 10, "max_hold_days": 10},
        "rules": ["Uptrend: the close is above the {trend_days}-day average close.",
                  "Dip: the {rsi_days}-day RSI closes under {rsi_below}.",
                  "Buy at that close. Stop: {stop_ranges}x the {range_days}-day average daily range below the entry.",
                  "Sell when a close is above the {exit_avg_days}-day average close, or after {max_hold_days} trading days."],
        "lookback": "trend_days",
        "entry": '''        closes = [b.c for b in view.bars]
        trend = _avg(closes, self.p["trend_days"])
        if trend is None:
            return NoTrade("not enough days of history yet")
        if closes[-1] <= trend:
            return NoTrade(f"below the {self.p['trend_days']}-day average: not an uptrend")
        rsi = _rsi(closes[-60:], self.p["rsi_days"])           # only on trend days: the slow part
        if rsi is None or rsi >= self.p["rsi_below"]:
            return NoTrade("no sharp dip" + (f" (RSI {rsi:.0f})" if rsi is not None else ""))
        rng = _range(view.bars, self.p["range_days"])
        return Entry("long", closes[-1] - self.p["stop_ranges"] * rng, None, f"RSI {rsi:.0f} dip in an uptrend")''',
        "exit": '''        closes = [b.c for b in view.bars]
        avg = _avg(closes, self.p["exit_avg_days"])
        if avg is not None and view.bars[-1].t > pos.entry_time and closes[-1] > avg:
            return Exit("bounced above the short average")
        if sum(1 for b in view.bars if b.t > pos.entry_time) >= self.p["max_hold_days"]:
            return Exit("held long enough")
        return None''',
    },
    "band_reversion": {
        "lines": ['avg_days', 'trend_days'],
        "timeframe": "1Day", "sides": ("long",), "style": "dip", "calm": True, "name": "Band reversion",
        "description": "Buys a close far below the 20-day average (2 standard deviations) in an uptrend; sells back at the average.",
        "params": {"avg_days": 20, "band_width": 2.0, "trend_days": 150, "stop_ranges": 2.5, "range_days": 14,
                   "max_hold_days": 12},
        "rules": ["Uptrend: the close is above the {trend_days}-day average close.",
                  "Stretch: the close is more than {band_width} standard deviations below the {avg_days}-day average.",
                  "Buy at that close. Stop: {stop_ranges}x the {range_days}-day average daily range below the entry.",
                  "Sell when a close gets back to the {avg_days}-day average, or after {max_hold_days} trading days."],
        "lookback": "trend_days",
        "entry": '''        closes = [b.c for b in view.bars]
        n = self.p["avg_days"]
        trend, avg = _avg(closes, self.p["trend_days"]), _avg(closes, n)
        if trend is None or avg is None:
            return NoTrade("not enough days of history yet")
        sd = (sum((x - avg) ** 2 for x in closes[-n:]) / n) ** 0.5
        if closes[-1] <= trend:
            return NoTrade("not an uptrend")
        if closes[-1] > avg - self.p["band_width"] * sd:
            return NoTrade("not stretched below the band")
        rng = _range(view.bars, self.p["range_days"])
        return Entry("long", closes[-1] - self.p["stop_ranges"] * rng, None, "stretched below the band in an uptrend")''',
        "exit": '''        closes = [b.c for b in view.bars]
        avg = _avg(closes, self.p["avg_days"])
        if avg is not None and view.bars[-1].t > pos.entry_time and closes[-1] >= avg:
            return Exit("back at the average")
        if sum(1 for b in view.bars if b.t > pos.entry_time) >= self.p["max_hold_days"]:
            return Exit("held long enough")
        return None''',
    },
    "trend_ride": {
        "lines": ['fast_days', 'slow_days'],
        "timeframe": "1Day", "sides": ("long",), "style": "breakout", "calm": True, "name": "Trend ride",
        "description": "Buys when the price closes back above its 50-day average while the 50-day is above the 200-day; sells on a close below the 50-day.",
        "params": {"fast_days": 50, "slow_days": 200, "stop_ranges": 4.0, "range_days": 20},
        "rules": ["Trend: the {fast_days}-day average is above the {slow_days}-day average.",
                  "Buy when the close crosses back above the {fast_days}-day average.",
                  "Stop: {stop_ranges}x the {range_days}-day average daily range below the entry.",
                  "Sell when a close falls below the {fast_days}-day average."],
        "lookback": "slow_days",
        "entry": '''        closes = [b.c for b in view.bars]
        fast, slow = _avg(closes, self.p["fast_days"]), _avg(closes, self.p["slow_days"])
        prev = _avg(closes[:-1], self.p["fast_days"])
        if fast is None or slow is None or prev is None:
            return NoTrade("not enough days of history yet")
        if fast <= slow:
            return NoTrade("the fast average is under the slow one: no trend")
        if not (closes[-2] <= prev and closes[-1] > fast):
            return NoTrade("no fresh cross above the fast average")
        rng = _range(view.bars, self.p["range_days"])
        return Entry("long", closes[-1] - self.p["stop_ranges"] * rng, None, "crossed back above the fast average")''',
        "exit": '''        closes = [b.c for b in view.bars]
        fast = _avg(closes, self.p["fast_days"])
        if fast is not None and view.bars[-1].t > pos.entry_time and closes[-1] < fast:
            return Exit("closed below the fast average")
        return None''',
    },
    "breakout": {
        "timeframe": "1Day", "sides": ("long", "short", "both"), "style": "breakout", "calm": False,
        "name": "Channel breakout",
        "description": "Buys a close above the highest high of the last 55 days (shorts the mirror image); exits on a 20-day low.",
        "params": {"high_days": 55, "exit_days": 20, "stop_ranges": 2.0, "range_days": 20},
        "rules": ["Long: the close is above the highest high of the previous {high_days} days (short: below the lowest low).",
                  "Enter at that close. Stop: {stop_ranges}x the {range_days}-day average daily range away from the entry.",
                  "Exit a long on a close below the lowest low of the previous {exit_days} days (shorts: above the highest high)."],
        "lookback": "high_days",
        "entry": '''        bars = view.bars
        n = self.p["high_days"]
        if len(bars) <= n:
            return NoTrade("not enough days of history yet")
        hi, lo, c = max(b.h for b in bars[-n - 1:-1]), min(b.l for b in bars[-n - 1:-1]), bars[-1].c
        rng = _range(bars, self.p["range_days"])
        if c > hi and self.sides in ("long", "both"):
            return Entry("long", c - self.p["stop_ranges"] * rng, None, f"closed above the {n}-day high")
        if c < lo and self.sides in ("short", "both"):
            return Entry("short", c + self.p["stop_ranges"] * rng, None, f"closed below the {n}-day low")
        return NoTrade(f"inside the {n}-day channel")''',
        "exit": '''        bars, n = view.bars, self.p["exit_days"]
        if len(bars) <= n or bars[-1].t <= pos.entry_time:
            return None
        if pos.side == "long" and bars[-1].c < min(b.l for b in bars[-n - 1:-1]):
            return Exit("closed below the exit-channel low")
        if pos.side == "short" and bars[-1].c > max(b.h for b in bars[-n - 1:-1]):
            return Exit("closed above the exit-channel high")
        return None''',
    },
    "quiet_breakout": {
        "lines": ['trend_days'],
        "timeframe": "1Day", "sides": ("long",), "style": "breakout", "calm": False, "name": "Quiet-day breakout",
        "description": "After the narrowest day of the last 7, buys a close above that day's high in an uptrend; 2R target.",
        "params": {"quiet_days": 7, "trend_days": 50, "r_multiple": 2.0, "max_hold_days": 5},
        "rules": ["Quiet day: yesterday's high-low range was the narrowest of the last {quiet_days} days.",
                  "Uptrend: the close is above the {trend_days}-day average close.",
                  "Buy when today closes above yesterday's high. Stop: yesterday's low. Target: {r_multiple}R.",
                  "Sell after {max_hold_days} trading days if neither the stop nor the target was hit."],
        "lookback": "trend_days",
        "entry": '''        bars = view.bars
        n = self.p["quiet_days"]
        closes = [b.c for b in bars]
        trend = _avg(closes, self.p["trend_days"])
        if trend is None or len(bars) < n + 1:
            return NoTrade("not enough days of history yet")
        y = bars[-2]
        if (y.h - y.l) > min(b.h - b.l for b in bars[-n - 1:-1]):
            return NoTrade("yesterday wasn't the quietest day")
        if closes[-1] <= trend:
            return NoTrade("not an uptrend")
        if closes[-1] <= y.h:
            return NoTrade("no close above yesterday's high")
        risk = closes[-1] - y.l
        return Entry("long", y.l, closes[-1] + self.p["r_multiple"] * risk, "broke out of a quiet day")''',
        "exit": '''        if sum(1 for b in view.bars if b.t > pos.entry_time) >= self.p["max_hold_days"]:
            return Exit("held long enough")
        return None''',
    },
    "momentum_hold": {
        "lines": ['trend_days', 'exit_avg_days'],
        "timeframe": "1Day", "sides": ("long",), "style": "breakout", "calm": False, "name": "Momentum hold",
        "description": "Buys a new 20-day high when the price is above where it was 126 days ago and above its 200-day average; holds until a close under the 100-day average.",
        "params": {"momentum_days": 126, "trend_days": 200, "high_days": 20, "exit_avg_days": 100, "stop_ranges": 4.0,
                   "range_days": 20},
        "rules": ["Momentum: the close is above the close {momentum_days} trading days ago.",
                  "Uptrend: the close is above the {trend_days}-day average close.",
                  "Buy when the close is the highest close of the last {high_days} days. Stop: {stop_ranges}x the "
                  "{range_days}-day average daily range below the entry.",
                  "Sell when a close falls under the {exit_avg_days}-day average."],
        "lookback": "trend_days",
        "entry": '''        closes = [b.c for b in view.bars]
        m, trend = self.p["momentum_days"], _avg(closes, self.p["trend_days"])
        if trend is None or len(closes) <= m:
            return NoTrade("not enough days of history yet")
        if closes[-1] <= closes[-1 - m]:
            return NoTrade("no momentum: below where it was months ago")
        if closes[-1] <= trend:
            return NoTrade("not an uptrend")
        if closes[-1] < max(closes[-self.p["high_days"]:]):
            return NoTrade("not a new closing high")
        rng = _range(view.bars, self.p["range_days"])
        return Entry("long", closes[-1] - self.p["stop_ranges"] * rng, None, "new closing high with momentum")''',
        "exit": '''        closes = [b.c for b in view.bars]
        avg = _avg(closes, self.p["exit_avg_days"])
        if avg is not None and view.bars[-1].t > pos.entry_time and closes[-1] < avg:
            return Exit("closed under the long average")
        return None''',
    },
    "spike_fade": {
        "lines": ['trend_days', 'exit_avg_days'],
        "timeframe": "1Day", "sides": ("short",), "style": "dip", "calm": False, "name": "Spike fade",
        "description": "Shorts a sharp 2-day pop when the price is below its 200-day average; covers on the drop back.",
        "params": {"trend_days": 200, "rsi_days": 2, "rsi_above": 90, "exit_avg_days": 5, "stop_ranges": 3.0,
                   "range_days": 10, "max_hold_days": 10},
        "rules": ["Downtrend: the close is below the {trend_days}-day average close.",
                  "Pop: the {rsi_days}-day RSI closes over {rsi_above}.",
                  "Short at that close. Stop: {stop_ranges}x the {range_days}-day average daily range above the entry.",
                  "Cover when a close is below the {exit_avg_days}-day average close, or after {max_hold_days} trading days."],
        "lookback": "trend_days",
        "entry": '''        closes = [b.c for b in view.bars]
        trend = _avg(closes, self.p["trend_days"])
        if trend is None:
            return NoTrade("not enough days of history yet")
        if closes[-1] >= trend:
            return NoTrade("above the long average: not a downtrend")
        rsi = _rsi(closes[-60:], self.p["rsi_days"])           # only on trend days: the slow part
        if rsi is None or rsi <= self.p["rsi_above"]:
            return NoTrade("no sharp pop" + (f" (RSI {rsi:.0f})" if rsi is not None else ""))
        rng = _range(view.bars, self.p["range_days"])
        return Entry("short", closes[-1] + self.p["stop_ranges"] * rng, None, f"RSI {rsi:.0f} pop in a downtrend")''',
        "exit": '''        closes = [b.c for b in view.bars]
        avg = _avg(closes, self.p["exit_avg_days"])
        if avg is not None and view.bars[-1].t > pos.entry_time and closes[-1] < avg:
            return Exit("dropped back under the short average")
        if sum(1 for b in view.bars if b.t > pos.entry_time) >= self.p["max_hold_days"]:
            return Exit("held long enough")
        return None''',
    },
    "opening_range": {
        "timeframe": "5Min", "sides": ("long", "short", "both"), "style": "breakout", "calm": False,
        "name": "Opening range break",
        "description": "Trades a break of the first 15 minutes' high or low; stop on the other side, 2R target, out by the close.",
        "params": {"range_minutes": 15, "r_multiple": 2.0, "last_entry_hour": 11},
        "rules": ["Opening range: the high and low of the first {range_minutes} minutes.",
                  "Long when a 5-minute candle closes above the range high (short: below the low), before {last_entry_hour}:00.",
                  "Stop: the other side of the range. Target: {r_multiple}R. Out at the close."],
        "lookback": None,
        "entry": '''        bars = view.bars
        k = self.p["range_minutes"] // 5
        if len(bars) <= k:
            return NoTrade("opening range still forming")
        if view.now.hour >= self.p["last_entry_hour"]:
            return NoTrade("too late in the day for a new entry")
        hi, lo, c = max(b.h for b in bars[:k]), min(b.l for b in bars[:k]), bars[-1].c
        if c > hi and self.sides in ("long", "both"):
            return Entry("long", lo, c + self.p["r_multiple"] * (c - lo), "closed above the opening range")
        if c < lo and self.sides in ("short", "both"):
            return Entry("short", hi, c - self.p["r_multiple"] * (hi - c), "closed below the opening range")
        return NoTrade("inside the opening range")''',
        "exit": '''        return None''',
    },
    "vwap_pullback": {
        "timeframe": "5Min", "sides": ("long", "short", "both"), "style": "dip", "calm": False, "name": "VWAP pullback",
        "description": "After 6 candles in a row above the day's average price (VWAP), buys a dip that touches it and closes back above; 2R target.",
        "params": {"above_bars": 6, "r_multiple": 2.0, "range_bars": 12},
        "rules": ["Trend: the last {above_bars} 5-minute candles closed above the day's VWAP (short: below).",
                  "Entry: a candle dips to the VWAP and closes back above it (short: the mirror image).",
                  "Stop: one average candle range (last {range_bars} candles) below the lower of that candle's low and "
                  "the VWAP (short: above). Target: {r_multiple}R. Out at the close."],
        "lookback": None,
        "entry": '''        bars = view.bars
        n = self.p["above_bars"]
        if len(bars) < n + 2:
            return NoTrade("too early in the day")
        pv = vol = 0.0
        vw = []
        for b in bars:
            pv += (b.h + b.l + b.c) / 3 * b.v; vol += b.v
            vw.append(pv / vol if vol else b.c)
        b, v = bars[-1], vw[-1]
        rng = _range(bars, self.p["range_bars"]) or (b.h - b.l)
        up = all(x.c > w for x, w in zip(bars[-n - 1:-1], vw[-n - 1:-1]))
        down = all(x.c < w for x, w in zip(bars[-n - 1:-1], vw[-n - 1:-1]))
        if up and b.l <= v < b.c and self.sides in ("long", "both"):
            stop = min(b.l, v) - rng
            return Entry("long", stop, b.c + self.p["r_multiple"] * (b.c - stop), "dipped to VWAP in an up day")
        if down and b.h >= v > b.c and self.sides in ("short", "both"):
            stop = max(b.h, v) + rng
            return Entry("short", stop, b.c - self.p["r_multiple"] * (stop - b.c), "popped to VWAP in a down day")
        return NoTrade("no pullback to VWAP in a one-way day")''',
        "exit": '''        return None''',
    },
}

ORDER = {"dip": ["dip_buy", "band_reversion", "spike_fade", "trend_ride", "quiet_breakout", "breakout", "momentum_hold"],
         "breakout": ["breakout", "momentum_hold", "trend_ride", "quiet_breakout", "dip_buy", "band_reversion",
                      "spike_fade"],
         "any": ["dip_buy", "trend_ride", "breakout", "momentum_hold", "band_reversion", "quiet_breakout", "spike_fade"]}
INTRADAY_ORDER = {"dip": ["vwap_pullback", "opening_range"], "breakout": ["opening_range", "vwap_pullback"],
                  "any": ["opening_range", "vwap_pullback"]}


def _fmt(v) -> str:
    return f"{v:g}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)


def _sides(spec: dict, t: dict) -> str | None:
    """The sides a template trades for this goal: the goal's own, or long only when the goal allows both."""
    if spec["sides"] in t["sides"]:
        return spec["sides"]
    if spec["sides"] == "both":
        return "long" if "long" in t["sides"] else "short" if "short" in t["sides"] else None
    return None


def pick(spec: dict, max_candidates: int = MAX_CANDIDATES) -> list[str]:
    """Templates that fit the goal, best fit first."""
    order = (INTRADAY_ORDER if spec["timeframe"] != "1Day" else ORDER)[spec["style"]]
    fits = [k for k in order if _sides(spec, TEMPLATES[k]) and (TEMPLATES[k]["calm"] or not spec["calm"]
                                                                          or spec["style"] == "breakout")]
    return fits[:max(1, min(max_candidates, MAX_CANDIDATES))]


def _indicators(t: dict) -> str:
    """An indicators() method drawing the template's averages on the chart (each value uses past closes only)."""
    keys = t.get("lines") or []
    if not keys:
        return ""
    names = {f"{t['params'][k]}-day avg": k for k in keys}
    return f'''    def indicators(self, bars):
        lines = {names!r}
        closes, out = [], {{n: [] for n in lines}}
        for b in bars:
            closes.append(b.c)
            for n, k in lines.items():
                out[n].append(_avg(closes, self.p[k]))
        return out

'''


def run_label(run_id: str) -> str:
    """'1017193647' -> 'factory run 10-17 19:36:47': a name a person can read, still unique per run."""
    r = run_id
    return f"factory run {r[:2]}-{r[2:4]} {r[4:6]}:{r[6:8]}:{r[8:10]}" if len(r) == 10 and r.isdigit() else f"factory run {r}"


def source(key: str, spec: dict, run_id: str) -> tuple[str, str]:
    """(file slug, Python source) for one candidate bot in the normal bot format."""
    t = TEMPLATES[key]
    name = f"{t['name']} ({run_id})"                    # the bot id (from the name) then matches the file name
    slug = scaffold._slug(f"{t['name']} {run_id}")
    cls = "".join(w.capitalize() for w in slug.split("_"))
    rules = [r.format(**{k: _fmt(v) for k, v in t["params"].items()}) for r in t["rules"]]
    look = t["params"][t["lookback"]] if t["lookback"] else 0
    calm_note = " Picked for a calm goal." if spec["calm"] else ""
    body = f'''"""Strategy factory candidate ({datetime.now().date()}): {t['description']}

Made by BotScope's strategy factory for the goal it was given, from a textbook template with settings that were
never tuned on this data, so every year counts as UNTESTED. Being picked from several candidates tried on the same
years still flatters it a little: paper trade it before trusting it. Not financial advice.
"""
from botscope.bot import Bot, Entry, Exit, NoTrade
{_HELPERS}

class {cls}(Bot):
    name = {name!r}
    version = "1.0"
    description = {t['description']!r}
    rules = {rules!r}
    symbols = {spec['symbols']!r}
    timeframe = {t['timeframe']!r}
    sides = {_sides(spec, t)!r}
    asset = {"crypto" if spec.get("asset") == "crypto" else "swing" if t['timeframe'] == "1Day" else "stock_intraday"!r}
    max_trades_per_day = 1
    flat_by_close = {t['timeframe'] != "1Day"}
    lookback_days = {look}
    params = {t['params']!r}
    tuned_on = None
    status = "untested"
    notes = {("Strategy factory candidate from the " + key + " template." + calm_note)!r}

{_indicators(t)}    def entry(self, view):
{t['entry']}

    def exit(self, view, pos):
{t['exit']}
'''
    return slug, body


def load_file(path: Path) -> type[Bot]:
    spec = importlib.util.spec_from_file_location(f"botscope_factory.{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for _, c in inspect.getmembers(mod, inspect.isclass):
        if issubclass(c, Bot) and c is not Bot and c.__module__ == mod.__name__:
            c.source_file = str(path)
            return c
    raise ValueError(f"{path.name} has no bot class")


# ---------------------------------------------------------------- judging one candidate

def judge(cls, spec: dict, fetch=None) -> dict:
    """Run one candidate through the honest pipeline. Returns {kept, reason | numbers}."""
    chk = scaffold.check_class(cls)
    bad = [c for c in chk["checks"] if not c["pass"]]
    if bad:
        return {"kept": False, "step": "check_bot", "reason": f"failed check_bot: {bad[0]['check']} ({bad[0]['detail']})"}
    cut = holdout_start()
    rep = report.full_report(cls, spec["symbols"], fetch=fetch, crashes=False, save=False, today=cut)
    u, years = rep["untested"], rep["years"]["untested"]
    n = u.get("trades", 0)
    row = {"untested_trades": n, "untested_years": len(years), "avg_r": u.get("avg_r"), "total_r": u.get("total_r"),
           "if_costs_doubled_r": u.get("if_costs_doubled_r"), "without_best_3_r": u.get("without_best_3_r"),
           "range_5_50_95": u.get("total_r_range_5_50_95"), "worst_losing_streak": u.get("worst_losing_streak"),
           "max_drawdown_r": u.get("max_drawdown_r"), "losing_years": rep["losing_untested_years"],
           "vs_spy": rep.get("vs_spy", {}).get("summary"), "years_beat_spy": rep.get("vs_spy", {}).get("years_beat"),
           "_entries": rep.get("untested_entries", [])}
    drop = None
    if n < 30:
        drop = f"only {n} trades on {len(years)} untested years (needs 30+ to judge at all)"
    elif u["avg_r"] <= 0:
        drop = f"lost money on untested years after costs ({u['avg_r']:+.2f}R a trade over {n} trades)"
    elif (u.get("if_costs_doubled_r") or 0) <= 0:
        drop = (f"made {u['total_r']:+.1f}R, but with trading costs doubled it's {u['if_costs_doubled_r']:+.1f}R: "
                "the edge is thinner than the costs")
    elif (u.get("without_best_3_r") or 0) <= 0:
        drop = f"rests on a few lucky trades: without its 3 best it's {u['without_best_3_r']:+.1f}R"
    elif report.tight_stops(u):
        drop = f"R can't be trusted: {report.tight_stops(u)}"
    elif len(rep["losing_untested_years"]) * 2 > len(years):
        drop = f"lost money in {len(rep['losing_untested_years'])} of {len(years)} untested years"
    elif spec["calm"] and (u.get("max_drawdown_r") or 0) < -CALM_MAX_DROP_R:
        drop = f"not calm: its deepest drop was {u['max_drawdown_r']:.1f}R (the calm limit is {CALM_MAX_DROP_R:g}R)"
    elif spec["calm"] and (u.get("worst_losing_streak") or 0) > CALM_MAX_STREAK:
        drop = f"not calm: {u['worst_losing_streak']} losses in a row (the calm limit is {CALM_MAX_STREAK})"
    if not drop:
        drop = later_half_check(rep, row)
    if not drop and spec.get("busy") and len(years):
        kind, limit = spec["busy"]
        per_year = n / len(years)
        if kind == "active" and per_year < limit:
            drop = f"not active enough: {per_year:.0f} trades a year (the active goal wants {limit}+)"
        elif kind == "hands-off" and per_year > limit:
            drop = f"too busy for hands-off: {per_year:.0f} trades a year (the goal allows {limit})"
    if drop:
        return {"kept": False, "step": "honest report", "reason": drop, **row}
    drop = neighbors_check(cls, spec, fetch, row)
    if drop:
        return {"kept": False, "step": "settings ±20%", "reason": drop, **row}
    lk = luck.luck_meter(cls, spec["symbols"], years=True, fetch=fetch, twins=LUCK_TWINS, shuffles=LUCK_SHUFFLES,
                         save=False, today=cut)
    row["luck"] = lk.get("level")
    row["luck_detail"] = (lk.get("why") or [""])[0]
    if lk.get("level") == "looks like luck":
        return {"kept": False, "step": "luck meter", "reason": f"looks like luck: {row['luck_detail']}", **row}
    conf = confidence.meter(u)
    step, why = conf["step"], list(conf["why"])
    if lk.get("level") == "unclear" and step > 0:
        step -= 1
        why.append("luck meter unclear: down one level")
    row["held_out"] = held_out(cls, spec, fetch, cut)
    row["confidence"] = confidence.LEVELS[step]
    row["confidence_step"] = step
    row["confidence_why"] = why
    return {"kept": True, "step": "survived", **row}


def holdout_start(today: date | None = None) -> date:
    """First day of the held-out year. Reports judged without it end the day before (year_windows' `today`)."""
    return (today or date.today()) - timedelta(days=HOLDOUT_DAYS)


def held_out(cls, spec: dict, fetch, cut: date) -> dict:
    """The survivor on the last year, which no keep/drop decision saw: the closest thing to a fresh test."""
    bot = cls()
    end = date.today() - timedelta(days=1)
    if bot.timeframe != "1Day":                         # intraday: the last full month only, to stay light
        end_m = end.replace(day=1) - timedelta(days=1)
        a, b = end_m.replace(day=1), end_m
    else:
        a, b = cut, end
    trades, _, _ = backtest.run_window(bot, spec["symbols"], a, b, fetch=fetch,
                                       warmup_days=backtest.warmup_days(bot, report.DAILY_WARMUP))
    s = backtest.summarize(trades, 10_000)
    return {"from": str(a), "to": str(b), "trades": s.get("trades", 0), "avg_r": s.get("avg_r"),
            "total_r": s.get("total_r"),
            "note": ("held out: no keep/drop decision used these days. One year (or month) is noisy: a loss here is a "
                     "warning, a gain is not proof")}


def later_half_check(rep: dict, row: dict) -> str | None:
    """Did it still make money in the later half of the untested years? An edge that only worked long ago is a
    warning: markets change, and the later years are the closest to now."""
    ys = [y for y in rep["by_year"] if y["period"] == "untested" and y["trades"]]
    if len(ys) < 4:
        return None
    half = len(ys) // 2
    early, late = (round(sum(y["total_r"] or 0 for y in part), 2) for part in (ys[:half], ys[half:]))
    row["halves_r"] = {"early": early, "late": late, "split_year": ys[half]["year"]}
    if late <= 0 < early:
        return (f"made money only in the earlier years: {early:+.1f}R up to {ys[half - 1]['year']}, "
                f"{late:+.1f}R from {ys[half]['year']} on")
    return None


def nudged(cls, factor: float):
    """The same bot with every number setting moved by `factor` (whole numbers stay whole, at least 1)."""
    p = {k: (max(1, round(v * factor)) if isinstance(v, int) else round(v * factor, 3))
         if isinstance(v, (int, float)) and not isinstance(v, bool) else v for k, v in cls.params.items()}
    look = -(-cls.lookback_days * max(factor, 1.0) // 1) if cls.lookback_days else 0
    return type(cls.__name__, (cls,), {"params": p, "lookback_days": int(look), "source_file": cls.source_file})


def neighbors_check(cls, spec: dict, fetch, row: dict) -> str | None:
    """Knife-edge test: run it again with every setting 20% smaller and 20% bigger. Real edges don't vanish when a
    setting moves a little; settings that only work at one exact value were probably found by luck."""
    out = {}
    for label, f in (("20% smaller", 0.8), ("20% bigger", 1.2)):
        u = report.full_report(nudged(cls, f), spec["symbols"], fetch=fetch, crashes=False, save=False,
                               today=holdout_start())["untested"]
        out[label] = {"trades": u.get("trades", 0), "avg_r": u.get("avg_r"), "total_r": u.get("total_r")}
    row["settings_nudged"] = out
    for label, u in out.items():
        if not u["trades"] or (u["avg_r"] or 0) <= 0:
            return (f"knife-edge settings: with every setting {label} it "
                    + ((f"lost money ({_r(u['avg_r'])} a trade over {u['trades']} trades)" if (u["avg_r"] or 0) < -0.005
                        else f"made nothing ({_r(u['avg_r'])} a trade over {u['trades']} trades)")
                       if u["trades"] else "never traded"))
    return None


# ---------------------------------------------------------------- one factory run

def _r(x) -> str:
    if x is None:
        return "–"
    if abs(x) < 0.005:
        return "0.00R"                                  # never "-0.00R" or "+0.00R"
    return f"{x:+.2f}R" if abs(x) < 10 else f"{x:+.1f}R"


LEARN = [("R can't be trusted", "docs/when-r-lies-tight-stops.md"), ("costs doubled", "docs/what-costs-do-to-small-edges.md"), ("trades on", "docs/how-many-trades-before-you-know.md"),
         ("lucky trades", "docs/how-many-trades-before-you-know.md"),     # before "luck": it contains the word
         ("only in the earlier years", "docs/why-the-factory-holds-out-a-year.md"),
         ("knife-edge", "docs/why-the-factory-holds-out-a-year.md"), ("luck", "docs/why-the-best-setting-looks-better.md")]


def learn_more(reason: str) -> str | None:
    """The research note that explains a drop reason in plain words, if there is one."""
    return next((doc for words, doc in LEARN if words in reason), None)


def _nudge(k: dict) -> str:
    n = k.get("settings_nudged") or {}
    return " / ".join(_r(n[x]["avg_r"]) for x in ("20% smaller", "20% bigger") if x in n) + " a trade" if n else "–"


def _held(k: dict) -> str:
    h = k.get("held_out") or {}
    if not h:
        return "–"
    return f"{h['trades']} trades, {_r(h['avg_r'])} each" if h["trades"] else "no trades"


def hindsight_note(symbols: list[str]) -> str | None:
    """Single stocks picked today flatter any test over past years (they're on the list because they did well)."""
    picked = [s for s in symbols if s not in ETFS + ["SPY", "QQQ"]]
    if not picked:
        return None
    return (f"Hindsight: {', '.join(picked)} {'is' if len(picked) == 1 else 'are'} on the list because of how "
            "they did, which flatters every candidate over past years (docs/hindsight-in-the-symbol-list.md). "
            "Try the same goal on index ETFs to compare.")


def markdown(spec: dict, kept: list[dict], dropped: list[dict], tried: int, demo: bool, run_id: str = "") -> str:
    lines = [("**DEMO DATA** (made-up prices: these results mean nothing about real markets)\n\n" if demo else "")
             + (f"_{spec['caution']}_\n\n" if spec.get("caution") else "")
             + f"Goal read as: {spec['read_as']}. Tried {tried} candidate(s); all years are UNTESTED "
               f"(textbook settings, never tuned here). Keep/drop decisions leave out the last year; survivors "
               f"show it as the held-out year."
             + (f" The number after each name is the run: {run_label(run_id)}." if run_id else "")]
    if kept:
        lines += ["", "| # | Candidate | Confidence | Untested trades | Per trade after costs | Costs doubled | "
                      "Without best 3 | Settings ±20% | Luck | vs holding SPY | Held-out year |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        for i, k in enumerate(kept, 1):
            lines.append(f"| {i} | {k['name']} | {k['confidence']} | {k['untested_trades']} | {_r(k['avg_r'])} | "
                         f"{_r(k['if_costs_doubled_r'])} | {_r(k['without_best_3_r'])} | {_nudge(k)} | {k['luck']} | "
                         f"{k['years_beat_spy'] if k['years_beat_spy'] is not None else '–'} of {k['untested_years']} years | "
                         f"{_held(k)} |")
    else:
        lines += ["", "**No candidate survived.** That's a real answer: none of these simple ideas held up honestly "
                      "for this goal."]
    if kept and (h := hindsight_note(spec["symbols"])):
        lines += ["", h]
    if dropped:
        lines += ["", "| Dropped | Why |", "|---|---|"] + [
            f"| {d['name']} | {d['reason']}" + (f" ([why this matters]({d['learn']}))" if d.get("learn") else "") + " |"
            for d in dropped]
    return "\n".join(lines)


def run(goal: str, symbols: list[str] | None = None, max_candidates: int = MAX_CANDIDATES, fetch=None,
        demo: bool | None = None, research: bool = False) -> dict:
    """research=True: your own Claude Code researches and writes the 5 candidates (factory_research); when it can't
    run, the templates are used and the run says why. Either way every candidate gets the same honest pipeline."""
    if demo is None:
        from .env import demo_mode
        demo = demo_mode()
    if not goal.strip():
        raise ValueError("describe the bot you want in a sentence, e.g. 'a calm daily ETF bot'")
    spec = understand(goal, symbols)
    keys = pick(spec, max_candidates)
    if not keys and not research:
        raise ValueError(f"no template fits {spec['read_as']}; try 'long and short' or another style")
    run_id = datetime.now().strftime("%m%d%H%M%S")
    folder = factory_dir() / run_id
    folder.mkdir(parents=True, exist_ok=True)
    cands, researched = None, None
    if research:
        from . import factory_research
        PROGRESS.clear(); PROGRESS.update(goal=goal, phase="research", done=0, total=factory_research.COUNT, kept=0)
        try:
            cands = factory_research.research(goal, spec, run_id, folder, PROGRESS)
            ok = sum(not c.get("refused") for c in cands)
            researched = {"used": True, "note": (
                f"Researched by your own Claude Code: {len(cands)} published ideas, each with its source"
                + (f" ({len(cands) - ok} refused before testing)" if ok < len(cands) else "")
                + ". Research only picks the ideas: famous strategies are famous because they looked good on past "
                  "data, so the same honest tests decide.")}
        except factory_research.Unavailable as e:
            researched = {"used": False, "note": f"Research didn't run ({e}), so this run used BotScope's built-in "
                                                 "textbook templates instead."}
            if not keys:
                PROGRESS.clear()
                raise ValueError(f"{researched['note']} No template fits {spec['read_as']} either.") from e
    if cands is None:
        cands = []
        for key in keys:
            slug, src = source(key, spec, run_id)
            (folder / f"{slug}.py").write_text(src)
            cands.append({"slug": slug, "path": folder / f"{slug}.py", "label": TEMPLATES[key]["name"],
                          "template": key, "source": "BotScope's built-in textbook template"})
    kept, dropped = [], []
    for i, c in enumerate(cands):                       # one candidate at a time
        PROGRESS.clear(); PROGRESS.update(goal=goal, phase="testing", done=i, total=len(cands), now=c["label"],
                                          kept=len(kept))
        cls = None
        if c.get("refused"):                             # never loaded: its file was refused before running
            res = {"kept": False, "step": "safety check", "reason": f"refused before testing: {c['refused']}"}
        else:
            try:
                cls = load_file(c["path"])
                res = judge(cls, spec, fetch)
            except Exception as e:                       # a broken candidate is a dropped candidate, never a crash
                res = {"kept": False, "step": "loading", "reason": f"crashed: {type(e).__name__}: {str(e)[:120]}"}
        res |= {"name": cls.name if cls else c["label"], "template": c.get("template"),
                "file": str(c["path"]) if c.get("path") else None, "id": c["slug"],
                "rules": list(cls.rules) if cls else [], "learn": learn_more(res.get("reason", "")),
                "idea": c.get("idea"), "idea_source": c.get("source"), "why_it_fits": c.get("why")}
        (kept if res.pop("kept") else dropped).append(res)
    keys = cands                                       # what was tried, for the counts below
    PROGRESS.clear()
    before, runs = tried_before(spec)
    total = before + len(keys)
    if total >= MANY_TRIES:                             # many candidates on the same years: any survivor could be luck
        for k in kept:
            if k["confidence_step"] > 0:
                k["confidence_step"] -= 1
                k["confidence"] = confidence.LEVELS[k["confidence_step"]]
                k["confidence_why"].append(f"{total} candidates tried on these years across {runs + 1} factory runs: "
                                           "down one level")
    kept.sort(key=lambda k: (-k["confidence_step"], -((k["if_costs_doubled_r"] or 0) / max(k["untested_trades"], 1))))
    overlaps = same_bets(kept)
    for r in kept + dropped:
        r.pop("_entries", None)
    md = markdown(spec, kept, dropped, len(keys), demo, run_id)
    if researched:
        md = f"_{researched['note']}_\n\n" + md
    if researched and researched["used"]:
        cell = lambda s: str(s or "–").replace("|", "/")     # noqa: E731
        md += "\n\n| Candidate | Idea | Source of the idea |\n|---|---|---|\n" + "\n".join(
            f"| {cell(r['name'])} | {cell(r.get('idea'))} | {cell(r.get('idea_source'))} |" for r in kept + dropped)
    if overlaps:
        md = md.replace("\n\n| Dropped |", "\n\n" + "\n".join(f"Same bet? {o}" for o in overlaps) + "\n\n| Dropped |", 1) \
            if "| Dropped |" in md else md + "\n\n" + "\n".join(f"Same bet? {o}" for o in overlaps)
    if not kept and (miss := closest_miss(dropped)):
        md = md.replace("for this goal.", "for this goal. " + miss, 1)
    out = {"goal": goal, "run": run_id, "understood": spec, "tried": len(keys), "kept": kept, "dropped": dropped,
           "same_bets": overlaps, "research": researched,
           "data": "DEMO DATA (made-up prices)" if demo else "Alpaca SIP (all US exchanges), your own keys",
           "period": ("all UNTESTED years since 2016 (candidates use textbook settings, never tuned here); keep/drop "
                      f"decisions use the years up to {holdout_start()}, and the year after that is HELD OUT, shown "
                      "for survivors only"),
           "markdown": md, "folder": str(folder),
           "tries_note": ((f"{total} candidates have now been tried on these symbols' untested years across "
                           f"{runs + 1} factory runs: the more you try, the more a survivor can be luck"
                           + (" (survivors are down one confidence level for it)" if total >= MANY_TRIES else "")
                           + ". Paper trade a survivor before trusting it.") if before else
                          (f"{len(keys)} candidates were tried on the same untested years, so the top one looks a bit "
                           "better than it is. Paper trade a survivor before trusting it.")),
           "next": (f"adopt_candidate(run, id) copies a survivor into your bots folder (checkpoint first), e.g. "
                    f"`botscope adopt_candidate {run_id} {kept[0]['id']}` for {kept[0]['name']}; then "
                    "open_bot_view, nutrition_label and paper trading." if kept else
                    "Try a different goal (another style, timeframe or symbols), or keep your money in something simple."),
           "note": "Ranked by confidence level, not by profit. Counts, not probabilities. Not financial advice."}
    out["report_file"] = str(write_report(folder, goal, out, demo))
    journal.add("factory_runs", {"goal": goal, "run": run_id, "when": datetime.now().isoformat(timespec="seconds"),
                                 "demo": demo, "understood": spec["read_as"], "tried": len(keys),
                                 "symbols": sorted(spec["symbols"]), "timeframe": spec["timeframe"],
                                 "kept": kept, "dropped": dropped, "markdown": md,
                                 "hindsight": hindsight_note(spec["symbols"]) if kept else None,
                                 "tries_note": out["tries_note"], "same_bets": overlaps, "research": researched})
    return out


MANY_TRIES = 15          # candidates tried on the same symbols' years before survivors drop one confidence level


def tried_before(spec: dict) -> tuple[int, int]:
    """(candidates, runs) from earlier factory runs on the same symbols and candle size: every rerun with a tweaked
    goal is more chances for a lucky survivor on the same years."""
    same = [r for r in journal.load("factory_runs")
            if r.get("symbols") == sorted(spec["symbols"]) and r.get("timeframe") == spec["timeframe"]]
    return sum(r.get("tried", 0) for r in same), len(same)


SAME_BET = 0.5          # share of the smaller survivor's entries on the same symbol and day


def same_bets(kept: list[dict]) -> list[str]:
    """Pairs of survivors that mostly enter the same symbol on the same day: running both is mostly one bet twice."""
    out = []
    for i, a in enumerate(kept):
        for b in kept[i + 1:]:
            ea, eb = set(map(tuple, a.get("_entries") or [])), set(map(tuple, b.get("_entries") or []))
            if not ea or not eb:
                continue
            share = len(ea & eb) / min(len(ea), len(eb))
            if share >= SAME_BET:
                out.append(f"{a['name']} and {b['name']} entered the same symbol on the same day in "
                           f"{len(ea & eb)} of {min(len(ea), len(eb))} trades: running both is mostly one bet twice.")
    return out


def closest_miss(dropped: list[dict]) -> str | None:
    """When nothing survived: the dropped candidate that did best on untested years, and what stopped it."""
    tested = [d for d in dropped if d.get("avg_r") is not None and d.get("untested_trades", 0) >= 30]
    if not tested:
        return None
    d = max(tested, key=lambda x: x["avg_r"])
    tip = (" Without 'calm' in the goal that limit wouldn't apply, but every other check still would."
           if d["reason"].startswith("not calm") else
           " Without that word in the goal the trade-count limit wouldn't apply." if "trades a year" in d["reason"] else "")
    return f"Closest miss: {d['name']} ({d['avg_r']:+.2f}R a trade over {d['untested_trades']}): {d['reason']}.{tip}"


def write_report(folder: Path, goal: str, out: dict, demo: bool) -> Path:
    """REPORT.md next to the candidate files: the whole run on one page, to keep or share (no keys, no account)."""
    p = folder / "REPORT.md"
    p.write_text(f"# Strategy factory: {goal}\n\n"
                 + f"Run {out['run']}, {datetime.now():%Y-%m-%d %H:%M}. Data: {out['data']}. Period: {out['period']}.\n\n"
                 + out["markdown"] + "\n\n" + out["tries_note"] + "\n\n"
                 + "Paper trading only. Past results, even honest ones, don't predict the future. Not financial advice.\n")
    return p


def history(limit: int = 10) -> dict:
    """Past factory runs (newest first) and how many candidates each symbol set has seen in all."""
    runs = journal.load("factory_runs")
    by_set: dict[str, dict] = {}
    for r in runs:
        if r.get("symbols"):
            k = f"{', '.join(r['symbols'])} ({r.get('timeframe')})"
            by_set.setdefault(k, {"symbols": k, "runs": 0, "candidates": 0})
            by_set[k]["runs"] += 1; by_set[k]["candidates"] += r.get("tried", 0)
    return {"runs": [{"run": r["run"], "when": r.get("when"), "goal": r["goal"], "demo": r.get("demo", False),
                      "tried": r.get("tried"), "survivors": [k["name"] for k in r.get("kept", [])],
                      "dropped": len(r.get("dropped", []))} for r in reversed(runs[-limit:])],
            "tries_by_symbols": sorted(by_set.values(), key=lambda x: -x["candidates"]),
            "note": "Every candidate tried on the same symbols' years is one more chance for a lucky survivor."}


def robustness(cls, symbols: list[str] | None = None, fetch=None, save: bool = False) -> dict:
    """The factory's whole checklist on any bot (yours too), every check shown pass/fail instead of stopping at the
    first. Same rules: decisions leave out the last year, which is then shown as the held-out year."""
    spec = {"symbols": [s.upper() for s in (symbols or cls.symbols)][:backtest.MAX_SYMBOLS], "calm": False, "busy": None}
    rows = []
    add = lambda check, ok, detail: rows.append({"check": check, "pass": bool(ok), "detail": detail})  # noqa: E731
    chk = scaffold.check_class(cls)
    bad = [c for c in chk["checks"] if not c["pass"]]
    add("check_bot", not bad, "all checks pass" if not bad else f"{bad[0]['check']}: {bad[0]['detail']}")
    cut = holdout_start()
    rep = report.full_report(cls, spec["symbols"], fetch=fetch, crashes=False, save=False, today=cut)
    u, years = rep["untested"], rep["years"]["untested"]
    n = u.get("trades", 0)
    add("30+ untested trades", n >= 30, f"{n} trades on {len(years)} untested years (up to {cut})")
    if n:
        add("makes money after costs", (u["avg_r"] or 0) > 0, f"{u['avg_r']:+.2f}R a trade, {u['total_r']:+.1f}R total")
        add("survives doubled costs", (u.get("if_costs_doubled_r") or 0) > 0, f"{_r(u.get('if_costs_doubled_r'))} with costs doubled")
        add("not a few lucky trades", (u.get("without_best_3_r") or 0) > 0, f"{_r(u.get('without_best_3_r'))} without its 3 best")
        add("stops wider than costs", not report.tight_stops(u),
            report.tight_stops(u) or f"{u.get('tight_stop_trades', 0)} of {n} trades had a stop closer than their costs")
        lose = rep["losing_untested_years"]
        add("wins most untested years", len(lose) * 2 <= len(years), f"lost money in {len(lose)} of {len(years)}")
        faded = later_half_check(rep, row := {})
        h = row.get("halves_r")
        add("still works in the later years", not faded and (not h or h["late"] > 0),
            faded or (f"{h['early']:+.1f}R before {h['split_year']}, {h['late']:+.1f}R from {h['split_year']} on" if h else
                      "too few years to split"))
    if cls.params:
        knife = neighbors_check(cls, spec, fetch, nrow := {})
        nd = nrow.get("settings_nudged", {})
        add("settings ±20% still work", not knife,
            knife or " / ".join(f"{k}: {_r(v['avg_r'])} a trade" for k, v in nd.items()))
    else:
        add("settings ±20% still work", True, "no number settings to move")
    if n >= 10:
        lk = luck.luck_meter(cls, spec["symbols"], years=True, fetch=fetch, twins=LUCK_TWINS, shuffles=LUCK_SHUFFLES,
                             save=False, today=cut)
        add("beats luck", lk.get("level") != "looks like luck", f"{lk.get('level')}: {(lk.get('why') or [''])[0]}")
    ho = held_out(cls, spec, fetch, cut)
    passed = sum(r["pass"] for r in rows)
    failed = [r["check"] for r in rows if not r["pass"]]
    if save:                                          # the nutrition label shows the last one
        journal.upsert("robustness", {"bot": loader.bot_id(cls)},
                       {"passed": f"{passed} of {len(rows)}", "failed": failed, "held_out": ho,
                        "bot_file_hash": report.fingerprint(cls)})
    return {"bot": cls.name, "symbols": spec["symbols"], "checks": rows, "passed": f"{passed} of {len(rows)}",
            "held_out": ho,
            "period": f"UNTESTED years up to {cut}; the year after that is held out and shown on its own",
            "note": ("Each failed check is a reason for caution, not a verdict on its own. A bot tuned on some years "
                     "(tuned_on) is judged on its other years only. Not financial advice.")}


def adopt(run_id: str, candidate: str) -> dict:
    """Copy one candidate from a factory run into the user's bots folder, after a checkpoint."""
    folder = factory_dir() / re.sub(r"[^0-9]", "", run_id)
    hits = [p for p in folder.glob("*.py") if candidate.lower().replace(" ", "_") in p.stem]
    if len(hits) != 1:
        raise ValueError(f"no single candidate {candidate!r} in run {run_id}; have: "
                         + ", ".join(p.stem for p in folder.glob("*.py")) if folder.exists() else f"no run {run_id}")
    dest = loader.bots_dir() / hits[0].name
    if dest.exists():
        raise ValueError(f"{dest.name} is already in your bots folder")
    cp = checkpoints.save(f"before adopt_candidate {hits[0].stem}")
    shutil.copy(hits[0], dest)
    return {"file": str(dest), "bot_id": loader.bot_id(load_file(dest)), "checkpoint_before": cp["id"],
            "next": "It's untested on paper: run nutrition_label, open_bot_view, and let it paper trade before trusting it."}
