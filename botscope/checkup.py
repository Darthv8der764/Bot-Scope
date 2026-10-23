"""Weekly checkup: one Sunday card. Drift (live paper vs backtest), changed trading costs (since the last checkup),
data gaps (weekdays last week with no paper results logged), old or missing honest reports, and bots changed since
their report. Reads what's saved on this computer; no new backtests."""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta

from . import backtest, drift, journal, loader, report

OLD_DAYS = 90


def costs_hash() -> str:
    return hashlib.sha256(json.dumps(backtest.COSTS, sort_keys=True).encode()).hexdigest()[:12]


def checkup(today: date | None = None) -> dict:
    today = today or date.today()
    bots, errors = loader.load_all()
    rows = []
    for bid, cls in bots.items():
        rep = report.saved(cls) or {}
        age = (today - journal.local_day(rep["saved_at"])).days if rep.get("saved_at") else None
        try:
            d = drift.for_bot(bid).get("level", "unknown")
        except Exception as e:
            d = f"unknown ({type(e).__name__})"
        flags = []
        if d in ("alarm", "watch", "too good"):
            flags.append(f"drift: {d}")
        if age is None:
            flags.append("no honest report yet")
        elif age >= OLD_DAYS:
            flags.append(f"report is {age} days old")
        if report.changed_since(cls, rep):
            flags.append("changed since its report")
        rows.append({"bot": bid, "drift": d, "report_age_days": age, "flags": flags})
    # the last checkup from an EARLIER day: running it twice today must not hide a cost change seen this morning
    last = ([r for r in journal.load("checkup") if r.get("day") != str(today)] or [{}])[-1]
    now_hash = costs_hash()
    costs = ("first checkup: costs noted for next week" if not last.get("costs_hash") else
             "unchanged since the last checkup" if last["costs_hash"] == now_hash else
             f"CHANGED since the last checkup ({last.get('day')}): every saved report used the old costs")
    week = [today - timedelta(days=k) for k in range(1, 8)]
    logged = {r.get("day") for r in journal.load("paper_results")}
    gaps = sorted(str(d) for d in week if d.weekday() < 5 and str(d) not in logged)
    journal.upsert("checkup", {"day": str(today)}, {"costs_hash": now_hash})
    flagged = [r for r in rows if r["flags"]]
    lines = [f"Drift: {sum(r['drift'] in ('alarm', 'watch', 'too good') for r in rows)} of {len(rows)} bots off from their backtest",
             f"Costs: {costs}",
             f"Data gaps: {', '.join(gaps) + ' had no paper results logged (market holiday, or run log_paper_results)' if gaps else 'none: every weekday last week has paper results'}",
             f"Reports: {sum(r['report_age_days'] is None or r['report_age_days'] >= OLD_DAYS for r in rows)} missing or {OLD_DAYS}+ days old; "
             f"{sum('changed since its report' in r['flags'] for r in rows)} bots changed since their report"]
    return {"day": str(today), "lines": lines, "bots": rows, "needs_a_look": [r["bot"] for r in flagged],
            "files_with_errors": [e["file"] for e in errors],
            "summary": (f"{len(flagged)} of {len(rows)} bots need a look: " + ", ".join(r["bot"] for r in flagged)
                        if flagged else f"all {len(rows)} bots look fine this week"),
            "note": "From results saved on this computer (live paper, saved reports, costs). Paper only. Not financial advice."}
