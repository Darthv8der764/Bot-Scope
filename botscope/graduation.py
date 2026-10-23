"""The graduation test: a bot's live-money switch stays locked until it has earned it on paper.

Every check must pass; each one says what it needs and what the bot has. Turning live OFF always works at once.
Turning it ON needs: a passed test, the live switch in your own .env (BOTSCOPE_LIVE_TRADING=1), and your yes.
Not financial advice: passing means "enough honest evidence to try small", not "will make money".
"""
from __future__ import annotations

from . import confidence, drift, guard, journal, loader, report, settings

PAPER_DAYS = 20
PAPER_TRADES = 30


def test(bot: str) -> dict:
    cls = loader.get(bot)
    bid = loader.bot_id(cls)
    live = journal.find("paper_results", bot=bid)
    days = len({r["day"] for r in live})
    rs = [r["r"] for r in live]
    conf = confidence.for_bot(bid)
    dr = drift.for_bot(bid)
    rep = report.saved(cls) or {}
    u = rep.get("untested") or {}
    lk = (journal.find("luck", bot=bid) or [{}])[-1]
    rows = [
        ("Not labeled failed", "status is not 'failed'", cls.status, cls.status != "failed"),
        ("Paper days", f"{PAPER_DAYS}+ days with closed paper trades", str(days), days >= PAPER_DAYS),
        ("Paper trades", f"{PAPER_TRADES}+ closed paper trades", str(len(rs)), len(rs) >= PAPER_TRADES),
        ("Paper results", "making money after costs", f"{sum(rs) / len(rs):+.2f}R per trade" if rs else "none",
         bool(rs) and sum(rs) > 0),
        ("Confidence", "high or very high", conf["level"], conf["step"] >= 3),
        ("Honest report", "untested years make money", f"{u['avg_r']:+.2f}R per trade" if u.get("trades") else
         "not run yet", bool(u.get("trades")) and u["avg_r"] > 0),
        ("Report is for today's code", "bot unchanged since its honest report",
         "changed since its report" if report.changed_since(cls, rep) else "same code" if rep else "no report",
         bool(rep) and not report.changed_since(cls, rep)),
        ("Luck meter", "not 'looks like luck'", lk.get("level", "not run yet"),
         lk.get("level") in ("beats luck", "unclear")),
        ("Drift alarm", "not 'alarm'", dr["level"], dr["level"] in ("ok", "watch", "too good")),
    ]
    passed = all(r[3] for r in rows)
    return {"bot": cls.name, "id": bid, "passed": passed,
            "checks": [{"check": a, "needs": b, "has": c, "pass": d} for a, b, c, d in rows],
            "live_now": bid in settings.load()["live_bots"],
            "verdict": "graduated: it may be switched to live, small, with your yes" if passed else
                       f"not yet: {sum(not r[3] for r in rows)} of {len(rows)} checks to go",
            "note": "Passing means enough honest evidence to try small, not a promise. Not financial advice."}


def switch_live(bot: str, on: bool, confirm: bool = False) -> dict:
    cls = loader.get(bot)
    bid = loader.bot_id(cls)
    s = settings.load()
    if not on:
        settings.change(live_bots=[b for b in s["live_bots"] if b != bid])
        return {"bot": cls.name, "live": False, "note": "Back to paper only."}
    t = test(bot)
    if not t["passed"]:
        return {"bot": cls.name, "live": False, "blocked": "the graduation test is not passed", "test": t}
    if not guard.live_switch_on():
        return {"bot": cls.name, "live": False,
                "blocked": "the live switch is off: the user must add BOTSCOPE_LIVE_TRADING=1 to their own .env"}
    if not confirm:
        return {"bot": cls.name, "live": False, "question":
                f"Switch {cls.name} to REAL MONEY? Orders stay under ${s['max_order_usd']:,.0f} each and each one "
                "still asks first.", "needs": "confirm=true"}
    settings.change(live_bots=sorted(set(s["live_bots"]) | {bid}))
    return {"bot": cls.name, "live": True, "max_order_usd": s["max_order_usd"]}
