"""Weekly loss budget: one limit across all bots; used up -> STOP (once a week); raising it needs a yes."""
from datetime import date

from botscope import journal, loss_budget as lb, settings


def _paper(day, r, bot="nr7_swing"):
    journal.add("paper_results", {"bot": bot, "symbol": "SPY", "day": day, "r": r, "trade_id": f"{bot}{day}{r}"})


def test_off_by_default_and_says_how_to_turn_it_on():
    st = lb.status(date(2026, 10, 16))
    assert st["budget_r"] is None and "off" in st["line"] and not lb.check(date(2026, 10, 16)).get("stopped_now")


def test_used_up_presses_stop_once_a_week():
    lb.set_budget(3)
    _paper("2026-10-09", -5)                       # last week: doesn't count
    _paper("2026-10-13", -2, "a"); _paper("2026-10-14", +0.5, "b")
    st = lb.check(date(2026, 10, 14))
    assert st["used_r"] == 1.5 and st["left_r"] == 1.5 and not settings.load()["stopped"]
    _paper("2026-10-15", -1.7, "c")
    st = lb.check(date(2026, 10, 15))
    assert st["used_up"] and st["stopped_now"] and settings.load()["stopped"] and "used up" in st["line"]
    settings.change(stopped=False)                 # the user resumes: not pressed again this week
    assert not lb.check(date(2026, 10, 16)).get("stopped_now") and not settings.load()["stopped"]
    assert journal.load("orders_log")[-1]["source"] == "STOP"


def test_lowering_is_instant_raising_or_off_asks_first():
    lb.set_budget(5)
    assert lb.set_budget(3)["set"] and settings.load()["loss_budget_r"] == 3
    assert "needs" in lb.set_budget(10) and settings.load()["loss_budget_r"] == 3
    assert "needs" in lb.set_budget(0)
    assert lb.set_budget(10, confirm=True)["set"] and settings.load()["loss_budget_r"] == 10


def test_brief_and_desk_show_it():
    from botscope import brief, desk
    lb.set_budget(4)
    out = brief.brief(day=date(2026, 10, 14), weather={"weather": "choppy", "why": []}, events=[])
    assert any(line.startswith("Loss budget:") for line in out["lines"])
    assert desk.panel("budget")["budget_r"] == 4
