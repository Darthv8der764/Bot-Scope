"""Mistake mirror: line up your own logged trades against what your bots would have done that day.

You give it a CSV of your trades (date, time, symbol, side, entry, exit; optional stop). For each trade and each bot,
BotScope replays that day on paper and says whether the bot agreed (same side, entered near your time), went the
other way, or stayed out, and why (the bot's own reason at your entry time). Then it compares how your trades did
when the bots agreed vs when they would have stayed out.

Your trades are read from your file and never copied or saved by BotScope. Counts and averages only, small samples
say so. Not financial advice.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, time
from pathlib import Path

from . import backtest, data, loader
from .data import ET

NEAR_MINUTES = 30
SMALL = 10
SIDES = {"long": "long", "buy": "long", "b": "long", "short": "short", "sell": "short", "s": "short",
         "sell short": "short", "sell_short": "short"}


def read_trades(path: str | Path) -> list[dict]:
    """Rows from a CSV with headers date, time (HH:MM New York, optional), symbol/ticker, side, entry, exit, stop."""
    out = []
    with open(Path(path).expanduser(), newline="") as f:
        for n, row in enumerate(csv.DictReader(f), 2):
            r = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            sym = (r.get("symbol") or r.get("ticker") or "").upper()
            side = SIDES.get(r.get("side", "").lower())
            try:
                d = date.fromisoformat(r["date"])
                t = time.fromisoformat(r["time"]) if r.get("time") else None
                entry, exit_ = float(r["entry"]), float(r["exit"])
                stop = float(r["stop"]) if r.get("stop") else None
            except (KeyError, ValueError) as e:
                raise ValueError(f"line {n}: needs date (YYYY-MM-DD), entry and exit numbers ({e})") from e
            if not sym or not side:
                raise ValueError(f"line {n}: needs a symbol and a side (long/buy or short/sell)")
            out.append({"date": d, "time": t, "symbol": sym, "side": side, "entry": entry, "exit": exit_, "stop": stop})
    return out


def your_result(t: dict) -> dict:
    d = 1 if t["side"] == "long" else -1
    out = {"pct": round((t["exit"] - t["entry"]) / t["entry"] * 100 * d, 2)}
    if t.get("stop") and t["stop"] != t["entry"]:
        out["r"] = round((t["exit"] - t["entry"]) * d / abs(t["entry"] - t["stop"]), 2)
    return out


def compare(t: dict, bot_cls, bars_for=None) -> dict:
    """One bot on the day of one of your trades."""
    bot = bot_cls()
    bars_for = bars_for or (lambda sym, d, tf: data.view_bars(sym, d, tf, backtest.warmup_days(bot, data.DAILY_LOOKBACK))[0])
    bs = data.clean(bars_for(t["symbol"], t["date"], bot.timeframe))[0]
    if not bs:
        return {"verdict": "no data", "why": "no bars that day"}
    trace: list = []
    trades, _ = backtest.run_day(bot, t["symbol"], t["date"], bs, backtest.COSTS[bot.asset], trace=trace,
                                 close_at_end=bot.timeframe == "1Day")
    today = [x for x in trades if x.t_in[:10] == str(t["date"])]
    yours = datetime.combine(t["date"], t["time"] or time(9, 30), ET)
    rows = [x for x in trace if x["t"].date() == t["date"]]
    at = next((x for x in reversed(rows) if x["t"] <= yours), rows[0] if rows else None)
    at_yours = at["reason"] if at else "no decision that day"
    if today:
        b = min(today, key=lambda x: abs((datetime.fromisoformat(x.t_in) - yours).total_seconds()))
        mins = abs((datetime.fromisoformat(b.t_in) - yours).total_seconds()) / 60
        same = b.side == t["side"]
        near = t["time"] is None or bot.timeframe == "1Day" or mins <= NEAR_MINUTES
        verdict = "agreed" if same and near else "same side, different time" if same else "went the other way"
        return {"verdict": verdict, "bot_side": b.side, "bot_entry_time": b.t_in[11:16], "bot_r": b.r,
                "why": b.why_in, "bot_at_your_time": at_yours}
    return {"verdict": "stayed out", "why": at_yours}


def mirror(path: str, bots: list[str] | None = None, bars_for=None, limit: int = 50) -> dict:
    trades = read_trades(path)[-limit:]
    all_bots, _ = loader.load_all()
    use = {k: c for k, c in all_bots.items() if not bots or k in bots}
    rows, problems = [], []
    for t in trades:
        res = your_result(t)
        row = {"date": str(t["date"]), "time": t["time"].strftime("%H:%M") if t["time"] else "", "symbol": t["symbol"],
               "side": t["side"], "your_pct": res["pct"], "your_r": res.get("r"), "bots": {}}
        for bid, cls in use.items():
            try:
                row["bots"][bid] = compare(t, cls, bars_for)
            except RuntimeError:
                raise                                   # missing keys: say so once
            except Exception as e:
                problems.append(f"{t['symbol']} {t['date']} {bid}: {type(e).__name__}: {str(e)[:100]}")
        rows.append(row)
    agreed = [r for r in rows if any(b["verdict"] == "agreed" for b in r["bots"].values())]
    out_ = [r for r in rows if r["bots"] and all(b["verdict"] == "stayed out" for b in r["bots"].values())]
    avg = lambda rs: round(sum(r["your_pct"] for r in rs) / len(rs), 2) if rs else None     # noqa: E731
    summary = {"your_trades": len(rows), "a_bot_agreed": len(agreed), "every_bot_stayed_out": len(out_),
               "your_avg_pct_when_a_bot_agreed": avg(agreed), "your_avg_pct_when_bots_stayed_out": avg(out_)}
    lines = []
    if agreed and out_:
        better = "agreed" if avg(agreed) > avg(out_) else "stayed out"
        lines.append(f"Your trades did better when the bots {better} ({avg(agreed):+.2f}% vs {avg(out_):+.2f}% a trade).")
    if len(rows) < SMALL:
        lines.append(f"Only {len(rows)} trades: too few to call it a pattern.")
    return {"summary": summary, "lines": lines, "trades": rows, "bots": list(use), "problems": problems[:10],
            "privacy": "Read from your file only; BotScope didn't copy or save your trades.",
            "note": "Your results in % (and R when you logged a stop); bot results in R after costs, on paper. "
                    "Not financial advice."}
