"""Loss autopsy: after a losing paper day, say why, in five checks. Each one says what it found or that it couldn't
tell; nothing is guessed.
1. Market: the weather that morning (from SPY's finished days) and how this bot does in that weather (saved fit),
   plus the market's own move that day against the bot's side.
2. Costs: how much of the loss was trading costs; would the day have lost before costs?
3. Fills: stop exits that slipped well past the stop (a gap or a fast move), and the extra slippage paid.
4. Normal or not: the day's loss next to the bot's worst drop on untested days. A loss inside that is the bot doing
   what it already did in testing, not a rule that broke.
Reads the paper log (data/journal/paper_results.json) and replays the day with your own keys for the cost detail.
Paper only. Not financial advice.
"""
from __future__ import annotations

from datetime import date, datetime

from . import backtest, data, journal, loader, view

GAP_R = -1.15          # a stop exit worse than this lost more than the planned 1R (plus normal costs)


def losing_days(bot: str | None = None) -> list[tuple[str, str, float]]:
    """(day, bot, total R) for every bot-day in the paper log that lost, newest first."""
    tot: dict[tuple[str, str], float] = {}
    for r in journal.load("paper_results"):
        if bot and r["bot"] != bot:
            continue
        tot[(r["day"], r["bot"])] = tot.get((r["day"], r["bot"]), 0.0) + r["r"]
    return sorted(((d, b, round(t, 2)) for (d, b), t in tot.items() if t < 0), reverse=True)


def _replay(cls, sym: str, day: date) -> dict[str, backtest.Trade]:
    bs, _ = data.view_bars(sym, day, cls.timeframe, backtest.warmup_days(cls, data.DAILY_LOOKBACK))
    bs = data.clean(bs)[0]
    if not bs:
        return {}
    trades, _ = backtest.run_day(cls(), sym, bs[-1].t.date(), bs, backtest.COSTS[cls.asset])
    return {view.trade_id(sym, datetime.fromisoformat(t.t_in)): t for t in trades}


def _weather_on(day: str, fetch=None) -> str:
    from . import weather
    d = date.fromisoformat(day)
    return weather.label_days(weather._index_bars(d, d, fetch)).get(day, "unknown")


def _spy_move(day: str) -> float:
    """SPY's close-to-close move on `day`, as a fraction."""
    from datetime import timedelta
    d = date.fromisoformat(day)
    bs = [b for b in data.clean(data.bars("SPY", d - timedelta(days=10), d, "1Day", "sip"))[0] if b.t.date() <= d]
    if len(bs) < 2 or str(bs[-1].t.date()) != day:
        raise ValueError("no SPY bar for that day")
    return bs[-1].c / bs[-2].c - 1


def market_move_check(move: float, sides: list[str]) -> str:
    sides = sorted(set(s for s in sides if s))
    word = f"SPY {'rose' if move > 0 else 'fell'} {abs(move) * 100:.1f}% that day"
    if abs(move) < 0.005:
        return f"{word}: a flat market, so the loss came from the stocks themselves, not the whole market"
    against = [s for s in sides if (s == "long") != (move > 0)]
    if against and len(against) == len(sides):
        return f"{word}, against the bot's {'/'.join(against)} trades: the whole market pushed the wrong way"
    return f"{word}; the bot's {'/'.join(sides) or '?'} trades {'were mixed' if against else 'went with it'}, " \
           f"so the market alone doesn't explain the loss"


def autopsy(bot: str | None = None, day: str | None = None, replay=None, weather_on=None, spy_move=None) -> dict:
    """Explain one losing bot-day (default: the newest one in the paper log)."""
    days = losing_days(bot)
    if day:
        days = [x for x in days if x[0] == day]
    if not days:
        return {"found": False, "why": "no losing paper day in the log" + (f" for {bot}" if bot else "")
                + (f" on {day}" if day else "") + " (log_paper_results saves them after the close)"}
    day, bid, total = days[0]
    bots, _ = loader.load_all()
    cls = bots.get(bid)
    rows = [r for r in journal.find("paper_results", bot=bid) if r["day"] == day]
    checks = []

    # 1. market
    try:
        w = (weather_on or _weather_on)(day)
    except Exception as e:
        w = f"unknown ({type(e).__name__})"
    fit = next((r for r in journal.load("weather_fit") if r["bot"] == bid), None)
    if fit:
        from .weather import fit_verdict
        checks.append({"check": "market", "found": f"{w} weather that morning; this bot {fit_verdict(fit['by_weather'], w)}"})
    else:
        checks.append({"check": "market", "found": f"{w} weather that morning; this bot's weather fit isn't measured "
                                                   f"yet (run market_weather with this bot)"})

    try:
        mv = (spy_move or _spy_move)(day)
        checks.append({"check": "market move", "found": market_move_check(mv, [r.get("side") for r in rows])})
    except Exception as e:
        checks.append({"check": "market move", "found": f"SPY's move that day isn't known ({type(e).__name__})"})

    # 2 + 3. costs and fills, from a replay of the day
    trades = {}
    if cls:
        for sym in sorted({r["symbol"] for r in rows}):
            try:
                trades.update((replay or _replay)(cls, sym, date.fromisoformat(rows[0].get("entered") or day)
                                                  if cls.timeframe == "1Day" else date.fromisoformat(day)))
            except Exception as e:
                checks.append({"check": "replay", "found": f"couldn't replay {sym}: {type(e).__name__}"})
    matched = [(r, trades[r["trade_id"]]) for r in rows if r["trade_id"] in trades]
    if matched:
        cost_r = sum((t.cost_pct / t.risk_pct) for _, t in matched if t.risk_pct)
        before = total + cost_r
        checks.append({"check": "costs", "found": f"costs took {cost_r:.2f}R of the {total:+.2f}R; before costs the "
                       f"day was {before:+.2f}R" + (" (costs turned it into a loss)" if before >= 0 else "")})
        slipped = [(r, t) for r, t in matched if "stop" in (t.why_out or "") and t.r < GAP_R]
        checks.append({"check": "fills", "found": "; ".join(
            f"{r['symbol']} stop exit at {t.r:+.2f}R (past the planned -1R)" for r, t in slipped)
            or "no stop exit slipped past the planned -1R"})
    else:
        checks.append({"check": "costs + fills", "found": "couldn't match the logged trades to a replay, so costs and "
                                                          "fills aren't known for this day"})

    # one bad bot, or a bad day for all of them?
    others: dict[str, float] = {}
    for r in journal.load("paper_results"):
        if r["day"] == day and r["bot"] != bid:
            others[r["bot"]] = others.get(r["bot"], 0.0) + r["r"]
    if others:
        lost = sorted(b for b, t in others.items() if t < 0)
        checks.append({"check": "other bots", "found": (
            f"{len(lost)} of {len(others)} other bots also lost that day ({', '.join(lost)}): a hard day for the "
            f"whole lineup" if lost and len(lost) == len(others) else
            f"{len(lost)} of {len(others)} other bots lost that day: mostly this bot's own trades")})
    else:
        checks.append({"check": "other bots", "found": "no other bot traded on paper that day"})

    # 4. normal or not
    u = (journal.find("backtests", bot=bid) or [{}])[-1].get("untested") or {}
    dd = u.get("max_drawdown_r")
    if dd is None:
        checks.append({"check": "normal?", "found": "no saved untested backtest to compare with (run run_backtest)"})
    else:
        normal = total >= dd
        checks.append({"check": "normal?", "found": f"{total:+.2f}R today vs a worst drop of {dd:+.2f}R on untested "
                       f"days: " + ("inside what it already did in testing" if normal else
                                    "worse than anything in testing: look at the chart for a rule that misfired")})
    sym = rows[0]["symbol"]
    return {"found": True, "bot": bid, "day": day, "total_r": total, "trades": len(rows),
            "trade_rows": [{"symbol": r["symbol"], "side": r.get("side"), "r": r["r"], "why_out": r.get("why_out")}
                           for r in rows],
            "checks": checks, "chart_path": f"/?bot={bid}&symbol={sym}&day={day}",
            "other_losing_days": [{"day": d, "bot": b, "total_r": t} for d, b, t in days[1:6]],
            "note": "Paper results only. One losing day is normal for any bot; the checks say whether this one was. "
                    "Not financial advice."}
