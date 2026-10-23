"""The daily pre-flight list: before the bots run each day, see which ones are failing and say on or off for each.

No answer (you're away and the computer starts the bots by itself) = yesterday's settings. A bot you have never
answered for stays OFF (nothing runs until you say so). STOP turns every bot off. Your answers are saved on this
computer (data/journal/preflight.json). Not financial advice.
"""
from __future__ import annotations

from datetime import date, datetime

from . import confidence, drift, journal, loader, report, settings
from .data import ET


def _today() -> date:
    return datetime.now(ET).date()


OLD_REPORT_DAYS = 90


def warnings_for(cls) -> list[str]:
    """Plain reasons a bot might be better off today (red flags only)."""
    bid = loader.bot_id(cls)
    out = []
    if cls.status == "failed":
        out.append("labeled failed (did not make money after costs in its test)")
    rep = report.saved(cls) or {}
    if report.changed_since(cls, rep):
        out.append("changed since its report (honest_report again)")
    age = (_today() - journal.local_day(rep["saved_at"])).days if rep.get("saved_at") else 0
    if age >= OLD_REPORT_DAYS:
        out.append(f"report is {age} days old (newer days aren't in it; honest_report again)")
    u = rep.get("untested") or {}
    if u.get("trades") and u["avg_r"] <= 0:
        out.append(f"loses on untested years ({u['avg_r']:+.2f}R per trade)")
    lk = (journal.find("luck", bot=bid) or [{}])[-1].get("level")
    if lk == "looks like luck":
        out.append("luck meter: looks like luck")
    try:
        d = drift.for_bot(bid)["level"]
        if d in ("alarm", "watch"):
            out.append(f"drift: {d} (live paper is off from the backtest)")
    except Exception:
        pass
    return out


def _base(day: date) -> tuple[dict | None, dict]:
    """The latest answer on or before `day` and the on/off it gives every current bot (STOP not applied)."""
    bots, _ = loader.load_all()
    rows = sorted((r for r in journal.load("preflight") if r.get("day", "") <= str(day)), key=lambda r: r["day"])
    src = rows[-1] if rows else None
    return src, {b: bool((src or {}).get("bots", {}).get(b, False)) for b in bots}


def settings_for(day: date | None = None) -> dict:
    """{bots: {id: on}, answered_by: 'you' | 'yesterday (no answer)' | 'nobody yet', answer_day}."""
    day = day or _today()
    src, on = _base(day)
    who = "nobody yet" if not src else "you" if src["day"] == str(day) else "yesterday (no answer)"
    if settings.load()["stopped"]:
        on = {b: False for b in on}
        who += ", but STOP is on: everything off"
    return {"day": str(day), "bots": on, "answered_by": who, "answer_day": src["day"] if src else None}


def is_on(bot_id: str, day: date | None = None) -> bool:
    return settings_for(day)["bots"].get(bot_id, False)


def today_list(day: date | None = None, events=None) -> dict:
    day = day or _today()
    cur = settings_for(day)
    bots, errors = loader.load_all()
    rows = []
    for bid, cls in bots.items():
        conf = confidence.for_bot(bid)
        w = warnings_for(cls)
        rows.append({"id": bid, "name": cls.name, "status": cls.status, "timeframe": cls.timeframe,
                     "confidence": conf["level"], "warnings": w, "on": cur["bots"].get(bid, False),
                     "flag": "red" if w else "ok"})
    if events is None:
        try:
            from .market_data import market_calendar
            events = [e for e in market_calendar.upcoming(1) if e.get("date") == str(day)]
        except Exception as e:      # the list works without the calendar
            events = [{"event": f"calendar unavailable: {e}", "source": "-"}]
    return {"day": str(day), "answered_by": cur["answered_by"], "bots": rows, "events_today": events,
            "stopped": settings.load()["stopped"], "files_with_errors": errors,
            "question": "Which bots should run today? (No answer = yesterday's settings.)",
            "note": "Red flags are reasons to think, not orders. Paper by default. Not financial advice."}


def answer(choices: dict, day: date | None = None) -> dict:
    """Save today's on/off answers. Bots not mentioned keep their current setting."""
    day = day or _today()
    bots, _ = loader.load_all()
    unknown = [b for b in choices if b not in bots]
    if unknown:
        raise ValueError(f"unknown bots {unknown}; have: {', '.join(bots)}")
    _, cur = _base(day)
    new = {**cur, **{b: bool(v) for b, v in choices.items()}}
    journal.upsert("preflight", {"day": str(day)}, {"bots": new, "answered_by": "you"})
    return settings_for(day) | {"saved": True}
