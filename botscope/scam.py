"""Scam checker: anything pasted or researched (a video transcript, article, "strategy", signal group pitch) is
checked for red flags BEFORE it's used. Verdict red / yellow / green with the reasons found.

Red is held back by default: you can read why and let it through on purpose (it's your call, and it's logged).
Green and yellow can go on to an honest backtest (the botscope-fact-check pipeline). A plain word list can't prove
something is a scam or that it's safe; it only says what to be careful about. Not financial advice.
"""
from __future__ import annotations

import re

from . import journal

# (name, why it matters, weight: 3 = red on its own, 1-2 = adds up to yellow/red, pattern)
FLAGS = [
    ("guaranteed returns", "nobody can guarantee market returns", 3,
     r"\bguarantee[ds]?\b.{0,40}\b(profit|return|income|gain|win)|\b(risk[- ]?free|can'?t lose|no[- ]risk|zero risk)\b"),
    ("too-good win rate", "real strategies lose often; 90%+ win claims usually hide big losses or cherry-picking", 2,
     r"\b(9[0-9]|100)\s?%\s*(win|accura|success|hit)|\bnever (lose|lost|had a losing)"),
    ("pay to join signals", "selling signals or a 'VIP' group pays them whether or not you win", 2,
     r"\b(vip|premium|private)\s+(group|channel|signals?|discord|telegram)|\bjoin (my|our) (discord|telegram|group)|\bsignals? (group|service)\b"),
    ("P/L screenshots as proof", "screenshots are easy to fake or cherry-pick; a full, checkable track record isn't", 1,
     r"\b(p&l|pnl|profit) (screenshot|proof)|\bscreenshots? (of|showing) (my )?(profits?|gains?|wins?)"),
    ("pump-and-dump wording", "pushing a small stock or coin to buy now is how pumps start", 3,
     r"\b(to the moon|next 100x|100x|1000x|load up now|before it explodes|hidden gem|about to (explode|moon))\b"),
    ("doubling down after losses", "martingale (bigger bets after losses) blows up accounts sooner or later", 3,
     r"\b(martingale|double (down|your (bet|position|size)) after (a )?loss|recover (your )?losses by)"),
    ("urgency", "'act now' pressure stops you from checking", 1,
     r"\b(act now|limited (time|spots?|seats?)|only \d+ spots?|last chance|today only|before it'?s too late)\b"),
    ("affiliate broker links", "they may earn money when you sign up or trade, win or lose", 1,
     r"\b(use my (link|code)|sign up (with|using) my|referral (link|code)|affiliate)\b"),
    ("get rich quick", "fast, life-changing money claims are a classic hook", 2,
     r"\b(quit (your|my) (job|9.?to.?5)|financial freedom in|get rich|passive income of \$|\$\d[\d,]* (a|per) (day|week) (easy|guaranteed))"),
]


def check(text: str) -> dict:
    found, score = [], 0
    low = " ".join(text.split())
    for name, why, w, pat in FLAGS:
        m = re.search(pat, low, re.I)
        if m:
            found.append({"flag": name, "why": why, "example": m.group(0)[:60]})
            score += w
    verdict = "red" if score >= 3 else "yellow" if score >= 1 else "green"
    return {"verdict": verdict, "score": score, "flags": found, "held_back": verdict == "red",
            "next": {"red": "Held back. Read the reasons; if you still want to test it, say so and it goes through "
                            "on purpose (logged).",
                     "yellow": "OK to test, carefully: the honest backtest (fact check) will show if the claims hold.",
                     "green": "No red flags found by this simple check (that doesn't make it good): next is the "
                              "honest backtest."}[verdict],
            "note": "A word check can miss scams and can flag honest posts. It's a warning light, not a verdict on "
                    "the person. Not financial advice."}


def let_through(source: str, reason: str) -> dict:
    """The user chose to test something that was flagged red. Logged so it's visible later."""
    journal.add("scam_overrides", {"source": source[:200], "reason": reason[:300]})
    return {"allowed": True, "logged": True,
            "note": "Going ahead on purpose. The honest backtest still decides; treat every claim as unproven."}
