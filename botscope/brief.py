"""Morning brief: 3 lines before the open. Market weather, today's events, and what each bot that's ON will watch,
with its confidence level. Reuses the weather, calendar, pre-flight list and confidence meter (no new data, no AI).
Optionally pushed to your phone with your own ntfy topic. Not financial advice.
"""
from __future__ import annotations

from datetime import date

from . import loader, preflight


def weather_line(w: dict) -> str:
    if w.get("error") or w.get("weather") in (None, "unknown"):
        return f"Weather: unknown ({w.get('error') or '; '.join(w.get('why') or []) or 'no data'})"
    mood = f", {w['mood']}" if w.get("mood") else ""
    return f"Weather: {w['weather']}{mood} (SPY, as of the {w.get('as_of_close') or '?'} close)"


def events_line(events: list[dict]) -> str:
    real = [e["event"] for e in events if e.get("date")]
    if not real:
        bad = [e for e in events if not e.get("date")]
        return "Today: no scheduled market events" + (" (calendar partly unavailable)" if bad else "")
    more = f" +{len(real) - 4} more" if len(real) > 4 else ""
    return "Today: " + "; ".join(real[:4]) + more


def fit_note(bid: str, weather: str | None) -> str:
    """'struggles in choppy weather' from the bot's saved weather fit; '' when unmeasured or too few trades."""
    from . import journal
    from .weather import fit_verdict
    row = next((r for r in journal.load("weather_fit") if r["bot"] == bid), None)
    if not row or not weather or weather == "unknown":
        return ""
    v = fit_verdict(row["by_weather"], weather)
    return "" if v.startswith("not enough") else v.split(" (")[0]


def loss_note(bid: str) -> str:
    """'lost -1.93R on 10-15 (loss_autopsy says why)' when the bot's newest paper day lost; '' otherwise."""
    from . import autopsy, journal
    days = [r["day"] for r in journal.find("paper_results", bot=bid)]
    lost = autopsy.losing_days(bid)
    if not days or not lost or lost[0][0] != max(days):
        return ""
    return f"lost {lost[0][2]:+.2f}R on {lost[0][0][5:]} (loss_autopsy says why)"


def bots_line(rows: list[dict], symbols: dict[str, list[str]], notes: dict[str, list[str]] | None = None) -> str:
    on = [r for r in rows if r["on"]]
    if not on:
        return "Bots: none on today (answer the pre-flight list to turn one on)"
    parts = []
    for r in on:
        syms = symbols.get(r["id"]) or []
        watch = ", ".join(syms[:4]) + (f" +{len(syms) - 4}" if len(syms) > 4 else "")
        flag = f" ⚠ {r['warnings'][0].split(' (')[0]}" if r["warnings"] else ""
        extra = "".join(f", {n}" for n in (notes or {}).get(r["id"], []) if n)
        parts.append(f"{r['name']} watches {watch or '?'} on {r['timeframe']}, confidence {r['confidence']}{flag}{extra}")
    return "Bots: " + "; ".join(parts)


def closed_reason(day: str, events: list[dict]) -> str | None:
    """'Saturday' / 'holiday' when the market is shut that day (holidays come from the Alpaca calendar events)."""
    d = date.fromisoformat(day)
    if d.weekday() >= 5:
        return d.strftime("%A")
    if any(e.get("date") == day and e["event"].startswith("Market closed") for e in events):
        return "holiday"
    return None


def brief(day: date | None = None, weather=None, events=None, push: bool = False, send=None,
          force: bool = False) -> dict:
    """The 3 lines. `weather`/`events` can be passed in (tests); otherwise they're read live with your keys."""
    if weather is None:
        try:
            from . import weather as wx
            weather = wx.today()
        except Exception as e:
            weather = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
    pf = preflight.today_list(day, events=events)
    bots, _ = loader.load_all()
    syms = {bid: list(getattr(cls(), "symbols", []) or []) for bid, cls in bots.items()}
    from .eventdays import today_note
    kinds = [e["event"].split(" (")[0] for e in pf["events_today"] if e.get("date")]
    notes = {r["id"]: [fit_note(r["id"], weather.get("weather")), today_note(r["id"], kinds), loss_note(r["id"])]
             for r in pf["bots"] if r["on"]}
    lines = [weather_line(weather), events_line(pf["events_today"]), bots_line(pf["bots"], syms, notes)]
    if pf["stopped"]:
        lines[2] = "Bots: STOP is on, nothing runs today"
    closed = closed_reason(pf["day"], pf["events_today"])
    if closed and not pf["stopped"]:
        crypto = [r for r in pf["bots"] if r["on"] and getattr(bots.get(r["id"]), "asset", "") == "crypto"]
        lines[2] = (f"Bots: stock market closed today ({closed}), no stock bot trades"
                    + ("; crypto trades every day: " + bots_line(crypto, syms, notes)[len("Bots: "):] if crypto else ""))
    elif closed:
        lines[2] = f"Bots: STOP is on, nothing runs today (market closed: {closed})"
    from . import loss_budget
    lb = loss_budget.status()
    if lb["budget_r"]:
        lines.append(lb["line"])
    out = {"day": pf["day"], "lines": lines,
           "sources": "weather: SPY daily closes (Alpaca SIP); events: Alpaca, Kalshi, FRED, Finnhub; "
                      "bots: your pre-flight answers + confidence meter (saved on this computer)",
           "note": "⚠ = the pre-flight list's first red flag for that bot (preflight_list shows all). Information only. "
                    "Not financial advice."}
    if push:
        from . import alerts, journal
        if journal.find("brief_pushed", day=pf["day"]) and not force:
            out["phone"] = {"sent": False, "why": "already sent today (pass force to send again)"}
        else:
            out["phone"] = (send or alerts.send)("BotScope morning brief", "\n".join(lines), tags="sunrise")
            if out["phone"].get("sent"):
                journal.upsert("brief_pushed", {"day": pf["day"]}, {})
    return out
