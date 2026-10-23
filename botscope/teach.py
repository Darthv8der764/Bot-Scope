"""Teach-me mode: the bot walks through one day like a tutor.

Built only from what the replay already recorded (each bar's decision and reason, the trades, the near misses), so
the lesson can never say something the bot didn't actually do. Plain words, short steps, one question at the end.
Not financial advice.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from . import view

MAX_WAIT_STEPS = 8
GLOSSARY = {
    "R": "the amount you risk on one trade (entry to stop). +2R = made twice what you risked; -1R = lost what you "
         "risked, which is the stop doing its job",
    "stop": "the price where the bot admits it was wrong and gets out, so one loss stays small",
    "target": "the price where the bot takes its profit",
    "long": "buying, hoping the price goes up",
    "short": "selling first, hoping to buy back cheaper",
    "costs": "fees and the gap between buy and sell prices; every trade pays them, win or lose",
    "near miss": "a trade the bot almost took but a rule blocked; shown so you can see if the rule helps",
}


def _hhmm(chart_t: int) -> str:
    return datetime.fromtimestamp(int(chart_t), timezone.utc).strftime("%H:%M")


def _shape(reason: str) -> str:
    """The reason without its numbers, so 'waiting' bars that only differ by a price group together."""
    return re.sub(r"[-+]?\d[\d.,:]*", "#", reason)


def _waits(reasons: dict, t_from: int | None, t_to: int | None) -> list[dict]:
    """Consecutive no-trade bars with the same kind of reason, merged into 'from - to: reason' steps."""
    out: list[dict] = []
    for t in sorted(reasons, key=int):
        x = reasons[t]
        if x["kind"] != "no_trade" or (t_from and int(t) < t_from) or (t_to and int(t) > t_to):
            continue
        if out and out[-1]["_shape"] == _shape(x["reason"]):
            out[-1]["to"] = _hhmm(int(t))
        else:
            out.append({"from": _hhmm(int(t)), "to": _hhmm(int(t)), "reason": x["reason"],
                        "_shape": _shape(x["reason"])})
    for w in out:
        del w["_shape"]
    if len(out) > MAX_WAIT_STEPS:
        out = out[:MAX_WAIT_STEPS // 2] + [{"from": "", "to": "", "reason": f"... {len(out) - MAX_WAIT_STEPS} more "
                                            "stretches of waiting ..."}] + out[-MAX_WAIT_STEPS // 2:]
    return out


def _trade_steps(t: dict, notional: float) -> list[str]:
    d = 1 if t["side"] == "long" else -1
    risk = abs(t["entry"] - t["stop"])
    risk_pct = risk / t["entry"] * 100 if t["entry"] else 0
    word = "bought" if t["side"] == "long" else "sold short"
    steps = [f"{_hhmm(t['t_in'])}: I {word} at {t['entry']:.2f}. Why: {t['why_in']}.",
             f"My stop was {t['stop']:.2f}, {risk:.2f} away ({risk_pct:.2f}% of the price). That distance is 1R: "
             f"the most I planned to lose on this trade (about ${notional * risk_pct / 100:,.0f} on a "
             f"${notional:,.0f} position)."]
    if t.get("target"):
        rr = abs(t["target"] - t["entry"]) / risk if risk else 0
        steps.append(f"My target was {t['target']:.2f}, {rr:.1f}R away: if it hit, I'd make {rr:.1f}x what I risked.")
    else:
        steps.append("I had no fixed target: I planned to get out on my exit rule instead.")
    if t.get("open"):
        steps.append("The trade is still open, so the lesson isn't finished yet.")
        return steps
    r = t["r"]
    moved = (t["exit"] - t["entry"]) * d
    steps.append(f"{_hhmm(t['t_out'])}: I got out at {t['exit']:.2f} ({t['why_out']}). Result after costs: {r:+.2f}R "
                 f"(about {'+' if r >= 0 else '-'}${abs(notional * r * risk_pct / 100):,.0f}).")
    if r <= -0.9:
        steps.append("A full loss, but a planned one: the stop kept it to about 1R. Losing trades are normal; what "
                     "matters is whether the wins add up to more over many trades.")
    elif r < 0:
        steps.append("A small loss: the price moved my way" if moved > 0 else "A small loss: I got out before the stop")
        steps[-1] += ", but costs and the exit left me slightly down."
    elif r >= 1:
        steps.append("A win bigger than the risk. One good day proves nothing, though: check the honest report for "
                     "how this works over hundreds of trades.")
    else:
        steps.append("A small win, smaller than the amount I risked.")
    return steps


def lesson(st: dict, notional: float = 10_000) -> dict:
    """The tutor's walk-through from a view.build() result."""
    bot, trades = st["bot"], st["trades"]
    first = trades[0]["t_in"] if trades else None
    parts = [{"title": "My rules", "steps": list(bot["rules"])},
             {"title": "Before my first trade" if trades else "Waiting all day",
              "steps": [f"{w['from']}-{w['to']}: {w['reason']}" if w["from"] else w["reason"]
                        for w in _waits(st["reasons"], None, first)]}]
    for n, t in enumerate(trades, 1):
        parts.append({"title": f"Trade {n} ({t['side']})", "steps": _trade_steps(t, notional)})
    for g in st.get("ghosts", [])[:3]:
        parts.append({"title": f"Near miss at {_hhmm(g['t_in'])}",
                      "steps": [f"I almost went {g['side']} here ({g['why_in']}) but a rule said no.",
                                f"If I had, it would have ended {g['r']:+.2f}R ({g['why_out']}). "
                                + ("The rule saved me." if g["r"] < 0 else "The rule cost me this time; one near "
                                   "miss is luck either way, the honest report counts all of them.")]})
    for v in st.get("vetoed", []):
        parts.append({"title": f"You vetoed my trade at {_hhmm(v['t'])}",
                      "steps": [f"I wanted to go {v['side']} at {v['price']:.2f} ({v['why_in']}); you said no."]
                      + ([f"It would have ended {v['would_have_r']:+.2f}R, so your veto "
                          f"{'helped' if v['would_have_r'] < 0 else 'cost'} this time."]
                         if v.get("would_have_r") is not None else [])})
    text = " ".join(s for p in parts for s in p["steps"])
    used = [k for k in GLOSSARY if re.search(rf"\b{re.escape(k)}\b", text, re.I) or (k == "R" and "R " in text)]
    side = trades[0]["side"] if trades else None
    quiz = (f"Quiz: before you look at the result, where would you have put the stop on that {side} trade, and why?"
            if trades else "Quiz: looking at the chart, was there a moment you'd have traded? Which of my rules "
            "would have said no?")
    return {"bot": bot["name"], "symbol": st["symbol"], "day": st["day"], "data": st["source"],
            "account": st["account"], "lesson": parts, "words_used": {k: GLOSSARY[k] for k in used}, "quiz": quiz,
            "note": "One day is a story, not proof. Not financial advice."}


def teach_me(bot: str, symbol: str | None = None, day: str | None = None, notional: float = 10_000) -> dict:
    return lesson(view.build(bot, symbol, day), notional)
