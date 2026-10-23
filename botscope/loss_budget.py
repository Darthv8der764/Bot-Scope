"""Loss budget: one weekly loss limit across all bots, in R (1R = what a trade risked). The week runs Monday to
Sunday (New York dates). When the week's closed paper results add up to a loss of the budget or more, STOP
everything is pressed (the same stop as the stop_everything tool) once that week. Resuming is the user's call; the
budget won't press STOP again until the next week. Lowering the budget works at once; raising it or turning it off
needs a yes, the same as any safety limit."""
from __future__ import annotations

from datetime import date, timedelta

from . import journal, settings


def week_start(day: date | None = None) -> date:
    day = day or date.today()
    return day - timedelta(days=day.weekday())


def status(day: date | None = None) -> dict:
    budget = settings.load().get("loss_budget_r")
    wk = week_start(day)
    rows = [r for r in journal.load("paper_results") if str(r.get("day", "")) >= str(wk)
            and (day is None or str(r.get("day", "")) <= str(day))]
    net = round(sum(float(r.get("r") or 0) for r in rows), 2)
    used = round(max(0.0, -net), 2)
    out = {"week_of": str(wk), "budget_r": budget, "week_r": net, "used_r": used, "trades": len(rows),
           "tripped": bool(journal.find("loss_budget", week=str(wk)))}
    if not budget:
        out["line"] = "Loss budget: off (set_loss_budget sets one weekly limit across all bots)"
        return out
    left = round(max(0.0, budget - used), 2)
    out |= {"left_r": left, "used_up": used >= budget}
    out["line"] = (f"Loss budget: used up ({used:g}R of {budget:g}R this week), everything paused" if used >= budget
                   else f"Loss budget: {used:g}R of {budget:g}R used this week, {left:g}R left")
    return out


def check(day: date | None = None) -> dict:
    """Press STOP when this week's budget is used up (once a week). Called after paper results are logged."""
    st = status(day)
    if st.get("used_up") and not st["tripped"]:
        from . import guard
        guard.stop_everything(f"weekly loss budget used up: {st['used_r']:g}R of {st['budget_r']:g}R "
                              f"(week of {st['week_of']})")
        journal.upsert("loss_budget", {"week": st["week_of"]}, {"used_r": st["used_r"], "budget_r": st["budget_r"]})
        st |= {"tripped": True, "stopped_now": True}
    return st


def set_budget(weekly_r: float | None, confirm: bool = False) -> dict:
    cur = settings.load().get("loss_budget_r")
    new = None if not weekly_r or weekly_r <= 0 else round(float(weekly_r), 2)
    looser = new is None or (cur is not None and new > cur)
    if cur is not None and looser and not confirm:
        return {"question": (f"Raise the weekly loss budget from {cur:g}R to {new:g}R?" if new else
                             f"Turn off the weekly loss budget (now {cur:g}R)?") + " It's a safety limit.",
                "needs": "confirm=true", "budget_r": cur}
    settings.change(loss_budget_r=new)
    return status() | {"set": True}
