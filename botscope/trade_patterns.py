"""My trades pattern table: how your own imported trades did, grouped six ways.

By setup (your note's tag), by hour and by weekday of the entry (US Eastern, same buckets as the time-of-day map),
by weekday and time of day ("Friday afternoon": morning is an entry before 12:00 ET, afternoon from 12:00 on), by
holding time, and by what the trade before it did that day (after a win / after a loss / first trade of the day).
Every row shows its trade count and wins as a count, never a %. A row under MIN_TRADES trades says "not enough
trades yet" instead of being compared. R shows only for trades with a stop in their note. Plain numbers: no
verdicts, no advice. Not financial advice.
"""
from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import datetime
from types import SimpleNamespace

from . import timemap, trade_import, trade_notes

MIN_TRADES = timemap.MIN_TRADES
HOLDING = ((5, "under 5 min"), (30, "5 to 30 min"), (120, "30 min to 2 h"), (60 * 24, "2 h to 1 day"),
           (None, "over 1 day"))
AFTER = ("after a win", "after a loss", "first trade of the day")
DAY_PARTS = ("morning", "afternoon")                  # entry before 12:00 ET / from 12:00 on


def day_part(t: dict) -> str:
    """Weekday and time of day of the entry, e.g. "Friday afternoon"."""
    when = datetime.fromisoformat(t["opened"])
    return f"{when.strftime('%A')} {DAY_PARTS[when.hour >= 12]}"


def minutes_held(t: dict) -> float:
    return (datetime.fromisoformat(t["closed"]) - datetime.fromisoformat(t["opened"])).total_seconds() / 60


def holding_bucket(t: dict) -> str:
    m = minutes_held(t)
    return next(label for top, label in HOLDING if top is None or m < top)


def after_what(trades: list[dict]) -> dict[str, str]:
    """trade_id -> what the trade before it did: the latest trade that CLOSED before this one opened, the same day."""
    days: dict[str, list] = defaultdict(list)
    for p in sorted(trades, key=lambda p: p["closed"]):
        days[p["closed"][:10]].append(p)
    out = {}
    for t in trades:
        day = days.get(t["opened"][:10], [])
        i = bisect.bisect_right([p["closed"] for p in day], t["opened"])
        while i and day[i - 1] is t:                  # a trade opened and closed in the same second
            i -= 1
        out[t["trade_id"]] = AFTER[2] if i == 0 else AFTER[0] if day[i - 1]["pnl"] > 0 else AFTER[1]
    return out


def row(group: str, ts: list[dict], min_trades: int = MIN_TRADES) -> dict:
    """One row: count, wins (a count), dollars, and R over the trades that have one."""
    rs = [t["r"] for t in ts if t.get("r") is not None]
    usd = round(sum(t["pnl"] for t in ts), 2)
    out = {"group": group, "trades": len(ts), "won": sum(t["pnl"] > 0 for t in ts), "total_usd": usd,
           "avg_usd": round(usd / len(ts), 2) if ts else None, "trades_with_r": len(rs),
           "total_r": round(sum(rs), 2) if rs else None, "avg_r": round(sum(rs) / len(rs), 2) if rs else None,
           "enough": len(ts) >= min_trades}
    if not out["enough"]:
        out["note"] = f"not enough trades yet ({len(ts)}, need {min_trades}+)"
    return out


def _rows(groups: dict[str, list], order, min_trades: int) -> list[dict]:
    return [row(k, groups[k], min_trades) for k in order if k in groups]


def table(trades: list[dict], min_trades: int = MIN_TRADES) -> dict:
    """The pattern table for a list of trades (each with trade_id, opened, closed, pnl and optional r)."""
    min_trades = max(1, int(min_trades))
    by: dict[str, dict[str, list]] = {k: defaultdict(list) for k in ("setup", "hour", "weekday", "day_part", "holding", "after")}
    after = after_what(trades)
    for t in trades:
        shim = SimpleNamespace(t_in=t["opened"])
        by["setup"][t.get("setup") or "no tag yet"].append(t)
        by["hour"][timemap._bucket(shim, "hour")].append(t)
        by["weekday"][timemap._bucket(shim, "weekday")].append(t)
        by["day_part"][day_part(t)].append(t)
        by["holding"][holding_bucket(t)].append(t)
        by["after"][after[t["trade_id"]]].append(t)
    first_hour = lambda k: min(datetime.fromisoformat(t["opened"]).hour for t in by["hour"][k])   # noqa: E731
    return {
        "by_setup": _rows(by["setup"], sorted(by["setup"], key=lambda k: (k == "no tag yet", k)), min_trades),
        "by_hour": _rows(by["hour"], sorted(by["hour"], key=first_hour), min_trades),
        "by_weekday": _rows(by["weekday"], timemap.DAYS, min_trades),
        "by_day_part": _rows(by["day_part"], [f"{d} {p}" for d in timemap.DAYS for p in DAY_PARTS], min_trades),
        "by_holding": _rows(by["holding"], [label for _, label in HOLDING], min_trades),
        "by_trade_before": _rows(by["after"], AFTER, min_trades),
        "all": row("all trades", trades, min_trades),
        "min_trades": min_trades,
    }


def patterns(source: str | None = None, min_trades: int = MIN_TRADES) -> dict:
    """The pattern table for your saved trades (one import, or all of them), with their notes."""
    trades = trade_notes.with_notes(trade_import.trades(source))
    if not trades:
        return {"trades": 0, "error": "no trades imported yet: import from Alpaca paper or a Webull CSV, or load the "
                                      "demo trades"}
    out = table(trades, min_trades)
    days = sorted({t["opened"][:10] for t in trades})
    return {"trades": len(trades), "from": days[0], "to": days[-1], "sources": sorted({t["source"] for t in trades}),
            **out, "times": "US Eastern, by entry time",
            "note": "Counts, dollars and R from your own past trades (R only where a note has a stop). Rows under "
                    f"{out['min_trades']} trades are too small to compare. Not financial advice."}
