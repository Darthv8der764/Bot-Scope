"""The confidence meter: five levels, very low to very high. Never a made-up percentage.

Evidence, in order:
1. UNTESTED days from the last plain run_backtest (days the settings were not picked on): how many trades, did they
   make money after costs, and does the bad end of the reshuffle range (5th percentile) still make money?
2. LIVE PAPER results (closed trades on live days seen in BotScope): they can pull the level down, and the level is
   capped while there are only a few of them. A bot cannot look sure of itself on backtests alone.
"""
from __future__ import annotations

LEVELS = ("very low", "low", "medium", "high", "very high")
LIVE_FOR_HIGH = 10          # live paper trades needed before "high"
LIVE_FOR_VERY_HIGH = 30     # ... and before "very high"


def _live_summary(live_rs: list[float]) -> dict:
    n = len(live_rs)
    return {"trades": n, "avg_r": round(sum(live_rs) / n, 3) if n else None, "total_r": round(sum(live_rs), 2)}


def meter(untested: dict | None, live_rs: list[float] | None = None) -> dict:
    """{level, step 0-4, levels, why[], untested_trades, live: {...}}. `untested` = backtest.summarize() output."""
    u, live_rs = untested or {}, list(live_rs or [])
    n = u.get("trades", 0)
    why = []
    if not n:
        step = 0; why.append("no backtest on untested days yet (run run_backtest)")
    elif n < 30:
        step = 0; why.append(f"only {n} untested trades (need 30+)")
    elif u["avg_r"] <= 0:
        step = 0; why.append(f"loses money on untested days ({u['avg_r']:+.2f}R per trade after costs)")
    else:
        lo = (u.get("total_r_range_5_50_95") or [0])[0]
        if lo <= 0:
            step = 1; why.append(f"makes money on {n} untested trades, but the bad end of the range is a loss (could be luck)")
        elif n < 100:
            step = 2; why.append(f"makes money on {n} untested trades, even at the bad end of the range (small sample)")
        elif n < 300:
            step = 3; why.append(f"makes money on {n} untested trades, even at the bad end of the range")
        else:
            step = 4; why.append(f"makes money on {n} untested trades (300+), even at the bad end of the range")
    from .backtest import tight_stops                  # (here: backtest imports this module)
    if n and tight_stops(u):                           # R from stops a few cents away says nothing either way
        step = 0; why.append(f"R can't be trusted: {tight_stops(u)}")

    lv = _live_summary(live_rs)
    m = lv["trades"]
    if m >= LIVE_FOR_HIGH and lv["avg_r"] <= 0 and step > 0:     # losing live: down one level, and at most medium
        step -= 1; why.append(f"live paper is losing ({lv['avg_r']:+.2f}R per trade over {m} trades): down one level")
    losing = m >= LIVE_FOR_HIGH and lv["avg_r"] <= 0
    cap = 2 if m < LIVE_FOR_HIGH or losing else 3 if m < LIVE_FOR_VERY_HIGH else 4
    if step > cap:
        step = cap
        why.append(f"capped at {LEVELS[cap]}: live paper is not making money" if losing
                   else f"capped at {LEVELS[cap]}: only {m} live paper trades (need {LIVE_FOR_HIGH if cap == 2 else LIVE_FOR_VERY_HIGH}+)")
    elif m:
        why.append(f"{m} live paper trades, {lv['avg_r']:+.2f}R per trade")
    return {"level": LEVELS[step], "step": step, "levels": list(LEVELS), "why": why,
            "next_level": next_level(step, n, u, m, losing, cap), "untested_trades": n, "live": lv,
            "note": "Based on trade counts and results, not a probability. Not financial advice."}


def next_level(step: int, n: int, u: dict, m: int, losing: bool, cap: int) -> str:
    """What would have to happen for the meter to move up one level, in counts. Never a promise that it will."""
    if step >= 4:
        return "already at the top level"
    if losing:
        return "live paper has to stop losing; more trades alone won't move it"
    if n < 30:
        return f"{30 - n} more untested trades (a longer backtest), and they have to make money after costs"
    if u.get("avg_r", 0) <= 0:
        return "make money on untested days after costs; more trades alone won't move it"
    if step == cap and step < 4 and m < (LIVE_FOR_HIGH if cap == 2 else LIVE_FOR_VERY_HIGH):
        return f"{(LIVE_FOR_HIGH if cap == 2 else LIVE_FOR_VERY_HIGH) - m} more closed live paper trades that hold up"
    if step == 1:
        return "the bad end of the range has to be a gain too (usually more untested trades that keep making money)"
    need = {2: 100, 3: 300}.get(step)
    return f"{need - n} more untested trades that keep making money" if need and n < need else "keep logging paper trades"


def for_bot(bid: str) -> dict:
    """The meter from what is saved on this computer: the last plain backtest and the live paper log."""
    from . import journal
    last = (journal.find("backtests", bot=bid) or [{}])[-1]
    from .imports import live_rs
    m = meter(last.get("untested"), [r["r"] for r in journal.find("paper_results", bot=bid)] + live_rs(bid))
    m["backtest_saved_at"] = last.get("saved_at")
    return m
