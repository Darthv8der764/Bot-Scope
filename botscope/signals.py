"""Signals: where YOUR strategies' own entry rules fire right now, refreshed through the trading day.

For every bot (yours first; the examples only when asked), today's bars so far are replayed with the bot's own rules,
exactly like the chart does. A row appears only where the bot's entry() itself returned an Entry on the latest
finished bar (or within the last few minutes). Nothing is scored, ranked or invented here: the bot's rule decides, and
every row carries that strategy's honest track record next to it. "Close to firing" rows are the bot's own near misses
(NoTrade.almost); "already in a trade" rows are entries from earlier today that are still open on paper.

Read-only and paper only: this module never sends, changes or cancels an order. Not financial advice.
"""
from __future__ import annotations

import threading
from datetime import date, datetime, time, timedelta

from . import backtest, confidence, data, journal, loader
from .bot import Entry, NoTrade, View
from .data import ET, UTC

WINDOW_MIN = 15          # an entry this many minutes before the latest bar still counts as "now"
MAX_SYMBOLS = 20         # per bot, so one long watchlist can't stall the page
REFRESH_S = 60
DAILY_REPLAY_BARS = 30   # daily bots: bars replayed after their lookback (a trade open longer shows as no signal)
_TF_MIN = {"1Min": 1, "5Min": 5, "15Min": 15, "30Min": 30, "1Hour": 60, "1Day": 1440}
NOTE = ("Paper only, not financial advice. Each row is what one of your strategies' own rules says on the latest "
        "finished bar, with that strategy's track record next to it. BotScope never places an order from this page.")

_cache: dict[tuple, dict] = {}          # (bot, symbol, day, minute) -> one symbol's result
_bars_cache: dict[tuple, tuple] = {}    # (symbol, timeframe, day, minute) -> (bars, source)
_cache_lock = threading.Lock()
_last: dict | None = None               # the last full scan (shown while another replay holds the lock)


def stocks_open(now: datetime) -> bool:
    """Regular US hours by the clock (9:30-16:00 New York, Mon-Fri). Holidays show up as "no bars today"."""
    now = now.astimezone(ET)
    return now.weekday() < 5 and time(9, 30) <= now.time() < time(16, 0)


def _clock(t: datetime) -> str:
    return t.astimezone(ET).strftime("%-I:%M %p")


def _session_day(symbol: str, timeframe: str, now: datetime) -> date:
    """The session being watched: today while it trades, else the last one (daily bots: up to yesterday's close)."""
    if timeframe == "1Day":
        d = now.astimezone(ET).date() - timedelta(days=1)
        while d.weekday() >= 5 and not data.is_crypto(symbol):
            d -= timedelta(days=1)
        return d
    if data.is_crypto(symbol):
        return now.astimezone(UTC).date()
    d = now.astimezone(ET).date()
    if now.astimezone(ET).time() < time(9, 31) or d.weekday() >= 5:      # before the first bar: the last session
        d -= timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
    return d


def _fetch(symbol: str, day: date, cls) -> tuple[list, str]:
    """The chart's bars for that session (live IEX for today's stocks, keyless crypto), cached per minute."""
    k = (symbol, cls.timeframe, day, datetime.now(ET).strftime("%Y%m%d%H%M"), backtest.warmup_days(cls))
    with _cache_lock:
        if k in _bars_cache:
            return _bars_cache[k]
    got = data.view_bars(symbol, day, cls.timeframe, backtest.warmup_days(cls, data.DAILY_LOOKBACK))
    with _cache_lock:
        if len(_bars_cache) > 400:
            _bars_cache.clear()
        _bars_cache[k] = got
    return got


def finished(bs: list, timeframe: str, now: datetime) -> list:
    """Only bars that have closed by `now` (a bar still forming, or a made-up future bar, is left out)."""
    if timeframe == "1Day":
        return bs
    step = timedelta(minutes=_TF_MIN.get(timeframe, 1))
    return [b for b in bs if b.t + step <= now]


def track_record(cls) -> dict:
    """The strategy's honest record, read from what is saved on this computer: the confidence meter, the untested
    numbers from the last full report (else the last quick backtest), and closed live paper trades."""
    from . import report
    bid = loader.bot_id(cls)
    conf = confidence.for_bot(bid)
    saved = report.saved(cls) or {}
    u, src = saved.get("untested") or {}, "full report"
    if not u.get("trades"):
        u, src = (journal.find("backtests", bot=bid) or [{}])[-1].get("untested") or {}, "quick backtest"
    live = conf.get("live") or {}
    return {"confidence": conf["level"], "confidence_step": conf["step"], "why": conf["why"],
            "untested_trades": u.get("trades", 0), "untested_avg_r": u.get("avg_r"),
            "untested_source": src if u.get("trades") else None,
            "live_paper_trades": live.get("trades", 0), "live_paper_avg_r": live.get("avg_r"),
            "summary": _track_line(conf["level"], u, live)}


def _track_line(level: str, u: dict, live: dict) -> str:
    n = u.get("trades", 0)
    bits = [f"confidence {level}"]
    bits.append(f"{n} untested trades, {u['avg_r']:+.2f}R each after costs" if n and u.get("avg_r") is not None
                else "no untested backtest yet")
    if live.get("trades"):
        bits.append(f"{live['trades']} live paper trades, {live['avg_r']:+.2f}R each")
    return "; ".join(bits)


def scan_symbol(cls, symbol: str, now: datetime, window_min: int = WINDOW_MIN, fetch=None) -> dict:
    """Replay one bot on one symbol's session so far. {signal | close | in_trade | None, last_bar, source, problems}."""
    day = _session_day(symbol, cls.timeframe, now)
    bs, source = (fetch or _fetch)(symbol, day, cls)
    if not bs and cls.timeframe != "1Day" and not data.is_crypto(symbol) and day == now.astimezone(ET).date():
        source += " (no bars yet today)"
    bs, bad = data.clean(finished(bs, cls.timeframe, now))
    if cls.timeframe == "1Day":      # today's decision needs only the bot's lookback, plus room for a trade still open
        bs = bs[-(getattr(cls, "lookback_days", 0) + DAILY_REPLAY_BARS):]
    out = {"day": str(day), "source": source, "problems": bad, "last_bar": None, "kind": None}
    if not bs:
        return out
    live = cls.timeframe != "1Day" and (data.is_crypto(symbol) or (day == now.astimezone(ET).date() and stocks_open(now)))
    bot = cls()
    if live:                         # the session isn't over: the latest bar is not "the last bar of the day"
        bot.flat_by_close = False
    seen = []                        # the bot's own decision on each bar it was asked about
    real_entry = bot.entry
    bot.entry = lambda view: seen.append((view.now, real_entry(view))) or seen[-1][1]
    trace = []
    _, problems = backtest.run_day(bot, symbol, day, bs, backtest.COSTS[cls.asset], trace=trace)
    out["problems"] += problems
    last = bs[-1]
    out["last_bar"] = last.t
    state = next((x for x in reversed(trace) if x["kind"] in ("entry", "holding", "exit")), None)
    base = {"symbol": symbol, "day": str(day), "source": source, "last_bar": last.t}
    if state and state["kind"] != "exit":                       # an entry is open on paper right now
        e = next(x for x in reversed(trace) if x["kind"] == "entry")
        price = next(b.c for b in bs if b.t == e["t"])
        fresh = last.t - e["t"] <= timedelta(minutes=max(window_min, 0)) or e["t"] == last.t
        out.update(kind="signal" if fresh else "in_trade",
                   row=_row(base, e["side"], price, e["stop"], e["target"], e["reason"].split(": ", 1)[-1], e["t"], last.c))
        return out
    dec = seen[-1][1] if seen and seen[-1][0] == last.t else None
    if isinstance(dec, NoTrade) and isinstance(dec.almost, Entry):     # the bot's own near miss on the latest bar
        a = dec.almost
        if (a.stop < last.c) if a.side == "long" else (a.stop > last.c):
            out.update(kind="close", row=_row(base, a.side, last.c, a.stop, a.target, a.reason, last.t, last.c)
                       | {"blocked_by": dec.reason})
    return out


def _row(base: dict, side: str, price: float, stop: float, target, reason: str, t: datetime, now_px: float) -> dict:
    risk = abs(price - stop)
    return base | {"side": side, "price": round(price, 4), "stop": round(stop, 4),
                   "target": round(target, 4) if target is not None else None,
                   "risk": round(risk, 4), "risk_pct": round(risk / price * 100, 3) if price else None,
                   "target_r": round(abs(target - price) / risk, 2) if target is not None and risk else None,
                   "last_price": round(now_px, 4),
                   "moved_r": round((now_px - price) / risk * (1 if side == "long" else -1), 2) if risk else None,
                   "reason": reason, "time": t, "time_label": _clock(t)}


def scan(include_examples: bool = False, window_min: int = WINDOW_MIN, now: datetime | None = None,
         bots: dict | None = None, fetch=None) -> dict:
    """Every bot (yours first) on every one of its symbols: what its own rules say on the latest finished bar."""
    global _last
    now = (now or datetime.now(ET)).astimezone(ET)
    window_min = max(0, min(int(window_min), 240))
    real = bots is None and fetch is None             # the page's scan (tests pass their own bots and bars)
    if bots is None:
        bots, errors = loader.load_all()
    else:
        errors = []
    mine = {k: c for k, c in bots.items() if loader.is_mine(c)}
    chosen = {**mine, **({k: c for k, c in bots.items() if k not in mine} if include_examples else {})}
    signals, close, in_trade, cards, problems = [], [], [], [], [f"{e['file']}: {e['error']}" for e in errors]
    last_stock_bar, any_crypto = None, False
    minute = now.strftime("%Y%m%d%H%M")
    for bid, cls in chosen.items():
        track = track_record(cls)
        card = {"id": bid, "name": cls.name, "mine": bid in mine, "timeframe": cls.timeframe,
                "symbols": list(cls.symbols)[:MAX_SYMBOLS], "track": track, "checked": 0, "problems": []}
        if len(cls.symbols) > MAX_SYMBOLS:
            card["problems"].append(f"watching the first {MAX_SYMBOLS} of its {len(cls.symbols)} symbols")
        for sym in card["symbols"]:
            sym = sym.upper()
            any_crypto = any_crypto or data.is_crypto(sym)
            k = (bid, sym, now.strftime("%Y%m%d") if cls.timeframe == "1Day" else minute, window_min, real)   # daily: once a day
            with _cache_lock:
                got = _cache.get(k)
            if got is None:
                try:
                    got = scan_symbol(cls, sym, now, window_min, fetch)
                except Exception as e:      # one symbol without data never stops the rest
                    got = {"kind": None, "problems": [f"{sym}: no data ({type(e).__name__}: {str(e)[:120]})"],
                           "last_bar": None}
                with _cache_lock:
                    if len(_cache) > 2000:
                        _cache.clear()
                    _cache[k] = got
            card["checked"] += 1
            card["problems"] += [p if p.startswith(sym) else f"{sym}: {p}" for p in got.get("problems", [])][:3]
            if got.get("last_bar") and not data.is_crypto(sym) and cls.timeframe != "1Day":
                last_stock_bar = max(last_stock_bar or got["last_bar"], got["last_bar"])
            if got.get("kind"):
                verb = "buy" if got["row"]["side"] == "long" else "sell short"
                row = got["row"] | {"bot": bid, "bot_name": cls.name, "mine": bid in mine, "track": track,
                                    "timeframe": cls.timeframe, "verb": verb,
                                    **({"time_label": f"{got['row']['time']:%a %b %-d} close"} if cls.timeframe == "1Day" else {}),
                                    "link": f"/?bot={bid}&symbol={sym.replace('/', '%2F')}&day={got['day']}"}
                row["says"] = {"signal": f"your strategy {cls.name} says {verb}",
                               "close": f"your strategy {cls.name} almost says {verb}",
                               "in_trade": f"your strategy {cls.name} is already in a paper {got['row']['side']}"}[got["kind"]]
                {"signal": signals, "close": close, "in_trade": in_trade}[got["kind"]].append(row)
        cards.append(card)
    for rows in (signals, close, in_trade):
        rows.sort(key=lambda r: (not r["mine"], -r["track"]["confidence_step"], -r["time"].timestamp()))
    is_open = stocks_open(now)
    if is_open:
        note = "US market open: refreshing every minute."
    else:
        when = f" from {_clock(last_stock_bar)} on {last_stock_bar:%a %b %-d}" if last_stock_bar else ""
        note = f"US market closed: last signals{when}." + (" Crypto trades around the clock, so crypto rows stay live."
                                                           if any_crypto else "")
    out = {"as_of": now, "as_of_label": now.strftime("%-I:%M:%S %p"), "paper_only": True,
           "market": {"stocks_open": is_open, "note": note,
                      "last_stock_bar": _clock(last_stock_bar) if last_stock_bar else None},
           "live": is_open or any_crypto, "refresh_s": REFRESH_S if (is_open or any_crypto) else None,
           "include_examples": include_examples, "window_min": window_min,
           "own_bots": len(mine), "bots": cards, "signals": signals, "close": close, "in_trade": in_trade,
           "problems": problems, "note": NOTE}
    if not mine and not include_examples:
        out["empty_reason"] = ("No bots of your own yet (bots_private/ or your bots folder). Tick \"include examples\" "
                               "to see the example bots here, or add your own strategy.")
    if real:
        _last = out
    return out


def last() -> dict | None:
    """The last full scan, for when another replay holds the lock."""
    return _last
