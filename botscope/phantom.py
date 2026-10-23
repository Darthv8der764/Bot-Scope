"""Phantom test: a live paper forward test for strategy-factory candidates, with no orders and nothing adopted.

Pick candidates from a factory run; from that day on, each finished market day is replayed for each candidate on
its own symbols with the same costs as the backtester, and every closed signal is saved (journal `phantom_results`).
After N days you see how many signals, their R, the confidence meter on those trades, and the backtest's untested
R per trade next to it. Days before the start never count (that would be a backtest, not a forward test).
Paper only, read only: it downloads bars with your own keys (or demo prices) and never places an order.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path

from . import backtest, confidence, data, journal
from .data import ET

MAX_CATCHUP_DAYS = 30          # one update replays at most this many missed days (keeps it light)


def _last_closed_day(now: datetime | None = None) -> date:
    now = now or datetime.now(ET)
    return now.date() if now.time() >= time(16, 1) else now.date() - timedelta(days=1)


def start(run_id: str, candidates: list[str], today: date | None = None) -> dict:
    """Start phantom tests for the named candidates (name or id) of a factory run."""
    runs = [r for r in journal.load("factory_runs") if r.get("run") == run_id]
    if not runs:
        raise ValueError(f"no factory run {run_id!r} (factory_history lists them)")
    pool = runs[-1].get("kept", []) + runs[-1].get("dropped", [])
    today = today or datetime.now(ET).date()
    started, problems = [], []
    for want in candidates:
        hit = [c for c in pool if want.lower() in (c.get("id", "").lower(), c.get("name", "").lower())]
        if not hit or not hit[0].get("file"):
            problems.append(f"{want}: not in run {run_id}")
            continue
        c = hit[0]
        if any(p["candidate"] == c["id"] and p["run"] == run_id and p["active"] for p in journal.load("phantom")):
            problems.append(f"{c['name']}: already being phantom tested")
            continue
        started.append(journal.add("phantom", {"run": run_id, "candidate": c["id"], "name": c["name"], "file": c["file"],
                                               "started": str(today), "active": True, "checked_to": None,
                                               "backtest_avg_r": c.get("avg_r"), "backtest_trades": c.get("untested_trades")}))
    return {"started": [{"name": p["name"], "from": p["started"]} for p in started], "problems": problems,
            "next": "Run phantom_test(how='update') after each close (or let the daily log do it); no orders are placed."}


def _replay(cls, day: date, since: date) -> list[dict]:
    """Signals that finished on `day`: intraday bots close by the bell; daily bots count a trade on the day it closes
    (if it was entered on or after the phantom's start), so a swing held for days is counted once, when it's done."""
    out = []
    for sym in cls.symbols:
        if cls.timeframe == "1Day":
            bs, _ = data.view_bars(sym, day, "1Day", backtest.warmup_days(cls, data.DAILY_LOOKBACK))
        else:
            bs, _ = data.view_bars(sym, day, cls.timeframe)
        bs = data.clean(bs)[0]
        if not bs or bs[-1].t.astimezone(ET).date() != day:
            continue                                                  # weekend, holiday or no data that day
        trades, _ = backtest.run_day(cls(), sym, day, bs, backtest.COSTS[cls.asset], close_at_end=cls.timeframe != "1Day")
        out += [{"symbol": sym, "side": t.side, "t_in": t.t_in, "t_out": t.t_out, "r": t.r, "why_out": t.why_out}
                for t in trades if t.t_out[:10] == str(day) and t.t_in[:10] >= str(since)]
    return out


def update(now: datetime | None = None, replay=None) -> dict:
    """Replay every finished day since each phantom's last check. `replay(cls, day)` is swappable for tests."""
    from .strategy_factory import load_file
    replay = replay or _replay
    last = _last_closed_day(now)
    done, problems = [], []
    for p in [p for p in journal.load("phantom") if p.get("active")]:
        d = date.fromisoformat(p["checked_to"]) + timedelta(days=1) if p["checked_to"] else date.fromisoformat(p["started"])
        d = max(d, last - timedelta(days=MAX_CATCHUP_DAYS))
        try:
            cls = load_file(Path(p["file"]))
        except Exception as e:                                        # a deleted factory file stops only this one
            problems.append(f"{p['name']}: can't load ({type(e).__name__})")
            continue
        new = 0
        while d <= last:
            if d.weekday() < 5 or cls.asset == "crypto":
                try:
                    for s in replay(cls, d, date.fromisoformat(p["started"])):
                        journal.upsert("phantom_results", {"phantom": p["id"], "symbol": s["symbol"], "t_in": s["t_in"]},
                                       {"day": str(d), **s})
                        new += 1
                except Exception as e:
                    problems.append(f"{p['name']} {d}: {type(e).__name__}: {str(e)[:80]}")
                    break
            journal.upsert("phantom", {"id": p["id"]}, {**p, "checked_to": str(d)})
            p["checked_to"] = str(d)
            d += timedelta(days=1)
        done.append({"name": p["name"], "new_signals": new, "checked_to": p["checked_to"]})
    return {"updated": done, "problems": problems}


def report() -> dict:
    rows = []
    for p in journal.load("phantom"):
        res = journal.find("phantom_results", phantom=p["id"])
        rs = [r["r"] for r in res if r.get("r") is not None]
        days = (date.fromisoformat(p["checked_to"]) - date.fromisoformat(p["started"])).days + 1 if p["checked_to"] else 0
        m = confidence.meter(None, rs)
        rows.append({"name": p["name"], "run": p["run"], "since": p["started"], "days_checked": max(days, 0),
                     "signals": len(res), "total_r": round(sum(rs), 2), "avg_r": round(sum(rs) / len(rs), 3) if rs else None,
                     "backtest_avg_r": p.get("backtest_avg_r"), "backtest_trades": p.get("backtest_trades"),
                     "verdict": verdict(rs, p.get("backtest_avg_r")),
                     "live_evidence": m["live"], "active": p["active"], "id": p["id"]})
    return {"phantoms": rows, "note": "Forward test on live days, paper only, no orders. Few signals = says little. "
                                      "Backtest numbers are from UNTESTED years; phantom numbers are from days after the start."}


def verdict(rs: list[float], bt: float | None) -> str:
    n = len(rs)
    if n < 10:
        return f"too early: {n} signal{'s' if n != 1 else ''} (need 10+ to say anything)"
    avg = sum(rs) / n
    if bt is None:
        return f"{avg:+.2f}R a signal over {n}"
    if avg <= 0 < bt:
        return f"losing live ({avg:+.2f}R a signal) while the backtest made {bt:+.2f}R: the backtest may not hold up"
    if avg < bt / 2:
        return f"weaker than the backtest ({avg:+.2f}R vs {bt:+.2f}R a trade)"
    return f"holding up so far ({avg:+.2f}R vs {bt:+.2f}R a trade in the backtest)"


def stop(name: str) -> dict:
    hits = [p for p in journal.load("phantom") if p["active"] and name.lower() in (p["name"].lower(), p["candidate"].lower())]
    for p in hits:
        journal.upsert("phantom", {"id": p["id"]}, {**p, "active": False})
    return {"stopped": [p["name"] for p in hits]}
