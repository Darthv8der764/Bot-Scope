"""Price bars from Alpaca with the user's own keys. Default feed: SIP (all US exchanges; free for history older than
15 minutes). Downloaded bars are cached on this computer only (data/cache, gitignored) and never redistributed."""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .bot import BarData
from . import demo
from .env import ROOT, alpaca_keys, demo_mode
from .userdata import place

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
CACHE = Path(os.getenv("BOTSCOPE_CACHE") or place(ROOT / "data" / "cache", "cache"))
_TF = {"1Min": (1, "Minute"), "5Min": (5, "Minute"), "15Min": (15, "Minute"), "30Min": (30, "Minute"), "1Hour": (1, "Hour"), "1Day": (1, "Day")}


def is_crypto(symbol: str) -> bool:
    """Crypto pairs are written with a slash (BTC/USD): they trade 24/7."""
    return "/" in symbol


def _fetch_crypto(symbol: str, start: date, end: date, timeframe: str) -> list[list]:
    from alpaca.data.historical import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    n, unit = _TF[timeframe]
    client = CryptoHistoricalDataClient()             # Alpaca's crypto history needs no keys
    req = CryptoBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame(n, TimeFrameUnit[unit]),
                            start=datetime.combine(start, time(0), UTC), end=datetime.combine(end, time(23, 59), UTC))
    rows = client.get_crypto_bars(req).data.get(symbol, [])
    return [[b.timestamp.isoformat(), b.open, b.high, b.low, b.close, b.volume] for b in rows]


def _fetch(symbol: str, start: date, end: date, timeframe: str, feed: str) -> list[list]:
    if is_crypto(symbol):
        from . import brokers
        if brokers.crypto_source() != "alpaca":           # another data adapter (BOTSCOPE_CRYPTO_DATA)
            return [[b.t.isoformat(), b.o, b.h, b.l, b.c, b.v]
                    for b in brokers.get(brokers.crypto_source()).bars(symbol, start, end, timeframe)]
        return _fetch_crypto(symbol, start, end, timeframe)
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    n, unit = _TF[timeframe]
    client = StockHistoricalDataClient(*alpaca_keys())
    req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame(n, TimeFrameUnit[unit]),
                           start=datetime.combine(start, time(0), ET), end=datetime.combine(end, time(23, 59), ET),
                           feed=DataFeed(feed), adjustment=Adjustment.SPLIT)
    rows = client.get_stock_bars(req).data.get(symbol, [])
    return [[b.timestamp.isoformat(), b.open, b.high, b.low, b.close, b.volume] for b in rows]


_DEMO_REAL: dict[str, bool] = {}      # demo mode: did this crypto symbol's last fetch get real prices?


def demo_real_crypto(symbol: str) -> bool:
    """Demo mode shows REAL past crypto prices when online (Alpaca's crypto history needs no keys); stocks stay
    made-up until keys are added. BOTSCOPE_DEMO_CRYPTO=made-up keeps crypto made-up too (tests, offline use)."""
    return is_crypto(symbol) and os.getenv("BOTSCOPE_DEMO_CRYPTO", "real") != "made-up"


def source_label(symbol: str, daily: bool = False) -> str:
    """Where a symbol's bars came from, in demo mode too (real crypto, or made-up prices)."""
    if demo_mode() and not (demo_real_crypto(symbol) and _DEMO_REAL.get(symbol, False)):
        return demo.SOURCE
    if is_crypto(symbol):
        return crypto_label(daily=daily) + (" (real past prices, in demo mode)" if demo_mode() else "")
    return "Alpaca SIP daily bars (all US exchanges)" if daily else "Alpaca SIP (all US exchanges)"


def bars(symbol: str, start: date, end: date, timeframe: str = "1Min", feed: str = "sip") -> list[BarData]:
    if demo_mode():                                  # no keys: made-up prices, never cached next to real data
        if not demo_real_crypto(symbol):
            return demo.bars(symbol, start, end, timeframe)
        try:                                         # real keyless crypto history; offline = made-up prices
            got = _real_bars(symbol, start, end, timeframe, feed)
            _DEMO_REAL[symbol] = bool(got)
            if got:
                return got
        except Exception:
            _DEMO_REAL[symbol] = False
        return demo.bars(symbol, start, end, timeframe)
    return _real_bars(symbol, start, end, timeframe, feed)


def _real_bars(symbol: str, start: date, end: date, timeframe: str, feed: str) -> list[BarData]:
    if is_crypto(symbol):
        from . import brokers
        feed = brokers.crypto_source()                    # cache per source, so two sources never mix
    path = CACHE / f"{symbol.replace('/', '-')}_{timeframe}_{feed}_{start}_{end}.json"
    if path.exists():
        rows = json.loads(path.read_text())
    else:
        rows = _fetch(symbol, start, end, timeframe, feed)
        if end < date.today():                      # only cache finished history
            CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(rows))
    return [BarData(datetime.fromisoformat(t).astimezone(ET), o, h, l, c, v) for t, o, h, l, c, v in rows]


def clean(bs: list[BarData]) -> tuple[list[BarData], list[str]]:
    """Drop bars a bot should never see: missing/NaN/zero/negative prices, high below low, prices outside the
    high-low range, duplicate times. Sorts by time. Returns (clean bars, plain-English problems)."""
    import math
    out, seen, bad = [], set(), {}
    for b in sorted(bs, key=lambda x: x.t):
        vals = (b.o, b.h, b.l, b.c)
        why = None
        if any(v is None or not isinstance(v, (int, float)) or math.isnan(v) or math.isinf(v) for v in vals):
            why = "missing or NaN price"
        elif min(vals) <= 0:
            why = "zero or negative price"
        elif b.h < b.l or not (b.l <= b.o <= b.h and b.l <= b.c <= b.h):
            why = "price outside the bar's high-low range"
        elif b.t in seen:
            why = "duplicate bar time"
        if why:
            bad[why] = bad.get(why, 0) + 1
            continue
        seen.add(b.t)
        out.append(b)
    problems = [f"dropped {n} bar(s): {why}" for why, n in bad.items()]
    if bs and [b.t for b in bs] != sorted(b.t for b in bs):
        problems.append("bars were out of order (sorted)")
    return out, problems


def by_session(bs: list[BarData], regular_only: bool = True) -> dict[date, list[BarData]]:
    """Group intraday bars by trading day (regular session 9:30-16:00 New York unless regular_only=False)."""
    days = defaultdict(list)
    for b in bs:
        if not regular_only or time(9, 30) <= b.t.time() < time(16, 0):
            days[b.t.date()].append(b)
    return dict(sorted(days.items()))


def sessions(bs: list[BarData], timeframe: str, crypto: bool = False) -> dict[date, list[BarData]]:
    """What the backtester plays as one run: each regular session for intraday bots (crypto: each 24-hour UTC day);
    the whole window (keyed by its last date) for daily bots, so a trade can last several days."""
    if timeframe == "1Day":
        return {bs[-1].t.date(): bs} if bs else {}
    if crypto:
        days = defaultdict(list)
        for b in bs:
            days[b.t.astimezone(UTC).date()].append(b)
        return dict(sorted(days.items()))
    return by_session(bs)


def crypto_label(daily: bool = False) -> str:
    """Names the real crypto source (crypto is never SIP, which is the US stock tape)."""
    from . import brokers
    kind = "daily bars" if daily else "bars"
    if brokers.crypto_source() != "alpaca":
        return f"{brokers.crypto_source().title()} crypto {kind} (24/7, keyless)"
    return f"Alpaca crypto {kind} (Alpaca's US crypto feed, 24/7, keyless)"


DAILY_LOOKBACK = 180    # calendar days of daily bars the chart shows for a daily bot


def view_bars(symbol: str, day: date, timeframe: str, calendar_days: int = DAILY_LOOKBACK) -> tuple[list[BarData], str]:
    """The bars the chart shows: one session for intraday bots, ~6 months ending on `day` for daily bots (more when
    the bot needs a longer lookback: pass backtest.warmup_days(bot, DAILY_LOOKBACK))."""
    if timeframe != "1Day":
        bs, src = day_bars(symbol, day, timeframe)
        return sessions(bs, timeframe, is_crypto(symbol)).get(day, []), src
    end = min(day, datetime.now(ET).date() - timedelta(days=1))     # daily bars up to yesterday's close
    bs = bars(symbol, end - timedelta(days=max(calendar_days, DAILY_LOOKBACK)), end, "1Day", "sip")
    return bs, source_label(symbol, daily=True)


def recent_window(days: int, end: date | None = None) -> tuple[date, date]:
    end = end or date.today() - timedelta(days=1)
    return end - timedelta(days=days), end


def day_bars(symbol: str, day: date, timeframe: str = "1Min") -> tuple[list[BarData], str]:
    """One trading day of bars + a label naming the source. Reuses any cached month that covers the day. Today
    comes from the free IEX feed (SIP is delayed 15 minutes on free keys)."""
    if demo_mode():
        bs = bars(symbol, day, day, timeframe)       # made-up, or real crypto when online
        return bs, source_label(symbol)
    for f in sorted(CACHE.glob(f"{symbol.replace('/', '-')}_{timeframe}_sip_*.json")):
        try:
            a, b = (date.fromisoformat(x) for x in f.stem.split("_")[-2:])
        except ValueError:
            continue
        if a <= day <= b:
            rows = [r for r in json.loads(f.read_text()) if datetime.fromisoformat(r[0]).astimezone(ET).date() == day]
            src = (crypto_label() if is_crypto(symbol) else "Alpaca SIP (all US exchanges)") + \
                ", cached on this computer"
            return [BarData(datetime.fromisoformat(t).astimezone(ET), o, h, l, c, v) for t, o, h, l, c, v in rows], src
    if is_crypto(symbol):
        return bars(symbol, day, day, timeframe, "sip"), crypto_label()
    if day >= datetime.now(ET).date():
        return bars(symbol, day, day, timeframe, "iex"), "Alpaca IEX (live, free feed: one exchange, about 2-3% of volume)"
    return bars(symbol, day, day, timeframe, "sip"), "Alpaca SIP (all US exchanges)"
