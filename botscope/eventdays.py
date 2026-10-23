"""Event-day split: how a bot's UNTESTED trades did on market event days (options expiration, CPI, jobs, GDP, PCE...)
vs ordinary days. Reuses the rule playground's cached untested backtest, so after the first run it's instant.

Event dates: monthly options expiration (computed, 3rd Friday) and economic releases (FRED release calendar, your
free key). Fed decision days aren't included: the free source (Kalshi) only lists upcoming ones. A group needs 10+
trades before it gets a verdict. Counts and R only, never a win %. Not financial advice.
"""
from __future__ import annotations

from datetime import date

from .weather import MIN_TRADES


def event_dates(start: date, end: date, econ=None) -> tuple[dict[str, list[str]], list[str]]:
    """{day: [event kinds]} and problems."""
    from .market_data import market_calendar as mc
    rows, problems = list(mc.opex(start, end)), []
    try:
        rows += (econ or mc.econ_releases)(start, end)
    except Exception as e:
        problems.append(f"economic releases unavailable ({type(e).__name__}); only options expiration is used")
    out: dict[str, list[str]] = {}
    for r in rows:
        kind = r["event"].split(" (")[0]
        out.setdefault(r["date"], []).append(kind)
    return out, problems


def split(trades, events: dict[str, list[str]]) -> list[dict]:
    groups: dict[str, list[float]] = {"ordinary days": [], "any event day": []}
    for t in trades:
        kinds = events.get(t.t_in[:10])
        groups["any event day" if kinds else "ordinary days"].append(t.r)
        for k in kinds or []:
            groups.setdefault(k, []).append(t.r)
    rows = []
    for g, rs in groups.items():
        row = {"days": g, "trades": len(rs), "avg_r": round(sum(rs) / len(rs), 3) if rs else None,
               "total_r": round(sum(rs), 2)}
        row["verdict"] = (f"too few trades to say ({len(rs)}, need {MIN_TRADES}+)" if len(rs) < MIN_TRADES else
                          "makes money here" if row["avg_r"] > 0 else "loses money here")
        rows.append(row)
    return rows


def event_days(bot_id: str, fetch=None, econ=None) -> dict:
    from . import playground
    c = playground.precompute(bot_id, fetch)
    a, b = (date.fromisoformat(c["window"][k]) for k in ("from", "to"))
    events, problems = event_dates(a, b, econ)
    rows = split(c["trades"], events)
    from . import journal
    journal.upsert("event_fit", {"bot": c["bot"]}, {"window": c["window"], "groups": rows})   # the brief reads it
    return {"bot": c["bot"], "name": c["name"], "window": c["window"], "groups": rows,
            "event_days_in_window": len(events), "problems": problems + c["problems"],
            "source": "options expiration: computed; releases: FRED release calendar; trades: untested backtest",
            "note": "Untested trades only, after costs. Fed decision days aren't included (no free history). A "
                    "group under 10 trades gets no verdict. Not financial advice."}


def today_note(bot_id: str, kinds: list[str]) -> str:
    """'loses money on CPI inflation days (-0.43R a trade over 12 untested)' for an event today, from the saved split."""
    from . import journal
    row = next((r for r in journal.load("event_fit") if r["bot"] == bot_id), None)
    for g in (row or {}).get("groups", []):
        if g["days"] in kinds and not g["verdict"].startswith("too few"):
            return f"{g['verdict'].replace(' here', '')} on {g['days']} days ({g['avg_r']:+.2f}R a trade over {g['trades']} untested)"
    return ""
