"""Time-of-day map: which hours a bot makes or loses money (by entry time, US Eastern), on UNTESTED days only.

Daily bots enter at most once a day, so for them the map is by weekday instead. Wins are a count, never a %.
A row with fewer than MIN_TRADES trades says so instead of a verdict. Not financial advice.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from . import backtest, report

MIN_TRADES = 5
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]   # crypto trades weekends


def _bucket(t, by: str) -> str:
    when = datetime.fromisoformat(t.t_in)
    if by == "weekday":
        return when.strftime("%A")
    h = when.hour
    return f"{h % 12 or 12}{'am' if h < 12 else 'pm'}-{(h + 1) % 12 or 12}{'am' if h + 1 < 12 else 'pm'}"


def rows(trades, by: str = "hour") -> list[dict]:
    g: dict[str, list] = defaultdict(list)
    for t in trades:
        g[_bucket(t, by)].append(t)
    if by == "weekday":
        order = [d for d in DAYS if d in g]
    else:
        order = sorted(g, key=lambda k: min(datetime.fromisoformat(t.t_in).hour for t in g[k]))
    out = []
    for k in order:
        ts = g[k]
        tot = round(sum(t.r for t in ts), 2)
        verdict = (f"too few to say ({len(ts)}, need {MIN_TRADES}+)" if len(ts) < MIN_TRADES else
                   "makes money here" if tot > 0 else "loses money here")
        out.append({"when": k, "trades": len(ts), "wins": sum(t.r > 0 for t in ts), "total_r": tot,
                    "avg_r": round(tot / len(ts), 3), "verdict": verdict})
    return out


def time_map(bot_cls, symbols: list[str] | None = None, days: int = 60, fetch=None) -> dict:
    bot = bot_cls()
    lo = backtest.left_out(list(symbols or bot.symbols))
    symbols = [s.upper() for s in (symbols or bot.symbols)][:backtest.MAX_SYMBOLS]
    (_, a, b), = [w for w in backtest.windows(bot_cls, days) if w[0] == "untested"]
    warm = backtest.warmup_days(bot, 120)
    trades, _, problems = backtest.run_window(bot, symbols, a, b, fetch=fetch, warmup_days=warm)
    by = "weekday" if bot.timeframe == "1Day" else "hour"
    r = rows(trades, by)
    worst = min((x for x in r if x["trades"] >= MIN_TRADES), key=lambda x: x["total_r"], default=None)
    unit = "day" if by == "weekday" else "hour"
    return {"bot": bot.name, "by": by, "rows": r, "symbols": symbols,
            "window": {"from": str(a), "to": str(b), "period": "untested"},
            "hint": (f"Weakest {unit}: {worst['when']} "
                     f"({worst['total_r']:+.2f}R over {worst['trades']} trades). Skipping it is a rule idea to test "
                     "on other days, not a fix." if worst and worst["total_r"] < 0 else
                     f"No {unit} with enough trades loses money on these days."),
            "data": report.data_line(symbols) + "; times in US Eastern", "problems": ([lo] if lo else []) + problems[:5],
            "note": "Untested days only. Picking hours from this map makes these days tuned. Not financial advice."}
