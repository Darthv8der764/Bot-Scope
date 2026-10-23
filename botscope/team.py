"""Team of bots: run all your bots together on their untested years for one combined result, the team's worst
drop (vs adding up each bot's own worst drop) and how much they overlap (same symbol, same day). Every trade
counts as 1R of risk, so the team total is in R. Paper only. Not financial advice."""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations

from . import backtest, loader, report


def _drawdown(rs: list[float]) -> float:
    peak = cur = worst = 0.0
    for r in rs:
        cur += r; peak = max(peak, cur); worst = min(worst, cur - peak)
    return round(worst, 2)


def drop_note(team_drop: float, sum_drops: float) -> str:
    if not sum_drops:                                  # nobody ever went below their own peak
        return "no bot had a losing stretch on these days, so there's no drop to compare"
    return (f"the team's worst drop ({team_drop:+.1f}R) vs {sum_drops:+.1f}R if every bot's worst stretch had come at "
            "once: " + ("they don't all lose at the same time" if team_drop > sum_drops * 0.7 else
                        "they tend to lose together"))


def team(bots: list[str] | None = None, fetch=None) -> dict:
    found, _ = loader.load_all()
    ids = [loader.bot_id(loader.get(b)) for b in bots] if bots else list(found)
    if len(ids) < 2:
        raise ValueError("a team needs at least 2 bots")
    per, all_trades, days = [], [], defaultdict(lambda: defaultdict(float))
    for bid in ids[:8]:
        cls = found.get(bid) or loader.get(bid)
        bot = cls()
        warm = backtest.warmup_days(bot, report.DAILY_WARMUP)
        trades = []
        for w in report.year_windows(cls):
            if w["period"] != "untested":
                continue
            t, _, _ = backtest.run_window(bot, cls.symbols, w["from"], w["to"], fetch=fetch, warmup_days=warm)
            trades += t
        trades.sort(key=lambda t: t.t_out or t.t_in)
        for t in trades:
            all_trades.append((t.t_out or t.t_in, bid, t))
            days[bid][(t.t_out or t.t_in)[:10]] += t.r
        rs = [t.r for t in trades]
        per.append({"bot": cls.name, "id": bid, "timeframe": cls.timeframe, "trades": len(rs),
                    "total_r": round(sum(rs), 2), "worst_drop_r": _drawdown(rs),
                    "_entries": {(t.symbol, t.t_in[:10]) for t in trades}})
    all_trades.sort(key=lambda x: x[0])
    rs = [t.r for _, _, t in all_trades]
    team_drop = _drawdown(rs)
    sum_drops = round(sum(p["worst_drop_r"] for p in per), 2)
    overlaps = []
    for a, b in combinations(per, 2):
        ea, eb = a["_entries"], b["_entries"]
        if ea and eb:
            shared = len(ea & eb)
            overlaps.append({"bots": [a["bot"], b["bot"]], "shared_entries": shared,
                             "share_of_smaller": round(shared / min(len(ea), len(eb)), 2)})
    for a, b in combinations(per, 2):                     # same-day results: do they win and lose together?
        da, db = days[a["id"]], days[b["id"]]
        both = [d for d in da if d in db]
        if len(both) >= 10:
            xs, ys = [da[d] for d in both], [db[d] for d in both]
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            vx, vy = sum((x - mx) ** 2 for x in xs) ** 0.5, sum((y - my) ** 2 for y in ys) ** 0.5
            o = next(o for o in overlaps if o["bots"] == [a["bot"], b["bot"]])
            o["days_both_traded"] = len(both)
            o["same_day_correlation"] = round(cov / (vx * vy), 2) if vx and vy else None
    for p in per:
        p.pop("_entries")
    out = {"team": {"bots": len(per), "trades": len(rs), "total_r": round(sum(rs), 2), "worst_drop_r": team_drop,
                    "sum_of_own_worst_drops_r": sum_drops},
           "bots": per, "overlap": overlaps, "period": "each bot's UNTESTED years (tuned years left out)",
           "data": report.data_line([s for p in per for s in found.get(p["id"], loader.get(p["id"])).symbols]),
           "drop_note": drop_note(team_drop, sum_drops),
           "note": "Every trade counts as 1R of risk; intraday bots test one month per year. Not financial advice."}
    if len(ids) > 8:
        out["left_out"] = f"a team holds 8 bots at most: {', '.join(ids[8:])} left out"
    big = [o for o in overlaps if o["share_of_smaller"] >= 0.5 or (o.get("same_day_correlation") or 0) >= 0.6]
    out["same_bet"] = [f"{o['bots'][0]} and {o['bots'][1]} are mostly one bet ("
                       + (f"{o['shared_entries']} shared entries" if o["share_of_smaller"] >= 0.5 else
                          f"same-day correlation {o['same_day_correlation']}") + ")" for o in big]
    out["markdown"] = "\n".join(["| Bot | Trades | Total | Worst drop |", "|---|---|---|---|"]
                                + [f"| {p['bot']} | {p['trades']} | {p['total_r']:+.1f}R | {p['worst_drop_r']:+.1f}R |" for p in per]
                                + [f"| **Team** | {len(rs)} | {sum(rs):+.1f}R | {team_drop:+.1f}R |"])
    return out
