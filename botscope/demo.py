"""Demo data: made-up prices BotScope generates on this computer, so every tool and page works with zero keys.

Nothing here comes from a data vendor: the prices are a seeded random walk (same symbol + day = same bars every
time), with an upward drift, calm and stormy stretches, and a small bounce-back after big days so the example bots
have something to do. They are NOT real prices, and results on them mean nothing about real markets. Every result
made from them says "DEMO DATA".
"""
from __future__ import annotations

import hashlib
import math
import random
import re
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from .bot import BarData

ET = ZoneInfo("America/New_York")
BADGE = "DEMO DATA"
SOURCE = "DEMO DATA: made-up prices generated on this computer (not real, results mean nothing)"
START = date(2016, 1, 4)
_START_PX = {"BTC/USD": 430.0, "ETH/USD": 8.0, "SPY": 200.0, "QQQ": 105.0, "IWM": 110.0, "DIA": 170.0, "AAPL": 26.0, "MSFT": 54.0, "NVDA": 8.0,
             "AMZN": 32.0, "GOOGL": 37.0, "META": 100.0, "TSLA": 15.0}
_STEP = {"1Min": 1, "5Min": 5, "15Min": 15, "30Min": 30, "1Hour": 60}


NEEDS_REAL_DATA = {"movers", "news", "fed", "yields", "econ", "short", "analysts", "insiders", "options", "calendar",
                   "keydates"}
HOW_TO_SWITCH = ("To switch to real data: open Studio's Get started tab, which walks you through free Alpaca PAPER "
                 "keys in about 2 minutes (or put ALPACA_API_KEY and ALPACA_SECRET_KEY in ~/.botscope/.env yourself). "
                 "Run doctor to check.")


def active() -> bool:
    from .env import demo_mode
    return demo_mode()


def needs_real_data(what: str) -> dict:
    """What a tool or panel that only has real-world data (news, calendars, live quotes) says in demo mode."""
    return {"data_badge": BADGE, "demo": f"{what}: needs real data, so there's nothing to show in demo mode. "
                                         + HOW_TO_SWITCH,
            "error": "needs real data: demo mode has no keys yet (doctor says how to add free ones)"}


def label(out):
    """Stamp a tool or panel result made in demo mode: a DEMO DATA badge, and data/source lines that name the demo."""
    if not active() or not isinstance(out, dict):
        return out
    err = str(out.get("error", ""))
    if err and any(w in err.lower() for w in ("key", "missing", "alpaca", "credential", "unauthorized", "forbidden")):
        return needs_real_data("this tool") | {"error_was": err[:160]}
    real_crypto = lambda v: "crypto" in v.lower() and "real past prices" in v.lower()     # noqa: E731
    out = {k: (SOURCE if k in ("data", "source") and isinstance(v, str) and "alpaca" in v.lower() and not real_crypto(v)
               else _no_sip(v)) for k, v in out.items()}
    return {"data_badge": BADGE, **out, "demo_note": "Demo mode: stock prices are made up (results on them mean nothing "
                                                     "about real markets); crypto uses real past prices when online. "
                                                     + HOW_TO_SWITCH}


def _no_sip(v):
    """Source lines built for real data ("SPY daily closes (Alpaca SIP)") name the demo prices instead, at any depth."""
    if isinstance(v, str):
        if "Alpaca SIP" not in v:
            return v
        v = re.sub(r"Alpaca SIP( bars)?( \(all US exchanges\))?", "DEMO DATA (made-up prices)", v)
        return re.sub(r",? (downloaded )?with your own keys|, your own keys| \(your own keys\)", "", v)
    if isinstance(v, list):
        return [_no_sip(x) for x in v]
    if isinstance(v, dict):
        return {k: _no_sip(x) for k, x in v.items()}
    return v


def fill_paper_days(n: int = 20) -> dict:
    """Demo only: let the example bots 'paper trade' the last n made-up weekdays (the normal end-of-day log, no phone
    alert), so the confidence meter, drift alarm, graduation test and My bots have something to show. Lands in the
    demo journal only, and only once."""
    from . import daily_log, journal
    if not active():
        raise RuntimeError("demo paper days only run in demo mode")
    mark = journal.folder() / "demo_paper_days.done"
    if mark.exists() or journal.load("paper_results"):
        return {"skipped": "the demo journal already has paper days"}
    days, d = [], date.today() - timedelta(days=1)
    while len(days) < n:
        if _trading_day(d):
            days.append(d)
        d -= timedelta(days=1)
    new = sum(daily_log.run(x, notify=False)["new_results"] for x in reversed(days))
    mark.parent.mkdir(parents=True, exist_ok=True)
    mark.write_text(f"{days[-1]} to {days[0]}\n")
    return {"days": n, "from": str(days[-1]), "to": str(days[0]), "paper_results": new}


def _seed(*parts) -> int:
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:8], "big")


def _crypto(symbol: str) -> bool:
    return "/" in symbol


def _trading_day(d: date, symbol: str = "") -> bool:
    if _crypto(symbol):
        return True
    return d.weekday() < 5 and not (d.month == 1 and d.day == 1) and not (d.month == 12 and d.day == 25) \
        and not (d.month == 7 and d.day == 4)


@lru_cache(maxsize=64)
def _daily(symbol: str, end: date) -> tuple[tuple, ...]:
    """(day, open, high, low, close, volume) for every demo trading day from 2016 to `end`, always the same path."""
    rng = random.Random(_seed("daily", symbol))
    px = _START_PX.get(symbol, 20.0 + rng.random() * 180)
    beta = 1.0 if symbol in ("SPY", "DIA") else 1.3 if symbol in ("QQQ", "IWM") else 1.6
    vol, prev_ret, out, d = 0.010 * beta, 0.0, [], START
    while d <= end:
        if _trading_day(d, symbol):
            vol = max(0.004, min(0.035, vol * math.exp(rng.gauss(0, 0.08)) * 0.98 + 0.0002 * beta))  # calm/stormy spells
            ret = 0.0003 * beta - 0.08 * prev_ret + rng.gauss(0, vol)                               # drift + small bounce-back
            o = px * (1 + rng.gauss(0, vol * 0.3))
            c = px * (1 + ret)
            h = max(o, c) * (1 + abs(rng.gauss(0, vol * 0.5)))
            lo = min(o, c) * (1 - abs(rng.gauss(0, vol * 0.5)))
            out.append((d, round(o, 2), round(h, 2), round(lo, 2), round(c, 2), int(1e6 * (1 + rng.random()))))
            px, prev_ret = c, ret
        d += timedelta(days=1)
    return tuple(out)


@lru_cache(maxsize=16)
def _by_day(symbol: str) -> dict:
    return {r[0]: r for r in _daily(symbol, date.today())}


@lru_cache(maxsize=512)
def _minutes(symbol: str, day: date) -> tuple[tuple, ...]:
    """390 one-minute bars for one demo day: a wobbly path from the day's open to its close."""
    rows = _by_day(symbol)
    if day not in rows:
        return ()
    _, o, h, lo, c, v = rows[day]
    rng = random.Random(_seed("minute", symbol, day))
    n, sd = (1440 if _crypto(symbol) else 390), max((h - lo) / max(o, 1e-9), 0.002) / 8
    walk, x = [0.0], 0.0
    for _ in range(n):
        x += rng.gauss(0, sd)
        walk.append(x)
    path = [o * math.exp(walk[i] - walk[-1] * i / n) * (c / o) ** (i / n) for i in range(n + 1)]   # bridge: o -> c
    t0 = datetime.combine(day, time(0), ZoneInfo("UTC")) if _crypto(symbol) else datetime.combine(day, time(9, 30), ET)
    out = []
    for i in range(n):
        a, b = path[i], path[i + 1]
        wig = abs(rng.gauss(0, sd * 0.5)) * a
        out.append((t0 + timedelta(minutes=i), round(a, 2), round(max(a, b) + wig, 2), round(min(a, b) - wig, 2),
                    round(b, 2), int(v / n * (1.5 if not _crypto(symbol) and (i < 30 or i > 360) else 1) * (0.5 + rng.random()))))
    return tuple(out)


def _group(rows, step: int) -> list[BarData]:
    out = []
    for i in range(0, len(rows), step):
        g = rows[i:i + step]
        out.append(BarData(g[0][0], g[0][1], max(r[2] for r in g), min(r[3] for r in g), g[-1][4], sum(r[5] for r in g)))
    return out


def bars(symbol: str, start: date, end: date, timeframe: str = "1Min", feed: str = "demo") -> list[BarData]:
    """Same call shape as data.bars, so any tool can use it as its `fetch`."""
    symbol = symbol.upper()
    end = min(end, date.today())
    if timeframe == "1Day":
        return [BarData(datetime.combine(d, time(0), ET), o, h, lo, c, v)
                for d, o, h, lo, c, v in _daily(symbol, date.today()) if start <= d <= end]
    step = _STEP.get(timeframe)
    if step is None:
        raise ValueError(f"demo data has no {timeframe} bars")
    out, d = [], max(start, START)
    while d <= end:
        if _trading_day(d, symbol):
            out += _group(_minutes(symbol, d), step)
        d += timedelta(days=1)
    return out
