"""Repeated vetoes become a suggested rule. If you keep vetoing the same kind of trade (shorts, late trades, one
ticker, far stops), BotScope writes that pattern down as a rule idea, backtests it honestly (tuned vs untested days,
with and without the rule), and saves it as a SUGGESTION. It is never applied by itself: the bot only changes if
you approve it and edit the bot. Not financial advice."""
from __future__ import annotations

import re
from collections import Counter
from datetime import time

from . import backtest, journal, loader, report

MIN_VETOES = 3          # a pattern needs at least this many vetoes
SHARE = 0.75            # ... and this share of all the bot's vetoes
BROAD = 0.4             # a rule that leaves fewer than 40% of the trades is too broad to call a filter
_STOP = set("the a an i it this that to of and too was is on in at for my not be so its it's way".split())


def _features(v: dict) -> dict:
    m = re.search(r"_(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})$", v.get("trade_id", ""))
    t = time(int(m.group(2)), int(m.group(3))) if m else None
    risk = abs(v["entry"] - v["stop"]) / v["entry"] * 100 if v.get("entry") and v.get("stop") else None
    return {"side": v.get("side"), "time": t, "symbol": v.get("symbol"), "risk_pct": risk}


def patterns(vetoes: list[dict]) -> list[dict]:
    """Candidate rules from what the vetoes have in common. [{filters, plain, evidence}]"""
    n = len(vetoes)
    if n < MIN_VETOES:
        return []
    f = [_features(v) for v in vetoes]
    need = max(MIN_VETOES, int(SHARE * n + 0.999))
    out = []
    side, k = Counter(x["side"] for x in f).most_common(1)[0]
    if side and k >= need:
        out.append({"filters": {"skip_side": side}, "plain": f"Skip {side} trades.",
                    "evidence": f"{k} of your {n} vetoes were {side}s"})
    sym, k = Counter(x["symbol"] for x in f).most_common(1)[0]
    if sym and k >= need:
        out.append({"filters": {"skip_symbols": [sym]}, "plain": f"Don't trade {sym} with this bot.",
                    "evidence": f"{k} of your {n} vetoes were on {sym}"})
    times = sorted(x["time"] for x in f if x["time"])
    if len(times) >= need:
        late = times[-need]                           # the earliest time that still covers `need` of the vetoes
        cut = f"{late.hour:02d}:{max(late.minute - 1, 0):02d}" if late.minute else f"{late.hour - 1:02d}:59"
        out.append({"filters": {"skip_after": cut}, "plain": f"No new trades after {cut}.",
                    "evidence": f"{need} of your {n} vetoes were at {late:%H:%M} or later"})
        early = times[need - 1]
        cut2 = f"{early.hour:02d}:{early.minute + 1:02d}" if early.minute < 59 else f"{early.hour + 1:02d}:00"
        out.append({"filters": {"skip_before": cut2}, "plain": f"No trades before {cut2}.",
                    "evidence": f"{need} of your {n} vetoes were at {early:%H:%M} or earlier"})
    risks = sorted(x["risk_pct"] for x in f if x["risk_pct"])
    if len(risks) >= need:
        r = risks[-need]
        lim = round(r * 0.95, 3)
        out.append({"filters": {"max_risk_pct": lim}, "plain": f"Skip trades whose stop is more than {lim}% away.",
                    "evidence": f"{need} of your {n} vetoes had stops {r:.2f}% or more away"})
    words = Counter(w for v in vetoes for w in re.findall(r"[a-z']+", (v.get("reason") or "").lower())
                    if w not in _STOP and len(w) > 2)
    common = [w for w, c in words.most_common(3) if c >= 2]
    for p in out:
        if common:
            p["your_words"] = common
    return out


def _cmp(before: dict, after: dict) -> dict:
    rows = {}
    for period in ("tuned", "untested"):
        b, a = before["periods"].get(period), after["periods"].get(period)
        if b is None:
            continue
        rows[period] = {"trades_before": b.get("trades", 0), "trades_after": a.get("trades", 0),
                        "total_r_before": b.get("total_r", 0.0), "total_r_after": a.get("total_r", 0.0),
                        "avg_r_before": b.get("avg_r"), "avg_r_after": a.get("avg_r")}
    u = rows.get("untested", {})
    if not u or not u["trades_before"]:
        verdict = "can't tell: no untested trades"
    elif u["trades_after"] == u["trades_before"]:
        verdict = "no effect: the rule never triggered on untested days"
    else:
        diff = round(u["total_r_after"] - u["total_r_before"], 2)
        skipped = u["trades_before"] - u["trades_after"]
        verdict = (f"{'helps' if diff > 0 else 'hurts' if diff < 0 else 'no change'} on untested days: "
                   f"{diff:+.2f}R total, skipping {skipped} trade(s)")
        if skipped < 10:
            verdict += " (fewer than 10 trades skipped, so this could be luck)"
    return {"before_after": rows, "verdict": verdict}


def suggest(bot: str, fetch=None, days: int = backtest.QUICK_DAYS) -> dict:
    cls = loader.get(bot)
    bid = loader.bot_id(cls)
    vetoes = journal.find("vetoes", bot=bid)
    cands = patterns(vetoes)
    if not cands:
        return {"bot": cls.name, "vetoes": len(vetoes), "suggestions": [],
                "note": f"No repeated pattern yet (needs {MIN_VETOES}+ vetoes with something in common)."}
    before = backtest.run(cls, days=days, fetch=fetch)
    out, too_broad = [], []
    for c in cands:
        after = backtest.run(cls, days=days, fetch=fetch, filters=c["filters"])
        row = c | _cmp(before, after)
        u = row["before_after"].get("untested", {})
        if u.get("trades_before") and u["trades_after"] < BROAD * u["trades_before"]:
            too_broad.append(f"{c['plain']} (would skip {u['trades_before'] - u['trades_after']} of "
                             f"{u['trades_before']} untested trades: that's a different bot, not a filter)")
            continue
        saved = journal.upsert("rule_ideas", {"bot": bid, "from": "repeated vetoes", "filters": c["filters"]},
                               {"plain": c["plain"], "evidence": c["evidence"], "verdict": row["verdict"],
                                "before_after": row["before_after"],
                                "status": "suggested, NOT applied: edit the bot only if you approve"})
        out.append(row | {"saved_id": saved["id"]})
    out.sort(key=lambda r: -((r["before_after"].get("untested", {}).get("total_r_after") or 0)
                             - (r["before_after"].get("untested", {}).get("total_r_before") or 0)))
    return {"bot": cls.name, "vetoes": len(vetoes), "suggestions": out, "left_out_too_broad": too_broad,
            "data": report.data_line(list(cls.symbols)),
            "note": "Suggestions only. Nothing was changed. 'untested' days are the honest test; ask the user before "
                    "changing the bot. Not financial advice."}
