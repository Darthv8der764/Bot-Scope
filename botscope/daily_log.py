"""End-of-day paper log: after the close, replay today for every bot and every one of its symbols, and save the
closed paper trades as live paper results (what the confidence meter's live part reads). Before this, results
were only saved for days someone opened in the chart.

Run after 16:00 New York time:  .venv/bin/python -m botscope.daily_log [YYYY-MM-DD]
Paper only, read only: it downloads bars with your own keys and writes data/journal/paper_results.json.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, time

from . import data, loader, view
from .data import ET


def live_since(bid: str, day: date) -> date:
    """The day BotScope started tracking this daily bot live. Only trades entered on or after it count as live
    paper results; earlier ones are backtest, not live."""
    rows = view.journal.find("live_since", bot=bid)
    if rows:
        return date.fromisoformat(rows[0]["day"])
    view.journal.add("live_since", {"bot": bid, "day": str(day)})
    return day


def log_daily_bot(bid: str, cls, day: date) -> list[dict]:
    """Daily bots hold for days: replay the last months up to `day` and save trades that were entered on or after
    the tracking start and have closed."""
    from . import backtest
    start = live_since(bid, day)
    out = []
    for sym in cls.symbols:
        bs, _ = data.view_bars(sym, day, "1Day", backtest.warmup_days(cls, data.DAILY_LOOKBACK))
        bs = data.clean(bs)[0]
        if not bs:
            continue
        trades, _ = backtest.run_day(cls(), sym, bs[-1].t.date(), bs, backtest.COSTS[cls.asset])   # no forced close
        have = {r["trade_id"] for r in view.journal.find("paper_results", bot=bid, symbol=sym)}
        new = 0
        for t in trades:
            tid = view.trade_id(sym, datetime.fromisoformat(t.t_in))
            if t.t_in[:10] < str(start) or tid in have:
                continue
            view.journal.upsert("paper_results", {"bot": bid, "symbol": sym, "day": t.t_out[:10], "trade_id": tid},
                                {"side": t.side, "r": t.r, "why_out": t.why_out, "entered": t.t_in[:10]})
            new += 1
        out.append({"bot": bid, "symbol": sym, "new_results": new, "tracking_since": str(start)})
    return out


def run(day: date | None = None, notify: bool = True) -> dict:
    now = datetime.now(ET)
    day = day or now.date()
    if day == now.date() and now.time() < time(16, 1):
        return {"skipped": "the market is still open; run this after 16:00 New York time"}
    bots, errors = loader.load_all()
    done, problems = [], [f"{e['file']}: {e['error']}" for e in errors]
    for bid, cls in bots.items():
        if cls.timeframe == "1Day":
            try:
                done += log_daily_bot(bid, cls, day)
            except Exception as e:
                problems.append((bid, f"{type(e).__name__}: {e}"))
            continue
        for sym in cls.symbols:
            try:
                bs, _ = data.view_bars(sym, day, cls.timeframe)
                bs = data.clean(bs)[0]
                if not bs:
                    continue                                       # holiday or no data
                before = len(view.journal.find("paper_results", bot=bid, symbol=sym))
                view.log_paper_day(bid, sym, day, cls, bs, day_over=True)
                after = len(view.journal.find("paper_results", bot=bid, symbol=sym))
                done.append({"bot": bid, "symbol": sym, "new_results": after - before})
            except Exception as e:     # one bad symbol never stops the rest
                problems.append((f"{bid} {sym}", f"{type(e).__name__}: {e}"))
    out = {"day": str(day), "logged": done, "new_results": sum(x["new_results"] for x in done),
           "problems": group_problems(problems)}
    try:                                                   # phantom tests ride along: same finished day, no orders
        from . import phantom
        out["phantom"] = phantom.update()
    except Exception as e:
        out["problems"].append(f"phantom tests: {type(e).__name__}: {e}")
    from . import loss_budget
    out["loss_budget"] = loss_budget.check(day)
    if not notify:                                  # demo paper days: never ping the phone
        return out
    from . import alerts, shadow
    try:
        shadows = shadow.phone_line(str(day))
    except Exception:          # the alert never fails because of the scoreboard
        shadows = ""
    out["phone"] = alerts.send(f"BotScope: {day} paper day logged",
                               f"{out['new_results']} new paper results saved"
                               + (f", {len(out['problems'])} problems" if out["problems"] else "") + ". "
                               + (shadows + ". " if shadows else "") + "Not financial advice.")
    return out


def group_problems(problems: list) -> list[str]:
    """One line per distinct error (missing keys would otherwise repeat once per bot and symbol)."""
    by_msg: dict[str, list[str]] = {}
    for p in problems:
        who, msg = p if isinstance(p, tuple) else (None, p)
        by_msg.setdefault(msg, []).append(who)
    return [msg if who == [None] else f"{', '.join(w for w in who if w)}: {msg}" for msg, who in by_msg.items()]


if __name__ == "__main__":
    out = run(date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None)
    print(f"{out.get('day', '')}: {out.get('skipped') or str(out['new_results']) + ' new paper results'}")
    for p in out.get("problems", []):
        print("  problem:", p)
