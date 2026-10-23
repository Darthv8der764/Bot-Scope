"""Flight simulator: trade a past day yourself with the future hidden, then compare with the bot and with simply
holding. The page shows candles one at a time; the bot's trades and the rest of the day are only shown at the end.
Paper only, nothing is sent anywhere. Same trading costs as every BotScope backtest."""
from __future__ import annotations

from datetime import date, timedelta

from . import backtest, data, journal, loader


def _last_weekday(today: date | None = None) -> date:
    d = (today or date.today()) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def flight(bot: str, symbol: str | None = None, day: str | None = None) -> dict:
    cls = loader.get(bot)
    sym = (symbol or cls.symbols[0]).upper()
    d = date.fromisoformat(day) if day else _last_weekday()
    bs, src = data.view_bars(sym, d, cls.timeframe, backtest.warmup_days(cls, data.DAILY_LOOKBACK))
    bs = data.clean(bs)[0]
    if len(bs) < 20:
        raise ValueError(f"not enough {cls.timeframe} candles for {sym} on {d} (weekend, holiday or no data); pick another day")
    daily = cls.timeframe == "1Day"
    start = max(20, len(bs) - 60) if daily else 6          # daily: play the last 60 days; intraday: from 10:00-ish
    cost = backtest.COSTS[cls.asset]
    trades, _ = backtest.run_day(cls(), sym, d, bs, cost, close_at_end=daily)
    first = bs[start].t.isoformat()
    bot_trades = [{"side": t.side, "t_in": t.t_in, "t_out": t.t_out, "entry": t.entry, "exit": t.exit, "pct": t.pct,
                   "r": t.r, "why_in": t.why_in, "why_out": t.why_out} for t in trades if t.t_in >= first]
    return {"bot": cls.name, "bot_id": loader.bot_id(cls), "symbol": sym, "day": str(d), "timeframe": cls.timeframe,
            "source": src, "start": start,
            "candles": [{"t": b.t.isoformat(), "o": b.o, "h": b.h, "l": b.l, "c": b.c} for b in bs],
            "cost_pct": (cost["entry_bps"] + cost["exit_bps"]) / 100, "stop_extra_pct": cost["stop_extra_bps"] / 100,
            "bot_trades": bot_trades, "bot_pct": round(sum(t["pct"] for t in bot_trades), 3),
            "hold_pct": round((bs[-1].c / bs[start].o - 1) * 100 - (cost["entry_bps"] + cost["exit_bps"]) / 100, 3),
            "hold_note": "just holding = buy at the first open you see, sell at the last close, one round trip of costs",
            "note": "Paper only. Your result and the bot's both pay the same costs. One day is luck-heavy: play several. "
                    "Not financial advice."}


def save_score(row: dict) -> dict:
    keep = {k: row.get(k) for k in ("bot", "symbol", "day", "you_pct", "bot_pct", "hold_pct", "trades")}
    journal.add("flights", keep)
    past = journal.load("flights")[-10:]
    beat_bot = sum((r.get("you_pct") or 0) > (r.get("bot_pct") or 0) for r in past)
    beat_hold = sum((r.get("you_pct") or 0) > (r.get("hold_pct") or 0) for r in past)
    return {"saved": True, "last_flights": len(past),
            "summary": f"last {len(past)} flights: you beat the bot on {beat_bot} and just holding on {beat_hold}"}
