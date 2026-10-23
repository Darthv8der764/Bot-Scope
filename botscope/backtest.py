"""Quick honest backtest: one bot, a short window, real costs, and results split into TUNED days (the dates the
bot's settings were picked on, where it is expected to look good) vs UNTESTED days (the real test).

Fills: entries at the close of the bar that triggered them. Stops fill at the stop (or the open, if the bar gapped
through it) plus the measured stop slippage; if one bar hits both stop and target, the stop counts (worst case).
Intraday bots are closed at the last bar of the day. Not financial advice: past results do not predict the future.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from . import benchmark, confidence, data, journal, loader
from .bot import Bot, Entry, Exit, NoTrade, Position, View

COSTS = json.loads((Path(__file__).with_name("costs.json")).read_text())
QUICK_DAYS = 30          # calendar days per sample (tuned + untested) in a quick run
MAX_SYMBOLS = 5
TIGHT_MOVES_R = 10.0     # ...and warn when those trades move the total by this much, however few they are
TIGHT_STOP_PCT = 0.05    # a stop under 0.05% of price, or closer than the trade's own costs: R per trade blows up


@dataclass
class Trade:
    symbol: str
    day: str
    side: str
    entry: float
    exit: float
    stop: float
    why_in: str
    why_out: str
    r: float             # result in R (multiples of the risk), after costs
    pct: float           # result as % of the position, after costs
    cost_pct: float
    t_in: str = ""       # entry bar time (ISO)
    t_out: str = ""      # exit bar time (ISO)
    target: float | None = None
    risk_pct: float = 0.0  # entry-to-stop distance as % of the entry (so R can be turned back into %)
    ghost: bool = False    # a near miss played out on paper, not a trade the bot took
    slip_pct: float = 0.0  # extra slippage paid on a stop exit, % of the position (already inside pct)
    blocked_by: str = ""   # ghosts: the bot rule (NoTrade reason) that blocked this near miss


def _close(pos: Position, px: float, why: str, cost: dict, stopped: bool, sym: str, day: date, t_out=None) -> Trade:
    d = 1 if pos.side == "long" else -1
    slip = cost["stop_extra_bps"] if stopped else 0.0
    px = px * (1 - d * slip / 1e4)
    cost_pct = (cost["entry_bps"] + cost["exit_bps"]) / 1e4
    pct = d * (px - pos.entry_price) / pos.entry_price - cost_pct
    risk = abs(pos.entry_price - pos.stop) / pos.entry_price
    day = pos.entry_time.date() if pos.entry_time else day      # daily bots: the entry day, not the window's end
    return Trade(sym, str(day), pos.side, pos.entry_price, round(px, 4), pos.stop, pos.reason, why,
                 round(pct / risk, 3) if risk else 0.0, round(pct * 100, 4), round(cost_pct * 100, 4),
                 pos.entry_time.isoformat(), t_out.isoformat() if t_out else "",
                 round(pos.target, 4) if pos.target is not None else None, round(risk * 100, 4),
                 slip_pct=round(slip / 100, 4))


def receipt(t: Trade, notional: float = 10_000) -> dict:
    """A trade's receipt: why in, why out, and what costs and slippage took, in dollars on a paper position."""
    shares = int(notional // t.entry) if t.entry else 0
    usd = lambda pct: round(pct / 100 * notional, 2)
    net = usd(t.pct)
    return {"position_usd": notional, "shares_about": shares, "why_in": t.why_in, "why_out": t.why_out,
            "price_move_usd": round(net + usd(t.cost_pct) + usd(t.slip_pct), 2), "costs_usd": -usd(t.cost_pct),
            "slippage_usd": -usd(t.slip_pct), "net_usd": net, "r": t.r,
            "note": ("Costs = the spread and fees in costs.json, both sides. Slippage = the extra a stop order "
                     "usually fills worse than the stop price. Both are estimates from real paper fills.")}


def _check_exit(bot: Bot, pos: Position, b, view: View, last_bar: bool, close_at_end: bool, cost: dict, sym: str,
                day: date) -> Trade | None:
    """Stop, then target, then the bot's own exit(), then the end of the day/window. None = keep holding."""
    d = 1 if pos.side == "long" else -1
    hit_stop = b.l <= pos.stop if d == 1 else b.h >= pos.stop
    hit_tgt = pos.target is not None and (b.h >= pos.target if d == 1 else b.l <= pos.target)
    if hit_stop:
        fill = min(b.o, pos.stop) if d == 1 else max(b.o, pos.stop)
        return _close(pos, fill, "stop hit", cost, True, sym, day, b.t)
    if hit_tgt:
        fill = max(b.o, pos.target) if d == 1 else min(b.o, pos.target)
        return _close(pos, fill, "target hit", cost, False, sym, day, b.t)
    ex = bot.exit(view, pos)
    if isinstance(ex, Exit) or (last_bar and (bot.flat_by_close or close_at_end)):
        why = ex.reason if isinstance(ex, Exit) else "end of day" if bot.flat_by_close else "end of test window"
        return _close(pos, b.c, why, cost, False, sym, day, b.t)
    return None


def play_out(bot: Bot, sym: str, day: date, bs: list, i: int, entry: Entry, cost: dict, ind_full: dict,
             close_at_end: bool = False, history: list | None = None) -> tuple[Trade | None, int]:
    """Enter at the close of bar i and follow the normal exit rules. Used for ghost trades. (trade, exit index);
    trade is None if the data ends before the trade closes."""
    pos = Position(entry.side, bs[i].c, bs[i].t, entry.stop, entry.target, entry.reason)
    for j in range(i + 1, len(bs)):
        view = View(sym, bs[:j + 1], {k: v[:j + 1] for k, v in ind_full.items()}, history=history or [])
        done = _check_exit(bot, pos, bs[j], view, j == len(bs) - 1, close_at_end, cost, sym, day)
        if done:
            return done, j
    return None, len(bs)


def needs_history(bot) -> int:
    """How many earlier sessions an intraday bot asked for (history_days); daily bots already see them in view.bars."""
    return int(getattr(bot, "history_days", 0) or 0) if bot.timeframe != "1Day" else 0


def earlier_sessions(sym: str, day: date, timeframe: str, n: int, fetch=None) -> list:
    """The n finished sessions before `day`, oldest first, flattened: what view.history holds."""
    fetch = fetch or data.bars
    raw, _ = data.clean(fetch(sym, day - timedelta(days=n * 7 // 5 + 6), day - timedelta(days=1), timeframe, "sip"))
    ss = data.sessions(raw, timeframe, data.is_crypto(sym))
    return [b for d in sorted(ss)[-n:] if d < day for b in ss[d]]


def run_day(bot: Bot, sym: str, day: date, bs: list, cost: dict, on_entry=None,
            trace: list | None = None, close_at_end: bool = False,
            ghosts: list | None = None, history: list | None = None) -> tuple[list[Trade], list[str]]:
    """Play one day bar by bar. Optional `on_entry(view, entry)` may return a changed Entry (a moved stop/target) or
    NoTrade (a veto); the slot still counts as used. Optional `trace` gets one dict per bar saying what the bot
    decided and why (the chart's "why not here?" click). Optional `ghosts` gets the near misses (NoTrade.almost)
    played out on paper; one ghost at a time, and none while the bot is in a real trade. `history`: the earlier
    sessions for view.history; when it isn't passed and the bot asks for history_days, it's downloaded here, so every
    caller (backtest, chart, luck meter, paper log...) gives the bot the same view."""
    ind_full = bot.indicators(bs)
    trades, problems, pos, n_in = [], [], None, 0
    if history is None:
        history = []
        if (n := needs_history(bot)):
            try:
                history = earlier_sessions(sym, day, bot.timeframe, n)
            except Exception as e:      # no data or no keys: the bot sees no history and it's said
                problems.append(f"{sym} {day}: earlier days for view.history unavailable ({type(e).__name__})")
    ghost_busy_until = -1
    note = trace.append if trace is not None else (lambda _: None)
    for i, b in enumerate(bs):
        last_bar = i == len(bs) - 1
        if i and b.t.date() != bs[i - 1].t.date():
            n_in = 0                               # a new day: the per-day trade limit starts over
        view = View(sym, bs[:i + 1], {k: v[:i + 1] for k, v in ind_full.items()}, n_in, history)
        if pos:
            done = _check_exit(bot, pos, b, view, last_bar, close_at_end, cost, sym, day)
            if done:
                trades.append(done); pos = None
                note({"t": b.t, "kind": "exit", "reason": f"exit: {done.why_out} at {done.exit:.2f} ({done.r:+.2f}R after costs)"})
            else:
                tgt = "none" if pos.target is None else f"{pos.target:.2f}"
                note({"t": b.t, "kind": "holding", "reason": f"in a {pos.side} trade since {pos.entry_time:%H:%M}: "
                                                             f"stop {pos.stop:.2f}, target {tgt}"})
            continue
        if last_bar and (bot.flat_by_close or close_at_end):
            note({"t": b.t, "kind": "no_trade", "reason": "last bar of the day: no new trades"}); continue
        if n_in >= bot.max_trades_per_day:
            note({"t": b.t, "kind": "no_trade", "reason": f"already used today's {bot.max_trades_per_day} trade(s)"}); continue
        dec = bot.entry(view)
        if isinstance(dec, Entry):
            bad_side = bot.sides != "both" and dec.side != bot.sides
            bad_stop = (dec.stop >= b.c) if dec.side == "long" else (dec.stop <= b.c)
            if bad_side or bad_stop:
                problems.append(f"{sym} {day} {b.t:%H:%M}: rejected entry ({'wrong side' if bad_side else 'stop on the wrong side'})")
                note({"t": b.t, "kind": "rejected", "reason": "BotScope rejected the bot's entry: "
                      + ("wrong side" if bad_side else "stop on the wrong side")})
                continue
            if on_entry:
                changed = on_entry(view, dec)
                if isinstance(changed, NoTrade):
                    n_in += 1
                    note({"t": b.t, "kind": "vetoed", "reason": changed.reason, "side": dec.side, "price": b.c,
                          "stop": dec.stop, "target": dec.target, "why_in": dec.reason})
                    continue
                dec = changed
            pos = Position(dec.side, b.c, b.t, dec.stop, dec.target, dec.reason)
            n_in += 1
            note({"t": b.t, "kind": "entry", "reason": f"{dec.side.upper()} at {b.c:.2f}: {dec.reason}",
                  "side": dec.side, "stop": dec.stop, "target": dec.target})
        elif isinstance(dec, NoTrade):
            row = {"t": b.t, "kind": "no_trade", "reason": dec.reason}
            a = dec.almost
            if isinstance(a, Entry) and i > ghost_busy_until and \
                    ((a.stop < b.c) if a.side == "long" else (a.stop > b.c)):
                g, j = play_out(bot, sym, day, bs, i, a, cost, ind_full, close_at_end, history)
                if g:
                    g.ghost = True
                    g.blocked_by = dec.reason
                    ghost_busy_until = j
                    row["ghost"] = {"side": a.side, "stop": a.stop, "target": a.target, "r": g.r, "why_out": g.why_out}
                    row["reason"] += f" (ghost: a {a.side} here would have made {g.r:+.2f}R)"
                    if ghosts is not None:
                        ghosts.append(g)
            note(row)
        else:
            problems.append(f"{bot.name}.entry() returned {type(dec).__name__}, expected Entry or NoTrade")
            break
    return trades, problems


def no_peek_check(bot: Bot, bs: list) -> str | None:
    """Indicators must not look ahead: values for the first k bars must not change when later bars exist."""
    full = bot.indicators(bs)
    for k in (len(bs) // 4, len(bs) // 2, len(bs) - 1):
        if k < 1:
            continue
        part = bot.indicators(bs[:k])
        for name, vals in part.items():
            if list(vals) != list(full[name][:k]):
                return f"indicator '{name}' changes when future bars are added (looks ahead)"
    return None


def _streak(rs):
    worst = cur = 0
    for r in rs:
        cur = cur + 1 if r <= 0 else 0
        worst = max(worst, cur)
    return worst


def _drawdown(rs):
    peak = eq = dd = 0.0
    for r in rs:
        eq += r; peak = max(peak, eq); dd = min(dd, eq - peak)
    return round(dd, 2)


def left_out(symbols: list[str]) -> str | None:
    """The note when a bot lists more symbols than a test runs on, so a shorter test never reads as the whole bot."""
    extra = list(dict.fromkeys(s.upper() for s in symbols))[MAX_SYMBOLS:]
    return (f"tested on the first {MAX_SYMBOLS} symbols only; left out: {', '.join(extra)}"
            if extra else None)


def summarize(trades: list[Trade], notional: float) -> dict:
    if not trades:
        return {"trades": 0}
    trades = sorted(trades, key=lambda t: t.t_out or t.t_in or t.day)   # streaks + drops in time order, not symbol order
    rs = [t.r for t in trades]
    wins = [t for t in trades if t.pct > 0]
    out = {"trades": len(trades), "wins": len(wins),   # a count, never a win %: see confidence for the verdict
          
           "avg_r": round(sum(rs) / len(rs), 3), "total_r": round(sum(rs), 2),
           "net_usd": round(sum(t.pct for t in trades) / 100 * notional, 2),
           "avg_usd_per_win": round(sum(t.pct for t in wins) / 100 * notional / len(wins), 2) if wins else 0.0,
           "costs_usd": round(sum(t.cost_pct for t in trades) / 100 * notional, 2),
           "worst_losing_streak": _streak(rs), "max_drawdown_r": _drawdown(rs)}
    gross = [(t.pct + t.cost_pct) / t.risk_pct for t in trades if t.risk_pct]
    if gross:                                          # what trading costs took out of the result
        out["before_costs_r"] = round(sum(gross), 2)
        out["costs_r"] = round(sum(gross) - sum(t.r for t in trades if t.risk_pct), 2)
        out["if_costs_doubled_r"] = round(out["total_r"] - out["costs_r"], 2)   # stress: pay the costs twice
    tight = [t for t in trades if t.risk_pct and t.risk_pct < max(TIGHT_STOP_PCT, t.cost_pct)]
    if tight:                                          # stops a few cents away: R per trade blows up, so say so
        out["tight_stop_trades"] = len(tight)
        out["without_tight_stops_r"] = round(sum(rs) - sum(t.r for t in tight), 2)
    if len(rs) >= 10:                                  # one-trade dependency: does it still work without its 3 best?
        out["without_best_3_r"] = round(sum(rs) - sum(sorted(rs)[-3:]), 2)
    if len(rs) >= 10:                                  # range of outcomes: reshuffle the trades 1,000 times
        rng = random.Random(7)
        n = len(rs)
        sims = sorted(sum(rng.choices(rs, k=n)) for _ in range(1000))
        out["total_r_range_5_50_95"] = [round(sims[50], 1), round(sims[500], 1), round(sims[950], 1)]
    return out


def tight_stops(u: dict) -> str | None:
    """The tight-stop warning when enough trades (3+ and 5%+) had a stop closer than their costs, or when those
    trades move the total by 10R or more (one 1-cent stop can read -464R), else None."""
    n = u.get("tight_stop_trades", 0)
    moved = abs((u.get("total_r") or 0) - (u.get("without_tight_stops_r") or 0))
    if not n or (n < max(3, u.get("trades", 0) * 0.05) and moved < TIGHT_MOVES_R):
        return None
    return (f"{n} trades had a stop closer than their own trading costs (or 0.05% of price), which inflates R "
            f"(without them {u['without_tight_stops_r']:+.1f}R; see docs/when-r-lies-tight-stops.md)")


def windows(bot_cls, days: int = QUICK_DAYS) -> list[tuple[str, date, date]]:
    yesterday = date.today() - timedelta(days=1)
    if not bot_cls.tuned_on:
        return [("untested", yesterday - timedelta(days=2 * days), yesterday)]
    t0, t1 = (date.fromisoformat(x) for x in bot_cls.tuned_on)
    tuned_end = min(t1, yesterday)
    return [("tuned", tuned_end - timedelta(days=days), tuned_end),
            ("untested", t0 - timedelta(days=days + 1), t0 - timedelta(days=1))]


def warmup_days(bot, floor: int = 0) -> int:
    """Calendar days of daily bars to fetch before a window so the bot's lookback (`lookback_days`, in trading days)
    is filled from the window's first day. Intraday bots: 0 (each session stands alone)."""
    if bot.timeframe != "1Day":
        return 0
    need = getattr(bot, "lookback_days", 0)
    return max(floor, -(-need * 365 // 250) + 10 if need else 0)


def run_window(bot: Bot, symbols: list[str], start: date, end: date, feed: str = "sip", fetch=None,
               on_entry=None, peek: dict | None = None,
               warmup_days: int = 0, filters: dict | None = None) -> tuple[list[Trade], list[Trade], list[str]]:
    """Every symbol over one date window: (trades, ghost trades, problems). `fetch(sym, start, end, timeframe, feed)`
    defaults to Alpaca (data.bars). Pass `peek={}` to run the no-peek check once (its result lands in peek['problem']).
    `warmup_days`: extra calendar days fetched before `start` so daily bots have history; trades entered during the
    warmup are not counted."""
    fetch = fetch or data.bars
    cost = COSTS[bot.asset]
    trades, ghosts, problems = [], [], []
    hist_n = needs_history(bot)
    extra = hist_n * 7 // 5 + 6 if hist_n else 0      # earlier sessions for view.history, fetched with the window
    for sym in symbols:
        try:
            raw = fetch(sym, start - timedelta(days=warmup_days + extra), end, bot.timeframe, feed)
        except RuntimeError:       # missing keys: stop and say so
            raise
        except Exception as e:     # one symbol without data never stops the rest
            problems.append(f"{sym} {start}..{end}: no data ({type(e).__name__}: {str(e)[:120]})")
            continue
        raw, bad = data.clean(raw)
        problems += [f"{sym}: {x}" for x in bad]
        ss = data.sessions(raw, bot.timeframe, data.is_crypto(sym))
        days = sorted(ss)
        for k, day in enumerate(days):
            bs = ss[day]
            hist = [b for d in days[max(0, k - hist_n):k] for b in ss[d]] if hist_n else []
            if hist_n and day < start - timedelta(days=warmup_days):
                continue                                   # fetched only as history for later days
            if peek is not None and "checked" not in peek and len(bs) > 20:
                peek["checked"] = True
                if (msg := no_peek_check(bot, bs)):
                    peek["problem"] = msg
            t, probs = run_day(bot, sym, day, bs, cost, on_entry or filter_hook(filters, sym),
                               close_at_end=bot.timeframe == "1Day", ghosts=ghosts, history=hist)
            trades += t
            problems += probs[:5]
    if warmup_days:
        trades = [t for t in trades if t.t_in[:10] >= str(start)]
        ghosts = [g for g in ghosts if g.t_in[:10] >= str(start)]
    trades.sort(key=lambda t: t.t_in); ghosts.sort(key=lambda t: t.t_in)
    return trades, ghosts, problems


def ghost_summary(ghosts: list[Trade]) -> dict:
    """Near misses the bot's filters blocked: if they would have made money, the filter may be costing you."""
    if not ghosts:
        return {"ghosts": 0}
    rs = [g.r for g in ghosts]
    total = round(sum(rs), 2)
    return {"ghosts": len(rs), "avg_r": round(total / len(rs), 3), "total_r": total,
            "verdict": ("the filters are saving you money: the blocked trades would have lost" if total < 0 else
                        "the filters are costing you: the blocked trades would have made money" if total > 0 else
                        "the blocked trades would have broken even")
                       + (" (fewer than 20 ghosts, so this could be luck)" if len(rs) < 20 else "")}


FILTERS = {"skip_side": "long|short", "skip_before": "HH:MM", "skip_after": "HH:MM", "skip_symbols": "[tickers]",
           "skip_weekdays": "[0=Mon..4=Fri]", "max_risk_pct": "skip trades whose stop is farther than this % away"}


def filter_hook(filters: dict | None, symbol: str):
    """An on_entry hook that skips entries matching simple rules (for testing rule ideas without editing the bot).
    Unknown keys raise ValueError so a typo can't silently test nothing."""
    if not filters:
        return None
    bad = set(filters) - set(FILTERS)
    if bad:
        raise ValueError(f"unknown filters {sorted(bad)}; known: {', '.join(FILTERS)}")
    from datetime import time as _t

    def hook(view: View, e: Entry):
        t = view.now.time()
        risk = abs(view.last.c - e.stop) / view.last.c * 100
        why = None
        if filters.get("skip_side") == e.side:
            why = f"rule idea: skip {e.side}s"
        elif filters.get("skip_before") and t < _t.fromisoformat(filters["skip_before"]):
            why = f"rule idea: no trades before {filters['skip_before']}"
        elif filters.get("skip_after") and t > _t.fromisoformat(filters["skip_after"]):
            why = f"rule idea: no trades after {filters['skip_after']}"
        elif symbol.upper() in {x.upper() for x in filters.get("skip_symbols", [])}:
            why = f"rule idea: skip {symbol}"
        elif view.now.weekday() in filters.get("skip_weekdays", []):
            why = f"rule idea: skip {view.now:%A}s"
        elif filters.get("max_risk_pct") and risk > float(filters["max_risk_pct"]):
            why = f"rule idea: stop too far ({risk:.2f}% > {filters['max_risk_pct']}%)"
        return NoTrade(why) if why else e
    return hook


def run(bot_cls, symbols: list[str] | None = None, days: int = QUICK_DAYS, notional: float = 10_000,
        feed: str = "sip", params: dict | None = None, fetch=None, filters: dict | None = None) -> dict:
    bot = bot_cls(**(params or {}))
    symbols_given = symbols
    symbols = [s.upper() for s in (symbols or bot.symbols)][:MAX_SYMBOLS]
    cost = COSTS[bot.asset]
    report = {"bot": bot.name, "version": bot.version, "status": bot.status, "symbols": symbols,
              "feed": feed, "timeframe": bot.timeframe, "position_size_usd": notional, "costs_bps": cost,
              "params": bot.p, "periods": {}, "problems": [], "sample_trades": []}
    if (lo := left_out(list(symbols_given or bot.symbols))):
        report["problems"].append(lo)
    peek: dict = {}
    untested_rs: list[float] = []
    for label, start, end in windows(bot_cls, days):
        trades, ghosts, probs = run_window(bot, symbols, start, end, feed, fetch, peek=peek, filters=filters,
                                           warmup_days=warmup_days(bot))
        if label == "untested":
            untested_rs = [t.r for t in trades]
        report["problems"] += probs
        s = summarize(trades, notional)
        report["periods"][label] = {"from": str(start), "to": str(end), **s,
                                    **benchmark.compare(s.get("net_usd"), start, end, notional, fetch),
                                    "near_misses": ghost_summary(ghosts)}
        report["sample_trades"] += [t.__dict__ | {"period": label} for t in trades[-3:]]
    if peek.get("problem"):
        report["problems"].insert(0, peek["problem"])
    untested = report["periods"].get("untested", {})
    prev = (journal.find("backtests", bot=loader.bot_id(bot_cls)) or [{}])[-1]
    from . import report as _report                # lazy: report imports this module
    keep_full = prev.get("source") == "full report" and \
        prev.get("untested", {}).get("trades", 0) >= untested.get("trades", 0) and \
        prev.get("version") == bot.version and not _report.changed_since(bot_cls)   # never keep a changed bot's old numbers
    what_if = bool(params or filters)
    if not what_if and not keep_full:           # the meter only trusts the bot's own settings, not a what-if run;
        journal.upsert("backtests", {"bot": loader.bot_id(bot_cls)},
                       {"untested": untested, "untested_rs": untested_rs, "symbols": symbols, "days": days,
                        "version": bot.version})
    if filters:
        report["filters"] = filters
    report["confidence"] = confidence.for_bot(loader.bot_id(bot_cls)) if not what_if else \
        confidence.meter(untested) | {"note": "What-if settings: not saved to the meter."}
    report["vs_spy_note"] = benchmark.NOTE
    for label, per in report["periods"].items():
        if tight_stops(per):
            report.setdefault("warnings", []).append(f"{label}: ⚠ {tight_stops(per)}; judge it by dollars and widen the stop")
    report["note"] = ("Quick run: short window, so the numbers are noisy. 'tuned' = days the settings were picked "
                      "on (expect it to look good); 'untested' = the real test. Not financial advice.")
    return report
