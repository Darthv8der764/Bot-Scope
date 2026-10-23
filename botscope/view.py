"""The "what the bot sees" chart: a page on this computer only (127.0.0.1) that shows one bot on one symbol and day.

Candles, the bot's indicators(), its entries/exits, stop and target lines you can drag, vetoes, your drawings, and a
"why not here?" reason for every candle. Everything is PAPER: moving a line or vetoing replays the day with your
change; nothing here sends an order. Your changes are saved by journal.py (local JSON).

The same actions are used by the page (HTTP) and by Claude (MCP tools in server.py).
"""
from __future__ import annotations

import bisect
import json
import socket
import threading
from datetime import date, datetime, time, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from . import backtest, benchmark, confidence, data, journal, loader, settings
from .bot import Entry, NoTrade
from .errtext import say
from .data import ET
from .env import key

PAGE = Path(__file__).with_name("web") / "bot_view.html"
HOST, FIRST_PORT = "127.0.0.1", 8765
_whatif_lock = threading.Lock()            # one what-if grid at a time (it replays many days)


# ---------- helpers ----------
def is_live_money() -> bool:
    """BotScope is paper only today. If a live switch is ever added, every change asks for a confirmation."""
    return key("BOTSCOPE_LIVE_TRADING") == "1"


def trade_id(symbol: str, t: datetime) -> str:
    return f"{symbol}_{t:%Y-%m-%d_%H%M}"


def chart_time(t: datetime) -> int:
    """Lightweight Charts draws UTC; shift so the axis shows New York time."""
    return int(t.timestamp() + t.utcoffset().total_seconds())


def latest_session(symbol: str, timeframe: str, now: datetime | None = None) -> date:
    now = now or datetime.now(ET)
    crypto = data.is_crypto(symbol)               # crypto trades every day, around the clock
    if timeframe == "1Day":                       # daily bots: the window ends at yesterday's close
        d = now.date() - timedelta(days=1)
        while d.weekday() >= 5 and not crypto:
            d -= timedelta(days=1)
        return d
    d = now.date() if crypto or now.time() >= time(9, 31) else now.date() - timedelta(days=1)
    for _ in range(7):
        if (crypto or d.weekday() < 5) and data.day_bars(symbol, d, timeframe)[0]:
            return d
        d -= timedelta(days=1)
    raise RuntimeError(f"no {symbol} bars in the last week")


def _key(bot_id, symbol, day):
    return {"bot": bot_id, "symbol": symbol.upper(), "day": str(day)}


# ---------- the day, replayed with your changes ----------
def _replay(cls, symbol, bs, day, overrides, vetoes, ghosts=None):
    bot = cls()

    def hook(view, dec: Entry):
        tid = trade_id(symbol, view.now)
        if tid in vetoes:
            return NoTrade("you vetoed this trade, so the bot skipped it (paper)")
        o = overrides.get(tid)
        if o:
            return Entry(dec.side, o.get("stop") or dec.stop, o.get("target") or dec.target, dec.reason)
        return dec

    trace = []
    trades, problems = backtest.run_day(bot, symbol, day, bs, backtest.COSTS[bot.asset], hook, trace, ghosts=ghosts)
    return bot, trades, problems, trace


SHOWCASE_NOTE = ("Example day, picked to show one full trade from entry to exit (made-up demo prices). Most days "
                 "aren't like this: the honest report counts every day, good and bad.")


def showcase_day(cls, symbol: str, look_back: int = 60) -> date | None:
    """Demo mode only: the most recent made-up day where the bot made exactly one trade that closed at its target
    (else at its stop), so a newcomer sees a whole trade. Labeled as picked; never used for any result."""
    from .env import demo_mode
    if not demo_mode() or cls.timeframe == "1Day":
        return None
    d, fallback = latest_session(symbol, cls.timeframe), None
    for _ in range(look_back):
        bs = data.clean(data.view_bars(symbol, d, cls.timeframe)[0])[0]
        if bs:
            _, trades, _, _ = _replay(cls, symbol, bs, d, {}, set())
            if len(trades) == 1:
                if "target" in trades[0].why_out:
                    return d
                fallback = fallback or d
        d -= timedelta(days=1)
    return fallback


def build(bot: str, symbol: str | None = None, day: str | None = None) -> dict:
    cls = loader.get(bot)
    bid = loader.bot_id(cls)
    symbol = (symbol or cls.symbols[0]).upper()
    note = None
    if day == "showcase":                       # the tutorial's example day (demo only; real data: the latest day)
        d = showcase_day(cls, symbol)
        note, day = (SHOWCASE_NOTE if d else None), (str(d) if d else None)
    d = date.fromisoformat(day) if day else latest_session(symbol, cls.timeframe)
    bs, source = data.view_bars(symbol, d, cls.timeframe, backtest.warmup_days(cls, data.DAILY_LOOKBACK))
    bs, bad_bars = data.clean(bs)
    k = _key(bid, symbol, d)
    overrides = {r["trade_id"]: r for r in journal.find("trade_overrides", **k)}
    vetoes = {r["trade_id"]: r for r in journal.find("vetoes", **k)}
    ghosts = []
    bot_obj, trades, problems, trace = _replay(cls, symbol, bs, d, overrides, vetoes, ghosts)
    shadow = {}
    if vetoes:                                   # what the vetoed trades would have done (seed for the veto scorecard)
        _, raw, _, _ = _replay(cls, symbol, bs, d, overrides, set())
        shadow = {trade_id(symbol, datetime.fromisoformat(t.t_in)): t for t in raw}

    is_today = d == datetime.now(ET).date()
    if is_today:
        log_paper_day(bid, symbol, d, cls, bs)
    out_trades = []
    for t in trades:
        tin = datetime.fromisoformat(t.t_in)
        out_trades.append({"id": trade_id(symbol, tin), "side": t.side, "open": False,
                           "t_in": chart_time(tin), "t_out": chart_time(datetime.fromisoformat(t.t_out)),
                           "entry": t.entry, "exit": t.exit, "stop": t.stop, "target": t.target,
                           "why_in": t.why_in, "why_out": t.why_out, "r": t.r,
                           "receipt": backtest.receipt(t), "moved": trade_id(symbol, tin) in overrides})
    last = next((x for x in reversed(trace) if x["kind"] in ("entry", "holding", "exit")), None)
    if last and last["kind"] != "exit" and (is_today or cls.timeframe == "1Day"):   # an open paper trade right now
        e = next(x for x in reversed(trace) if x["kind"] == "entry")
        out_trades.append({"id": trade_id(symbol, e["t"]), "side": e["side"], "open": True,
                           "t_in": chart_time(e["t"]), "t_out": chart_time(bs[-1].t), "entry": bs[[b.t for b in bs].index(e["t"])].c,
                           "exit": None, "stop": e["stop"], "target": e["target"], "why_in": e["reason"],
                           "why_out": "still open", "r": None, "moved": trade_id(symbol, e["t"]) in overrides})
    vetoed = []
    for x in trace:
        if x["kind"] == "vetoed":
            tid = trade_id(symbol, x["t"])
            s = shadow.get(tid)
            vetoed.append({"id": tid, "t": chart_time(x["t"]), "side": x["side"], "price": x["price"],
                           "stop": x["stop"], "target": x["target"], "why_in": x["why_in"],
                           "reason_you_gave": vetoes[tid].get("reason", ""),
                           "would_have_r": s.r if s else None, "would_have_exit": s.why_out if s else None})

    ind = bot_obj.indicators(bs)
    vs_spy = None
    if bs:                                       # beat just holding?: same $10,000 in SPY over the days on screen
        bot_usd = sum(t.pct for t in trades) / 100 * 10_000
        try:
            vs_spy = benchmark.compare(bot_usd, bs[0].t.date(), bs[-1].t.date())
        except RuntimeError:
            vs_spy = None
    return {
        "bot": {"id": bid, **cls.card()}, "symbol": symbol, "day": str(d), "source": source,
        "live": is_today, "account": "LIVE MONEY" if is_live_money() else "PAPER",
        "candles": [{"time": chart_time(b.t), "open": b.o, "high": b.h, "low": b.l, "close": b.c} for b in bs],
        "indicators": {n: [{"time": chart_time(b.t), **({"value": v} if v is not None else {})} for b, v in zip(bs, vals)]
                       for n, vals in ind.items()},
        "trades": out_trades, "vetoed": vetoed,
        "ghosts": [{"id": "ghost_" + trade_id(symbol, datetime.fromisoformat(g.t_in)), "side": g.side,
                    "t_in": chart_time(datetime.fromisoformat(g.t_in)), "t_out": chart_time(datetime.fromisoformat(g.t_out)),
                    "entry": g.entry, "exit": g.exit, "stop": g.stop, "target": g.target, "why_in": g.why_in,
                    "why_out": g.why_out, "r": g.r} for g in ghosts],
        "reasons": {str(chart_time(x["t"])): {"kind": x["kind"], "reason": x["reason"]} for x in trace},
        "drawings": journal.find("drawings", **k), "rule_ideas": journal.find("rule_ideas", bot=bid),
        "problems": bad_bars + problems, "confidence": confidence.for_bot(bid),
        "stopped": settings.load()["stopped"],
        "events": _events(str(d), bs, cls),
        "empty_reason": empty_reason(d, datetime.now(ET).date(), data.is_crypto(symbol)) if not bs else None,
        "vs_spy": vs_spy, **({"note": note} if note else {}),
    }


# Bot view time ranges: the longer the range, the bigger each candle, so it never looks jumbled.
SPANS = {"2d": ("5Min", 2), "5d": ("15Min", 5), "10d": ("30Min", 10), "1m": ("1Hour", 21), "3m": ("1Day", 63),
         "6m": ("1Day", 126)}          # (candle size, trading days shown)


def snap(times: list[int], t: int) -> int:
    """The start of the bigger candle a trade falls in (the last candle starting at or before it)."""
    i = bisect.bisect_right(times, t) - 1
    return times[max(i, 0)]


def build_span(bot: str, symbol: str | None, day: str | None, span: str) -> dict:
    """The chart over 2 days to 6 months with bigger candles. Trades come from replaying the bot on its own candles
    each day in the range (intraday) or over the range (daily), then are placed on the bigger candles."""
    if span not in SPANS:
        raise ValueError(f"range must be one of {', '.join(SPANS)}")
    cls = loader.get(bot)
    bid, (tf, n) = loader.bot_id(cls), SPANS[span]
    symbol = (symbol or cls.symbols[0]).upper()
    d = date.fromisoformat(day) if day else latest_session(symbol, cls.timeframe)
    crypto = data.is_crypto(symbol)
    start = d - timedelta(days=n if crypto else int(n * 7 / 5) + 4)
    big = data.clean(data.bars(symbol, start, d, tf))[0]
    if tf != "1Day":
        big = [b for day_bs in data.sessions(big, tf, crypto).values() for b in day_bs]   # regular hours only
    days = sorted({b.t.astimezone(ET).date() for b in big})[-n:]
    big = [b for b in big if days and b.t.astimezone(ET).date() >= days[0]]
    trades = []
    if cls.timeframe == "1Day":
        bs, _ = data.view_bars(symbol, d, "1Day", backtest.warmup_days(cls, data.DAILY_LOOKBACK) + n * 2)
        got, _ = backtest.run_day(cls(), symbol, d, data.clean(bs)[0], backtest.COSTS[cls.asset])
        trades = [t for t in got if days and t.t_in[:10] >= str(days[0])]
    else:
        for x in days:
            bs, _ = data.view_bars(symbol, x, cls.timeframe)
            bs = data.clean(bs)[0]
            if bs:
                trades += backtest.run_day(cls(), symbol, x, bs, backtest.COSTS[cls.asset], close_at_end=True)[0]
    times = [chart_time(b.t) for b in big]
    out_trades = []
    for t in trades:
        tin, tout = chart_time(datetime.fromisoformat(t.t_in)), chart_time(datetime.fromisoformat(t.t_out))
        if not times:
            break
        out_trades.append({"id": trade_id(symbol, datetime.fromisoformat(t.t_in)), "side": t.side, "open": False,
                           "t_in": snap(times, tin), "t_out": snap(times, tout), "entry": t.entry, "exit": t.exit,
                           "stop": t.stop, "target": t.target, "why_in": t.why_in, "why_out": t.why_out, "r": t.r,
                           "receipt": backtest.receipt(t), "moved": False})
    from . import demo
    from .env import demo_mode
    src = data.source_label(symbol) if demo_mode() or crypto else "Alpaca SIP bars (all US exchanges)"
    return {"bot": {"id": bid, **cls.card()}, "symbol": symbol, "day": str(d), "span": span, "candle": tf,
            "source": f"{src}, {tf} candles", "live": False, "account": "LIVE MONEY" if is_live_money() else "PAPER",
            "candles": [{"time": chart_time(b.t), "open": b.o, "high": b.h, "low": b.l, "close": b.c} for b in big],
            "indicators": {}, "trades": out_trades, "vetoed": [], "ghosts": [], "reasons": {}, "drawings": [],
            "rule_ideas": [], "problems": [], "confidence": confidence.for_bot(bid), "stopped": settings.load()["stopped"],
            "events": [], "vs_spy": None,
            "empty_reason": None if big else f"no {tf} candles for {symbol} in the {len(days) or n} days up to {d}",
            "note": f"{len(days)} trading days on {tf} candles; each trade is drawn on the candle it happened in. "
                    "Pick 1 day to veto, move lines or replay."}


def empty_reason(d: date, today: date, crypto: bool = False) -> str:
    """Why a chart has no candles, in plain words (instead of a blank chart)."""
    if d > today:
        return f"No candles: {d} hasn't happened yet."
    if crypto:                                    # never "the market is closed": crypto trades every day
        return f"No candles for {d}: no crypto data from this source for that day yet."
    if d.weekday() >= 5:
        return f"No candles: {d} is a {d.strftime('%A')}, the market is closed. Pick a weekday."
    if d == today:
        return "No candles yet today: the market opens at 9:30 AM New York time."
    return f"No candles for {d}: a market holiday, or no data for this symbol that day."


def _events(day: str, bs, cls) -> list[dict]:
    """Market events that day (Fed, CPI, earnings of a bot ticker...) for a warning on the chart."""
    from . import desk
    from .eventdays import today_note
    evs = desk.events_on(day)
    note = today_note(loader.bot_id(cls), [e["event"].split(" (")[0] for e in evs]) if evs else ""
    return evs + ([{"event": f"this bot {note}", "source": "event_days (untested trades)"}] if note else [])


def log_paper_day(bid, symbol, d, cls, bs, day_over=False):
    """Closed trades on a live day are forward paper results for the confidence meter. The bot's own trades are
    logged (your vetoes and moved lines are left out, so the meter grades the bot, not your edits)."""
    _, raw, _, _ = _replay(cls, symbol, bs, d, {}, set())
    have = {r["trade_id"] for r in journal.find("paper_results", bot=bid, symbol=symbol)}
    day_over = day_over or (bool(bs) and bs[-1].t.time() >= time(15, 59))
    for t in raw:
        tid = trade_id(symbol, datetime.fromisoformat(t.t_in))
        if tid in have or (t.why_out == "end of day" and not day_over):   # still open right now: not a result yet
            continue
        journal.upsert("paper_results", {**_key(bid, symbol, d), "trade_id": tid},
                       {"side": t.side, "r": t.r, "why_out": t.why_out})


def why_not_here(bot: str, symbol: str, day: str, hhmm: str) -> dict:
    st = build(bot, symbol, day)
    t = datetime.combine(date.fromisoformat(st["day"]), time.fromisoformat(hhmm), ET)
    r = st["reasons"].get(str(chart_time(t)))
    return {"time": hhmm, **(r or {"kind": "none", "reason": "no bar at that time (market closed or no trades)"})}


# ---------- actions (page + Claude) ----------
def _find_trade(st: dict, tid: str | None) -> dict:
    pool = st["trades"] + [dict(v, entry=v["price"]) for v in st["vetoed"]]
    if not pool:
        raise ValueError("the bot took no trades that day")
    if tid is None:
        return pool[-1]
    for t in pool:
        if t["id"] == tid:
            return t
    raise ValueError(f"no trade {tid}; trades: {', '.join(t['id'] for t in pool)}")


def veto(bot: str, symbol: str, day: str, trade_id: str | None = None, reason: str = "") -> dict:
    st = build(bot, symbol, day)
    t = _find_trade(st, trade_id)
    k = _key(st["bot"]["id"], st["symbol"], st["day"])
    row = journal.upsert("vetoes", {**k, "trade_id": t["id"]},
                         {"side": t["side"], "entry": t["entry"], "stop": t["stop"], "target": t["target"],
                          "why_bot_wanted_it": t["why_in"], "reason": reason, "account": st["account"]})
    return {"vetoed": t["id"], "saved_to": str(journal.folder() / "vetoes.json"), "row": row,
            "note": "Paper: the bot skips this trade. veto_scorecard shows whether your vetoes helped or hurt."}


def veto_scorecard(bot: str | None = None) -> dict:
    """Replay every logged veto: did skipping the trade help (it would have lost) or hurt (it would have won)?"""
    rows = journal.find("vetoes", bot=loader.bot_id(loader.get(bot)) if bot else None)
    days, out = {}, []
    for r in rows:
        days.setdefault((r["bot"], r["symbol"], r["day"]), []).append(r)
    for (b, sym, day), vs in sorted(days.items(), key=lambda kv: kv[0][2]):
        try:
            st = build(b, sym, day)
            seen = {v["id"]: v for v in st["vetoed"]}
            err = None
        except Exception as e:     # bot renamed or data unavailable: still list the veto
            seen, err = {}, str(e)
        for r in vs:
            v = seen.get(r["trade_id"], {})
            wr = v.get("would_have_r")
            verdict = ("unknown" if wr is None else "helped" if wr < 0 else "hurt" if wr > 0 else "no change")
            out.append({"bot": b, "symbol": sym, "day": day, "trade_id": r["trade_id"], "side": r.get("side"),
                        "your_reason": r.get("reason", ""), "would_have_r": wr,
                        "would_have_exit": v.get("would_have_exit"), "verdict": verdict,
                        **({"problem": err or "the bot no longer takes this trade (its rules or data changed)"}
                           if wr is None else {})})
    known = [x for x in out if x["would_have_r"] is not None]
    saved = round(-sum(x["would_have_r"] for x in known), 2)
    n_help = sum(x["verdict"] == "helped" for x in out); n_hurt = sum(x["verdict"] == "hurt" for x in out)
    if not known:
        verdict = "no vetoes to grade yet" if not out else "none of your vetoes could be replayed"
    else:
        verdict = (f"your vetoes {'helped' if saved > 0 else 'hurt' if saved < 0 else 'broke even'}: "
                   f"{abs(saved):.2f}R {'saved' if saved >= 0 else 'missed'} over {len(known)} vetoes")
        if len(known) < 10:
            verdict += " (fewer than 10 vetoes, so this could easily be luck)"
    return {"verdict": verdict, "vetoes": len(out), "helped": n_help, "hurt": n_hurt,
            "net_r_saved": saved, "rows": out,
            "note": "Paper replay. helped = the trade would have lost; hurt = it would have won. Not financial advice."}


def undo_veto(bot: str, symbol: str, day: str, trade_id: str) -> dict:
    k = _key(loader.bot_id(loader.get(bot)), symbol, day)
    rows = journal.find("vetoes", **k, trade_id=trade_id)
    for r in rows:
        journal.remove("vetoes", r["id"])
    return {"removed": len(rows)}


def move_lines(bot: str, symbol: str, day: str, trade_id: str | None = None, stop: float | None = None,
               target: float | None = None, scope: str | None = None, confirm: bool = False) -> dict:
    """Move a trade's stop and/or target. scope: 'this_trade' or 'rule'. No scope = ask first."""
    if stop is None and target is None:
        raise ValueError("give a new stop and/or target price")
    st = build(bot, symbol, day)
    t = _find_trade(st, trade_id)
    d = 1 if t["side"] == "long" else -1
    if stop is not None and d * (stop - t["entry"]) >= 0:
        raise ValueError(f"a {t['side']} stop must be {'below' if d == 1 else 'above'} the entry ({t['entry']:.2f})")
    if target is not None and d * (target - t["entry"]) <= 0:
        raise ValueError(f"a {t['side']} target must be {'above' if d == 1 else 'below'} the entry ({t['entry']:.2f})")
    if scope not in ("this_trade", "rule"):
        return {"question": "Just this trade, or the rule for all future trades?", "trade": t["id"],
                "options": ["this_trade", "rule"], "nothing_saved": True}
    if st["account"] != "PAPER" and not confirm:
        return {"question": "This is REAL MONEY. Confirm the change?", "needs": "confirm=true", "nothing_saved": True}
    k = _key(st["bot"]["id"], st["symbol"], st["day"])
    if scope == "this_trade":
        row = journal.upsert("trade_overrides", {**k, "trade_id": t["id"]},
                             {"stop": stop, "target": target, "original_stop": t["stop"], "original_target": t["target"]})
        return {"moved": t["id"], "row": row, "note": "Paper: the day was replayed with your new line(s). The bot's rules did not change."}
    risk0 = abs(t["entry"] - t["stop"])
    idea = {"bot": st["bot"]["id"], "from_trade": t["id"], "status": "needs a backtest before it can be used",
            "current_params": st["bot"]["params"]}
    if stop is not None:
        idea["stop_change"] = f"stop at {abs(t['entry'] - stop) / risk0:.2f}x the rule's distance from entry (was 1.00x)"
    if target is not None:
        idea["target_change"] = (f"target at {abs(target - t['entry']) / risk0:.2f}R "
                                 f"(was {abs(t['target'] - t['entry']) / risk0:.2f}R)" if t["target"] else
                                 f"target at {abs(target - t['entry']) / risk0:.2f}R (was none)")
    row = journal.add("rule_ideas", idea)
    return {"rule_idea": row, "next": "Run run_backtest with the matching params (tuned vs untested days) and show "
                                      "the before/after. The bot only changes if the user approves after that."}


def quiz_score(bot: str, symbol: str, day: str, hits: int, n: int) -> dict:
    """Save a chart quiz score (first try per bot/symbol/day only: a retake has seen the answers) and return the
    last 7 days in counts. Matching the bot is a skill check, not a sign that its trades are good."""
    hits, n = int(hits), int(n)
    if not 0 <= hits <= n <= 50:
        raise ValueError("a quiz score is hits 0..n with n at most 50")
    k = _key(loader.bot_id(loader.get(bot)), symbol, day)
    rows = journal.load("quiz")
    counted = not any(all(r.get(f) == v for f, v in k.items()) for r in rows)
    if counted:
        journal.add("quiz", {**k, "hits": hits, "n": n})
        rows = journal.load("quiz")
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
    week = [r for r in rows if r.get("saved_at", "") >= since]
    return {"counted": counted, "week": {"quizzes": len(week), "hits": sum(r["hits"] for r in week),
                                         "candles": sum(r["n"] for r in week)},
            "note": "First try per bot, symbol and day counts; retakes don't (you've seen the answers)."}


def add_drawing(bot: str, symbol: str, day: str, kind: str, points: list[dict], note: str = "") -> dict:
    if kind == "note" and len(points) == 1:          # a note pinned to one candle: stored as a zero-length line
        points = points * 2
        if not note.strip():
            raise ValueError("a chart note needs some text")
    if kind not in ("line", "circle", "note") or len(points) != 2:
        raise ValueError("a drawing is a 'line' or 'circle' with exactly 2 points [{time, price}], or a 'note' "
                         "with 1 point and text")
    k = _key(loader.bot_id(loader.get(bot)), symbol, day)
    pts = [{"time": int(p["time"]), "price": round(float(p["price"]), 4)} for p in points]
    return journal.add("drawings", {**k, "kind": kind, "points": pts, "note": note[:500]})


def drawings_for_claude(bot: str | None = None, symbol: str | None = None, day: str | None = None) -> list[dict]:
    """Drawings + what is under them (time span, price span, the bot's decisions there), in New York time."""
    rows = journal.find("drawings", bot=loader.bot_id(loader.get(bot)) if bot else None,
                        symbol=symbol.upper() if symbol else None, day=day)
    cache, out = {}, []
    for r in rows[-50:]:
        (a, b) = r["points"]
        if r["kind"] == "circle":     # stored as two opposite corners of the box around the circle
            t0, t1 = sorted((a["time"], b["time"])); p0, p1 = sorted((a["price"], b["price"]))
        else:
            t0, t1, p0, p1 = a["time"], b["time"], a["price"], b["price"]
        hm = lambda x: datetime.fromtimestamp(x, timezone.utc).strftime("%H:%M")   # noqa: E731  (chart time is already ET)
        item = {"id": r["id"], "kind": r["kind"], "note": r.get("note", ""), "bot": r["bot"], "symbol": r["symbol"],
                "day": r["day"], "saved_at": r["saved_at"]}
        if r["kind"] == "line":
            item["line"] = {"from": {"time": hm(t0), "price": p0}, "to": {"time": hm(t1), "price": p1},
                            "flat": abs(p1 - p0) < 1e-9 or abs(p1 - p0) / p0 < 0.0005}
        else:
            item["circle"] = {"from_time": hm(t0), "to_time": hm(t1), "price_low": p0, "price_high": p1}
        ck = (r["bot"], r["symbol"], r["day"])
        try:
            st = cache.get(ck) or cache.setdefault(ck, build(*ck))
            lo, hi = min(t0, t1), max(t0, t1)
            under = [c for c in st["candles"] if lo <= c["time"] <= hi]
            if under:
                item["candles_under"] = {"count": len(under), "open": under[0]["open"], "close": under[-1]["close"],
                                         "high": max(c["high"] for c in under), "low": min(c["low"] for c in under)}
            kinds = [st["reasons"][str(c["time"])] for c in under if str(c["time"]) in st["reasons"]]
            item["bot_did_there"] = sorted({x["reason"] for x in kinds if x["kind"] in ("entry", "exit", "vetoed")}) \
                or (sorted({x["reason"] for x in kinds})[:3])
            item["trades_touching"] = [t["id"] for t in st["trades"] + st["vetoed"]
                                       if t.get("t_in", t.get("t")) <= hi and t.get("t_out", t.get("t")) >= lo]
        except Exception as e:  # data unavailable: still return the drawing itself
            item["context_error"] = str(e)
        out.append(item)
    return out


# ---------- the localhost server ----------
_server: ThreadingHTTPServer | None = None
_srv_lock = threading.Lock()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):           # never print (the MCP server talks over stdout)
        pass

    def _host_ok(self) -> bool:          # blocks other websites from reading/writing your journal (DNS rebinding, CSRF)
        port = self.server.server_address[1]
        ok = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in ok:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in {f"http://{h}" for h in ok}

    def _send(self, code: int, body, ctype="application/json"):
        raw = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "SAMEORIGIN")              # other sites can't frame a page (clickjacking)
        self.send_header("Content-Security-Policy", "frame-ancestors 'self'")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    # ---- Studio's console (Claude panel + terminal): stricter than the other routes, see console.py ----
    def _console_refused(self, token: str | None) -> str | None:
        from . import console
        return console.allowed(self.client_address[0], self.headers.get("Host"), self.headers.get("Origin"), token,
                               self.server.server_address[1])

    def _console_get(self, u, q):
        from . import console
        why = self._console_refused(q.get("t") if u.path == "/api/console/term" else self.headers.get("X-BotScope-Token"))
        if why:
            return self._send(403, {"error": f"forbidden: {why}"})
        if u.path == "/api/console/term":           # (status is a POST: browsers send no Origin on same-origin GETs)
            return self._terminal(q)
        return self._send(404, {"error": "not found"})

    def _terminal(self, q):
        """A WebSocket to a shell in a local pty. One shell per socket; it ends when the socket closes."""
        from . import console
        if not console.STATE["on"]:
            return self._send(403, {"error": "the Claude panel is off: switch it on in Studio settings first"})
        key = self.headers.get("Sec-WebSocket-Key")
        if (self.headers.get("Upgrade", "").lower() != "websocket" or not key
                or self.headers.get("Sec-WebSocket-Version") != "13"):
            return self._send(400, {"error": "a WebSocket is needed here"})
        self.protocol_version = "HTTP/1.1"          # browsers refuse an HTTP/1.0 upgrade
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", console.ws_accept(key))
        self.end_headers()
        self.close_connection = True
        lock = threading.Lock()

        def send(data: bytes | None, op: int = 2):
            with lock:
                self.connection.sendall(console.ws_frame(b"" if data is None else data, 8 if data is None else op))
                if data is None:                     # the shell ended: stop reading too, so this thread ends
                    try:
                        self.connection.shutdown(socket.SHUT_RD)
                    except OSError:
                        pass

        try:
            term = console.Terminal(send, int(q.get("cols") or 100), int(q.get("rows") or 30))
        except (OSError, PermissionError, ValueError) as e:
            send(say(e).encode(), 1); send(None)
            return
        try:
            while not term.closed:
                f = console.ws_read(self.rfile)
                if f is None or f[0] == 8:
                    break
                if f[0] in (1, 2):
                    term.handle(f[1])
                elif f[0] == 9:
                    send(f[1], 10)
        except OSError:
            pass
        finally:
            term.close()

    def _console_post(self, path):
        from . import console
        why = self._console_refused(self.headers.get("X-BotScope-Token"))
        if why:
            return self._send(403, {"error": f"forbidden: {why}"})
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self._send(403, {"error": "forbidden"})
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 100_000)) or b"{}")
            if path == "/api/console/status":
                return self._send(200, console.status())
            if path == "/api/console/switch":
                return self._send(200, console.switch(bool(body.get("on")), bool(body.get("confirm"))))
            if path != "/api/console/chat":
                return self._send(404, {"error": "not found"})
            console.need_on()
            args = (str(body.get("prompt", "")), body.get("session") or None, body.get("tab"), body.get("bot"))
            console.chat_command(args[1])            # bad session / no claude: a plain 400 before streaming starts
        except PermissionError as e:
            return self._send(403, {"error": say(e)})
        except (KeyError, ValueError, RuntimeError, json.JSONDecodeError) as e:
            return self._send(400, {"error": say(e)})
        self.send_response(200)                      # one JSON event per line, as Claude answers
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def write(ev):
            self.wfile.write((json.dumps(ev) + "\n").encode())
            self.wfile.flush()
        try:
            console.chat(*args, write=write)
        except (BrokenPipeError, ConnectionResetError):
            pass                                     # the page pressed Stop or went away: Claude was stopped
        except (PermissionError, ValueError, RuntimeError, OSError) as e:
            try:
                write({"type": "error", "text": say(e)}); write({"type": "end", "code": 1})
            except OSError:
                pass

    def _setup_post(self, path):
        """Get started: setup status, saving keys, the first import. Keys are secrets, so these routes need what the
        console needs: this computer, the exact host and origin, and this launch's token."""
        from . import setup_guide
        why = self._console_refused(self.headers.get("X-BotScope-Token"))
        if why:
            return self._send(403, {"error": f"forbidden: {why}"})
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self._send(403, {"error": "forbidden"})
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 10_000)) or b"{}")
            if path == "/api/setup/status":
                return self._send(200, setup_guide.status(bool(body.get("fresh"))))
            if path == "/api/setup/keys":
                return self._send(200, setup_guide.save_alpaca(str(body.get("api_key", ""))[:200],
                                                               str(body.get("secret", ""))[:200]))
            if path == "/api/setup/optional":
                return self._send(200, setup_guide.save_optional(str(body.get("name", "")), str(body.get("value", ""))[:200]))
            if path == "/api/setup/custom":
                return self._send(200, setup_guide.save_custom(str(body.get("name", ""))[:60], str(body.get("value", ""))[:600]))
            if path == "/api/setup/custom_remove":
                return self._send(200, setup_guide.remove_custom(str(body.get("name", ""))[:60]))
            if path == "/api/setup/import":
                return self._send(200, setup_guide.import_alpaca())
        except (KeyError, ValueError, RuntimeError, json.JSONDecodeError) as e:
            return self._send(400, {"error": say(e)})
        return self._send(404, {"error": "not found"})

    def _factory_research(self):
        """The strategy factory with research by your own Claude Code: the console's rules (this computer, the exact
        host and origin, this launch's token) and the Claude panel switched on."""
        from . import console
        why = self._console_refused(self.headers.get("X-BotScope-Token"))
        if why or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self._send(403, {"error": f"forbidden: {why or 'JSON only'}"})
        if not console.STATE["on"]:
            return self._send(403, {"error": "Research runs your own Claude Code, so the Claude panel must be switched "
                                             "on (Studio settings). Or run the factory with the textbook templates.",
                                    "offer": "templates"})
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 10_000)) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "bad request"})
        return self._send(200, factory_run(str(body.get("goal", ""))[:200], research=True))

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path.startswith("/api/console/"):
            return self._console_get(u, q)
        if not self._host_ok():
            return self._send(403, {"error": "forbidden"})
        try:
            if u.path == "/":
                return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/view":
                if q.get("span") and q["span"] != "1d":
                    return self._send(200, build_span(q.get("bot", ""), q.get("symbol"), q.get("day"), q["span"]))
                return self._send(200, build(q.get("bot", ""), q.get("symbol"), q.get("day")))
            if u.path == "/zoom":
                return self._send(200, PAGE.with_name("zoom.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/zoom":
                from . import zoom
                return self._send(200, zoom.stack(q.get("symbol", "SPY"), q.get("day", ""), q.get("t") or None))
            if u.path == "/studio":                   # the console token is written into this page only
                from . import console
                html = PAGE.with_name("studio.html").read_text().replace('/*TOKEN*/""/*/TOKEN*/', json.dumps(console.TOKEN))
                return self._send(200, html.encode(), "text/html; charset=utf-8")
            if u.path == "/flight":
                return self._send(200, PAGE.with_name("flight.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/flight":
                from . import flight
                return self._send(200, flight.flight(q.get("bot", "first_hour_breakout"), q.get("symbol"), q.get("day")))
            if u.path == "/api/optimizer":
                from . import journal
                return self._send(200, list(reversed(journal.load("optimizer")))[:5])
            if u.path.startswith("/api/optimizer/"):          # Optimizer tab: a bot's number settings, the run in progress
                return self._send(200, optimizer_info(u.path, q.get("bot", "")))
            if u.path == "/api/factory/progress":
                from . import strategy_factory
                return self._send(200, dict(strategy_factory.PROGRESS))
            if u.path == "/api/imported/trades":       # one strategy's trades (My bots: click a strategy)
                from . import imports
                ts = imports.trades(q.get("import", ""), q.get("bot") or None)
                return self._send(200, sorted(ts, key=lambda t: t.get("opened") or ""))
            if u.path == "/api/imported":
                from . import imports
                out = imports.summary()
                if q.get("orders"):
                    try:
                        out["orders"] = imports.orders(q.get("bot") or None, int(q.get("days") or 30))
                    except Exception as e:      # demo mode / no keys: the summary still shows
                        out["orders_error"] = str(e)
                return self._send(200, out)
            if u.path == "/api/friends":
                from . import friends
                return self._send(200, friends.listing())
            if u.path == "/api/friends/compare":
                from . import friends
                return self._send(200, friends.compare(q.get("bot", ""), q.get("friend", ""), q.get("name") or "me"))
            if u.path == "/api/phantom":
                from . import phantom
                return self._send(200, phantom.report())
            if u.path == "/api/factory":
                from . import journal
                return self._send(200, list(reversed(journal.load("factory_runs")))[:10])
            if u.path == "/api/mode":
                from . import demo
                return self._send(200, {"demo": demo.active(), "badge": demo.BADGE, "how": demo.HOW_TO_SWITCH})
            if u.path == "/theme.js":
                from . import demo
                mode = json.dumps({"demo": demo.active(), "badge": demo.BADGE, "how": demo.HOW_TO_SWITCH})
                js = PAGE.with_name("theme.js").read_text().replace("/*DEMO*/null/*/DEMO*/", mode)
                return self._send(200, js.encode(), "text/javascript; charset=utf-8")
            if u.path == "/i18n.js":
                return self._send(200, PAGE.with_name("i18n.js").read_bytes(), "text/javascript; charset=utf-8")
            if u.path == "/start.js":
                return self._send(200, PAGE.with_name("start.js").read_bytes(), "text/javascript; charset=utf-8")
            if u.path == "/optimizer.js":
                return self._send(200, PAGE.with_name("optimizer.js").read_bytes(), "text/javascript; charset=utf-8")
            if u.path == "/factory.js":
                return self._send(200, PAGE.with_name("factory.js").read_bytes(), "text/javascript; charset=utf-8")
            if u.path == "/friends.js":
                return self._send(200, PAGE.with_name("friends.js").read_bytes(), "text/javascript; charset=utf-8")
            if u.path == "/signals.js":
                return self._send(200, PAGE.with_name("signals.js").read_bytes(), "text/javascript; charset=utf-8")
            if u.path == "/api/signals":                # your strategies' rules on today's bars so far (read-only)
                from . import signals
                if not _whatif_lock.acquire(blocking=False):      # one replay at a time: show the last scan meanwhile
                    got = signals.last()
                    if got is not None:
                        return self._send(200, {**got, "busy": "another replay is going: these are the last signals"})
                    if not _whatif_lock.acquire(timeout=180):        # the first scan of the day: wait for it, then share it
                        return self._send(400, {"error": "another replay is already going; try again in a minute"})
                    if signals.last() is not None:
                        _whatif_lock.release()
                        return self._send(200, signals.last())
                try:
                    return self._send(200, signals.scan(q.get("examples") == "1", int(q.get("window") or signals.WINDOW_MIN)))
                finally:
                    _whatif_lock.release()
            if u.path == "/tour.js":
                return self._send(200, PAGE.with_name("tour.js").read_bytes(), "text/javascript; charset=utf-8")
            if u.path == "/desk":
                return self._send(200, PAGE.with_name("desk.html").read_bytes(), "text/html; charset=utf-8")
            if u.path.startswith("/api/desk/"):
                from . import desk
                return self._send(200, desk.panel(u.path.rsplit("/", 1)[1], q))
            if u.path == "/clip":
                return self._send(200, PAGE.with_name("clip.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/clip":
                from . import clip
                return self._send(200, clip.clip_data(q.get("bot", ""), q.get("symbol"), q.get("day"), q.get("trade")))
            if u.path == "/weather":
                return self._send(200, PAGE.with_name("weather.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/weather_calendar":
                from . import demo, weather
                return self._send(200, demo.label(weather.calendar_days(int(q.get("months") or 6))))
            if u.path == "/parent":
                return self._send(200, PAGE.with_name("parent.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/parent":
                from . import parent
                return self._send(200, __import__("botscope.demo", fromlist=["x"]).label(parent.summary()))
            if u.path == "/preflight":
                return self._send(200, PAGE.with_name("preflight.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/preflight":
                from . import preflight
                return self._send(200, preflight.today_list(events=None if q.get("events") == "1" else []))
            if u.path == "/playground":
                return self._send(200, PAGE.with_name("playground.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/playground":
                from . import playground
                return self._send(200, playground.play(q.get("bot", ""), [x for x in q.get("off", "").split("|") if x],
                                                       q.get("side", "both")))
            if u.path == "/api/eventdays":
                from . import eventdays
                return self._send(200, eventdays.event_days(loader.bot_id(loader.get(q.get("bot", "")))))
            if u.path == "/label":
                return self._send(200, PAGE.with_name("label.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/label":
                from . import label
                return self._send(200, label.build(q.get("bot", "")))
            if u.path == "/api/whatif":
                from . import whatif
                cls = loader.get(q.get("bot", ""))
                got = None if q.get("refresh") == "1" else whatif.saved(loader.bot_id(cls))
                if got is None:
                    if not _whatif_lock.acquire(blocking=False):
                        return self._send(400, {"error": "a what-if run is already going; try again in a minute"})
                    try:
                        got = whatif.grid(cls)
                    finally:
                        _whatif_lock.release()
                return self._send(200, got)
            if u.path == "/api/timemap":
                from . import timemap
                if not _whatif_lock.acquire(blocking=False):
                    return self._send(400, {"error": "another replay is already going; try again in a minute"})
                try:
                    return self._send(200, timemap.time_map(loader.get(q.get("bot", ""))))
                finally:
                    _whatif_lock.release()
            if u.path == "/api/alike":
                from . import alike
                if not _whatif_lock.acquire(blocking=False):
                    return self._send(400, {"error": "another replay is already going; try again in a minute"})
                try:
                    return self._send(200, alike.days_like_today(loader.get(q.get("bot", "")), q.get("symbol")))
                finally:
                    _whatif_lock.release()
            if u.path == "/map":
                return self._send(200, PAGE.with_name("map.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/map":
                from . import projmap
                return self._send(200, projmap.build())
            if u.path == "/api/teach":
                from . import teach
                return self._send(200, teach.teach_me(q.get("bot", ""), q.get("symbol"), q.get("day")))
            if u.path == "/api/veto_scorecard":
                return self._send(200, veto_scorecard(q.get("bot") or None))
            if u.path == "/api/bots":
                bots, _ = loader.load_all()
                return self._send(200, [{"id": k, "name": c.name, "symbols": c.symbols, "mine": loader.is_mine(c)}
                                        for k, c in bots.items()])
        except (KeyError, ValueError, RuntimeError) as e:
            return self._send(400, {"error": say(e)})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path.startswith("/api/console/"):
            return self._console_post(urlparse(self.path).path)
        if urlparse(self.path).path.startswith("/api/setup/"):
            return self._setup_post(urlparse(self.path).path)
        if urlparse(self.path).path == "/api/factory/research":
            return self._factory_research()
        if (self._host_ok() and urlparse(self.path).path == "/api/clip/save"
                and self.headers.get("Content-Type", "").split(";")[0] == "video/webm"):   # not a simple request: no cross-site posts
            from . import clip
            n = int(self.headers.get("Content-Length", 0))
            if n > clip.MAX_BYTES:
                return self._send(413, {"error": "clip too big (8 MB max)"})
            try:
                name = parse_qs(urlparse(self.path).query).get("name", ["clip"])[0]
                return self._send(200, clip.save(name, self.rfile.read(n)))
            except ValueError as e:
                return self._send(400, {"error": say(e)})
        if not self._host_ok() or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self._send(403, {"error": "forbidden"})
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 100_000)) or b"{}")
            base = (body.get("bot", ""), body.get("symbol", ""), body.get("day", ""))
            path = urlparse(self.path).path
            if path == "/api/preflight":
                from . import preflight
                return self._send(200, preflight.answer(body.get("choices") or {}))
            if path == "/api/flight/score":
                from . import flight
                return self._send(200, flight.save_score(body))
            if path in ("/api/friends/code", "/api/friends/check", "/api/friends/add", "/api/friends/remove"):
                from . import friends      # read-only cards: numbers in, numbers out; nothing is run or traded
                if path.endswith("/code"):
                    return self._send(200, friends.my_code(str(body.get("bot", "")), str(body.get("name") or "me")[:30],
                                                           bool(body.get("include_rules"))))
                if path.endswith("/check"):                    # preview a pasted code; nothing saved
                    return self._send(200, {"card": friends.decode(str(body.get("code", ""))[:friends.MAX_CODE + 1000])})
                if path.endswith("/add"):
                    return self._send(200, friends.add(str(body.get("code", ""))[:friends.MAX_CODE + 1000]))
                return self._send(200, friends.remove(str(body.get("id", ""))))
            if path == "/api/phantom":
                from . import phantom
                return self._send(200, phantom.start(str(body.get("run", "")), [str(c)[:80] for c in body.get("candidates", [])][:5]))
            if path == "/api/optimizer/run":
                return self._send(200, optimizer_run(str(body.get("bot", "")), body.get("a") or None, body.get("b") or None))
            if path == "/api/factory":
                return self._send(200, factory_run(str(body.get("goal", ""))[:200]))
            if path == "/api/stop":
                from . import guard
                return self._send(200, guard.stop_everything(body.get("reason", "STOP button on the chart")))
            if path == "/api/resume":
                from . import guard
                return self._send(200, guard.resume(bool(body.get("confirm"))))
            if path == "/api/veto":
                return self._send(200, veto(*base, body.get("trade_id"), body.get("reason", "")))
            if path == "/api/undo_veto":
                return self._send(200, undo_veto(*base, body["trade_id"]))
            if path == "/api/move":
                return self._send(200, move_lines(*base, body.get("trade_id"), body.get("stop"), body.get("target"),
                                                  body.get("scope"), bool(body.get("confirm"))))
            if path == "/api/quiz":
                return self._send(200, quiz_score(*base, body.get("hits", -1), body.get("n", 0)))
            if path == "/api/drawings":
                return self._send(200, add_drawing(*base, body.get("kind", ""), body.get("points", []), body.get("note", "")))
            if path == "/api/drawings/delete":
                return self._send(200, {"removed": journal.remove("drawings", body.get("id", ""))})
        except (KeyError, ValueError, RuntimeError, json.JSONDecodeError) as e:
            return self._send(400, {"error": say(e)})
        self._send(404, {"error": "not found"})


def _warm_imports() -> None:
    """Import the Alpaca SDK once before the server's threads start: the desk loads ~10 panels at once, and parallel
    first imports of the same module can raise Python's import _DeadlockError (seen on a cold desk load)."""
    try:
        import alpaca.data.enums, alpaca.data.historical, alpaca.data.requests, alpaca.data.timeframe  # noqa: F401,E401
    except Exception:
        pass        # no SDK = the panels already say so on their own


def factory_run(goal: str, research: bool = False) -> dict:
    """Studio's Factory tab: the same strategy factory as the tool, one backtest at a time across Claude and pages.
    research=True: your own Claude Code researches the 5 candidates first (or the run says why it couldn't)."""
    from . import server, strategy_factory
    if not server._one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        out = strategy_factory.run(goal, research=research)
        return {k: out[k] for k in ("run", "tried", "kept", "dropped", "markdown", "research")}
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        server._one_backtest.release()


def optimizer_info(path: str, bot_id: str) -> dict:
    """GET /api/optimizer/progress (cells done of total) and /api/optimizer/settings?bot= (what the tab can vary)."""
    from . import optimizer
    if path.endswith("/progress"):
        return dict(optimizer.PROGRESS)
    if not path.endswith("/settings"):
        raise KeyError(path)
    cls = loader.get(bot_id)
    nums = optimizer.number_settings(cls)
    out = {"bot": cls.name, "settings": nums, "today": {k: cls.params[k] for k in nums}, "default": []}
    try:
        out["default"] = list(optimizer.pick_settings(cls, None, None))
    except ValueError as e:                       # fewer than two number settings: nothing to map
        out["error"] = say(e)
    return out


def optimizer_run(bot_id: str, a: str | None, b: str | None) -> dict:
    """Studio's Optimizer tab: the same honest optimizer as the tool, saved, one backtest at a time."""
    from . import optimizer, server
    if not server._one_backtest.acquire(blocking=False):
        p = optimizer.PROGRESS
        return {"error": "another backtest is already running" + (f" ({p['bot']}: {p['done']} of {p['total']} cells)"
                                                                   if p.get("total") else "") + "; try again when it finishes"}
    try:
        out = optimizer.optimize(loader.get(bot_id), a, b, save=True)
        return {k: out[k] for k in ("bot", "settings", "cells_tried", "verdict")}
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        server._one_backtest.release()


def ensure_server() -> str:
    """Start the page server once (127.0.0.1 only) and return its base URL."""
    global _server
    with _srv_lock:
        if _server is None:
            for port in range(FIRST_PORT, FIRST_PORT + 20):
                try:
                    _server = ThreadingHTTPServer((HOST, port), _Handler)
                    break
                except OSError:
                    continue
            else:
                raise RuntimeError("no free port between 8765 and 8784")
            _warm_imports()
            threading.Thread(target=_server.serve_forever, daemon=True, name="botscope-view").start()
        return f"http://{HOST}:{_server.server_address[1]}"


def open_view(bot: str, symbol: str | None = None, day: str | None = None) -> dict:
    st = build(bot, symbol, day)
    url = ensure_server() + "/?" + urlencode({"bot": st["bot"]["id"], "symbol": st["symbol"], "day": st["day"]})
    return {"url": url, "bot": st["bot"]["name"], "symbol": st["symbol"], "day": st["day"], "live": st["live"],
            "account": st["account"], "data_source": st["source"],
            "trades": [{k: t[k] for k in ("id", "side", "entry", "stop", "target", "exit", "why_out", "r")} for t in st["trades"]],
            "vetoed": [v["id"] for v in st["vetoed"]],
            "how_to_use": "Click a candle: why the bot did or didn't trade. Drag the red/green lines to move the stop/target. "
                          "Pick Line or Circle to draw; Claude reads drawings with get_chart_drawings."}


if __name__ == "__main__":    # python -m botscope.view [bot] [symbol] [day]  -> serve until Ctrl+C
    import sys
    info = open_view(*(sys.argv[1:] or ["first_hour_breakout"]))
    print(info["url"], flush=True)
    threading.Event().wait()
