"""Bot vs bot arena: race two bots (or two versions of one bot) on the same UNTESTED days.

Both bots see the same symbols and the same days, never days either one was tuned on. The winner is decided by the
total result after costs, and a reshuffle check says whether the gap is bigger than luck: the days are resampled
1,000 times and we count how often each bot stays ahead. Counts, never a made-up probability. Not financial advice.
"""
from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, timedelta

from . import backtest, report

RESHUFFLES = 1000


def _tuned_range(bot_cls) -> tuple[date, date] | None:
    if not bot_cls.tuned_on:
        return None
    return tuple(date.fromisoformat(x) for x in bot_cls.tuned_on)


def untested_window(cls_a, cls_b, days: int, today: date | None = None) -> tuple[date, date]:
    """The latest `days`-long window that neither bot was tuned on (ends yesterday at the latest)."""
    end = (today or date.today()) - timedelta(days=1)
    ranges = [r for r in (_tuned_range(cls_a), _tuned_range(cls_b)) if r]
    for _ in range(40):                      # step back past any tuned range until the window is clean
        start = end - timedelta(days=days)
        hit = [r for r in ranges if r[0] <= end and start <= r[1]]
        if not hit:
            return start, end
        end = min(r[0] for r in hit) - timedelta(days=1)
    raise ValueError("couldn't find untested days for both bots")


def _by_day(trades) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for t in trades:
        out[t.t_in[:10]] += t.r
    return out


def head_to_head(day_a: dict[str, float], day_b: dict[str, float], seed: int = 7,
                 reshuffles: int = RESHUFFLES) -> dict:
    """Paired comparison by day: how often A stays ahead when the days are resampled."""
    days = sorted(set(day_a) | set(day_b))
    diffs = [day_a.get(d, 0.0) - day_b.get(d, 0.0) for d in days]
    if not diffs:
        return {"days": 0, "a_ahead": 0, "b_ahead": 0, "of": 0}
    rng = random.Random(seed)
    sims = [sum(rng.choice(diffs) for _ in diffs) for _ in range(reshuffles)]
    return {"days": len(days), "a_better_days": sum(x > 0 for x in diffs), "b_better_days": sum(x < 0 for x in diffs),
            "a_ahead": sum(s > 0 for s in sims), "b_ahead": sum(s < 0 for s in sims), "of": reshuffles}


def verdict(name_a: str, name_b: str, sa: dict, sb: dict, h: dict) -> dict:
    if min(sa.get("trades", 0), sb.get("trades", 0)) < 10:
        return {"winner": None, "level": "not enough trades",
                "why": [f"{name_a}: {sa.get('trades', 0)} trades, {name_b}: {sb.get('trades', 0)} (need 10+ each)"]}
    lead, name, other = (h["a_ahead"], name_a, name_b) if h["a_ahead"] >= h["b_ahead"] else (h["b_ahead"], name_b, name_a)
    why = [f"{name} stayed ahead in {lead} of {h['of']} reshuffles of the same days"]
    if lead >= 95 * h["of"] / 100:
        level = "clear winner"
    elif lead >= 80 * h["of"] / 100:
        level = "probably better"
    else:
        return {"winner": None, "level": "too close to call",
                "why": why + [f"that's not enough to say {name} beats {other}; it could be luck"]}
    tot = sa["total_r"] if name == name_a else sb["total_r"]
    if tot <= 0:
        why.append(f"but {name} still lost money on these days: winning the race isn't the same as having an edge")
    return {"winner": name, "level": level, "why": why}


def race(cls_a, cls_b=None, params_a: dict | None = None, params_b: dict | None = None,
         symbols: list[str] | None = None, days: int = 60, notional: float = 10_000, fetch=None,
         today: date | None = None) -> dict:
    """Race two bots on the same untested days. `cls_b=None` races two versions of `cls_a` (params_a vs params_b)."""
    cls_b = cls_b or cls_a
    a, b = cls_a(**(params_a or {})), cls_b(**(params_b or {}))
    if a.timeframe != b.timeframe and "1Day" in (a.timeframe, b.timeframe):
        raise ValueError("can't race a daily bot against an intraday one on the same days; pick two of the same kind")
    symbols = [s.upper() for s in (symbols or sorted(set(a.symbols) & set(b.symbols)) or a.symbols)]
    symbols = symbols[:backtest.MAX_SYMBOLS]
    start, end = untested_window(cls_a, cls_b, days, today)
    name_a = a.name + (f" {params_a}" if params_a else "")
    name_b = b.name + (f" {params_b}" if params_b else "")
    if name_a == name_b:
        name_a, name_b = name_a + " (A)", name_b + " (B)"
    rows, per_day, problems = [], [], []
    for bot, name in ((a, name_a), (b, name_b)):
        warm = backtest.warmup_days(bot, 30)
        trades, _, probs = backtest.run_window(bot, symbols, start, end, fetch=fetch, warmup_days=warm)
        problems += [f"{name}: {p}" for p in probs[:5]]
        s = backtest.summarize(trades, notional)
        rows.append({"bot": name, **{k: s.get(k) for k in ("trades", "wins", "avg_r", "total_r",
                                                             "worst_losing_streak", "max_drawdown_r", "costs_r")}})
        per_day.append(_by_day(trades))
    h = head_to_head(*per_day)
    return {"window": {"from": str(start), "to": str(end), "period": "untested for both bots"},
            "symbols": symbols, "data": report.data_line(symbols),
            "table": rows, "head_to_head": h, **verdict(name_a, name_b, rows[0], rows[1], h),
            "problems": problems,
            "note": "Same symbols, same untested days, real costs. Counts, not a probability. Not financial advice."}
