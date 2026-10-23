"""The drift alarm: are live paper results still what the backtest said to expect?

It draws 1,000 pretend runs of the same number of trades from the bot's UNTESTED backtest trades and counts how many
did worse than the live paper results. If almost none did (fewer than 50 of 1,000), live trading has drifted away
from the backtest: the market changed, the bot has a bug live, or the backtest was too kind. Counts, not a
probability. Not financial advice.
"""
from __future__ import annotations

import random

from . import journal, loader

MIN_LIVE = 10
SIMS = 1000


def check(live_rs: list[float], backtest_rs: list[float], seed: int = 11) -> dict:
    n = len(live_rs)
    if n < MIN_LIVE:
        return {"level": "not enough live trades", "live_trades": n,
                "why": [f"only {n} live paper trades (needs {MIN_LIVE}+ before drift can be judged)"]}
    if len(backtest_rs) < 10:
        return {"level": "no backtest to compare", "live_trades": n,
                "why": ["no saved untested backtest trades: run run_backtest or honest_report first"]}
    rng = random.Random(seed)
    live = round(sum(live_rs), 2)
    sims = sorted(sum(rng.choice(backtest_rs) for _ in range(n)) for _ in range(SIMS))
    worse = sum(s < live for s in sims)
    exp = round(sum(backtest_rs) / len(backtest_rs) * n, 2)
    why = [f"live paper: {live:+.2f}R over {n} trades; the backtest expected about {exp:+.2f}R",
           f"{worse} of {SIMS} backtest-like runs did worse than live"]
    if worse < 50:
        level = "alarm"
        why.append("live is worse than almost every backtest-like run: something changed. Pause the bot and look.")
    elif worse < 100:
        level = "watch"
        why.append("live is near the bad end of what the backtest allows: keep an eye on it")
    elif worse > 990:
        level = "too good"
        why.append("live is better than almost every backtest-like run: nice, but check for a bug or luck")
    else:
        level = "ok"
        why.append("live results fit what the backtest expected")
    return {"level": level, "live_trades": n, "live_total_r": live, "expected_total_r": exp,
            "backtest_runs_worse": worse, "runs": SIMS, "why": why}


def for_bot(bot: str) -> dict:
    cls = loader.get(bot)
    bid = loader.bot_id(cls)
    live = [r["r"] for r in journal.find("paper_results", bot=bid)]
    bt = (journal.find("backtests", bot=bid) or [{}])[-1].get("untested_rs") or []
    return {"bot": cls.name} | check(live, bt) | {
        "note": "Live = paper trades logged by BotScope after the close. Counts, not a probability. Not financial advice."}
