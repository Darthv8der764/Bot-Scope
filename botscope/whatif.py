"""What-if slider: how would the bot have done with a wider or tighter stop, or a bigger or smaller target?

Works for any bot without editing it: each entry's stop distance is scaled (0.5x .. 2x of what the bot chose) and
the target is set to N times the new risk (or kept where the bot put it). The whole grid is computed once on the
UNTESTED days from bars already downloaded, so the chart's sliders just look up the answer and update instantly.

Honesty: if you pick a setting because it looked best here, these days stop being untested for that setting. The
result says so, and a rule change still goes through a fresh backtest on other days. Not financial advice.
"""
from __future__ import annotations

from . import backtest, journal, loader, report
from .bot import Entry
from .luck import _day_groups

STOP_X = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
TARGET_R = (None, 1.0, 1.5, 2.0, 3.0)           # None = keep the bot's own target price


def scale_hook(stop_x: float, target_r: float | None):
    def hook(view, e: Entry):
        c = view.last.c
        d = 1 if e.side == "long" else -1
        risk = abs(c - e.stop) * stop_x
        if risk <= 0:
            return e
        stop = c - d * risk
        target = e.target if target_r is None else c + d * target_r * risk
        return Entry(e.side, stop, target, e.reason)
    return hook


def _cell(bot, groups, cost, stop_x, target_r, notional) -> dict:
    trades = []
    for sym, day, bs, start in groups:
        tr, _ = backtest.run_day(bot, sym, day, bs, cost, scale_hook(stop_x, target_r),
                                 close_at_end=bot.timeframe == "1Day")
        trades += [t for t in tr if t.t_in[:10] >= str(start)]
    s = backtest.summarize(trades, notional)
    return {"stop_x": stop_x, "target_r": target_r,
            **{k: s.get(k, 0) for k in ("trades", "wins", "avg_r", "total_r", "net_usd", "avg_usd_per_win",
                                         "worst_losing_streak", "max_drawdown_r")}} | (
        {"tight_stops": True} if backtest.tight_stops(s) else {})


def grid(bot_cls, symbols: list[str] | None = None, days: int = 30, notional: float = 10_000, fetch=None) -> dict:
    bot = bot_cls()
    lo = backtest.left_out(list(symbols or bot.symbols))
    symbols = [s.upper() for s in (symbols or bot.symbols)][:backtest.MAX_SYMBOLS]
    ws = [(a, b) for label, a, b in backtest.windows(bot_cls, days) if label == "untested"]
    groups = _day_groups(bot, symbols, ws, fetch, 30 if bot.timeframe == "1Day" else 0)
    cost = backtest.COSTS[bot.asset]
    cells = [_cell(bot, groups, cost, sx, tr, notional) for sx in STOP_X for tr in TARGET_R]
    base = next(c for c in cells if c["stop_x"] == 1.0 and c["target_r"] is None)
    fair = [c for c in cells if not c.get("tight_stops")]   # R from stops inside the costs can't be trusted
    best = max(fair, key=lambda c: c["total_r"]) if fair else base
    out = {"bot": bot.name, "symbols": symbols, "window": {"from": str(ws[0][0]), "to": str(ws[0][1]),
                                                             "period": "untested"},
           "position_size_usd": notional, "stop_x": list(STOP_X), "target_r": list(TARGET_R),
           "baseline": base, "cells": cells, "data": report.data_line(symbols),
           "note": ("stop_x 1.0 + target_r null = the bot as it is. Picking the best-looking cell turns these days "
                    "into tuned days for that setting: test it on other days (run_backtest with params, or "
                    "honest_report) before changing the rule. Not financial advice.")}
    if len(fair) < len(cells):
        out["tight_stop_cells"] = (f"{len(cells) - len(fair)} cells had stops closer than their own costs, so their "
                                   "R is inflated: never picked as best-looking (docs/when-r-lies-tight-stops.md)")
    if lo:
        out["left_out"] = lo
    if base["trades"] < 10:
        out["warning"] = f"only {base['trades']} untested trades: every cell here is mostly noise"
    elif best is not base:
        out["best_looking"] = {k: best[k] for k in ("stop_x", "target_r", "total_r", "trades")} | {
            "caution": "best of 30 tries on the same days: expect it to look worse on new days"}
    journal.upsert("whatif", {"bot": loader.bot_id(bot_cls)}, {k: v for k, v in out.items() if k != "bot"})
    return out


def saved(bot_id: str) -> dict | None:
    rows = journal.find("whatif", bot=bot_id)
    return rows[-1] if rows else None
