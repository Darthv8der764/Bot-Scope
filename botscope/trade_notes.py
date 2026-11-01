"""Trade notes: your own notes on each of your trades, saved in the journal (`trade_notes`, this computer only).

A note holds a setup tag (your own word, e.g. "pullback", so trades can be grouped by setup), the stop you had in
mind (it gives the trade's R: how many times the risk it made or lost), a free note, and your answers to the
pre-trade checklist. The answers are only stored here: nothing in BotScope draws conclusions from them. Notes are kept
by trade id, so they stay attached when the same trades are imported again. Not financial advice.
"""
from __future__ import annotations

from . import journal

CHOICES = {"last_trade": ("win", "loss", "none today"), "big_news": ("yes", "no", "not sure"),
           "feeling": ("calm", "rushed", "frustrated", "excited", "bored")}
CHECKLIST = ("setup", "stop", "risk", "target", "last_trade", "trades_today", "big_news", "feeling")
MAX_TEXT = 500


def _trade(trade_id: str) -> dict:
    t = next((r for r in journal.load("my_trades") if r.get("trade_id") == trade_id), None)
    if not t:
        raise ValueError(f"no trade with id {trade_id}: list your trades to see their ids")
    return t


def r_of(t: dict, stop: float | None) -> float | None:
    """R = what the trade made per unit of risk (entry to stop). None when there's no stop."""
    if not stop or stop == t["entry"]:
        return None
    d = 1 if t["side"] == "long" else -1
    return round((t["exit"] - t["entry"]) * d / abs(t["entry"] - stop), 2)


def checklist_answers(answers: dict | None) -> dict:
    """Your checklist answers, checked against the list in docs (unknown questions and choices say so)."""
    out = {}
    for k, v in (answers or {}).items():
        if k not in CHECKLIST:
            raise ValueError(f"unknown checklist question '{k}' (known: {', '.join(CHECKLIST)})")
        v = str(v if v is not None else "").strip()[:MAX_TEXT]
        if k in CHOICES and v and v.lower() not in CHOICES[k]:
            raise ValueError(f"'{k}' is one of: {', '.join(CHOICES[k])}")
        if k == "trades_today" and v and not v.isdigit():
            raise ValueError("'trades_today' is a whole number")
        out[k] = v.lower() if k in CHOICES else v
    return out


def note(trade_id: str, setup: str | None = None, stop: float | None = None, note: str | None = None,
         checklist: dict | None = None) -> dict:
    """Save (or change) the note on one trade. A field left out keeps what was there; "" clears a text field and
    stop=0 clears the stop. Returns the trade with its note and R."""
    t = _trade(trade_id)
    old = next(iter(journal.find("trade_notes", trade_id=trade_id)), {})
    row = {k: old.get(k) for k in ("setup", "stop", "note", "checklist")}
    if setup is not None:
        row["setup"] = str(setup).strip().lower()[:40] or None
    if note is not None:
        row["note"] = str(note).strip()[:MAX_TEXT] or None
    if stop is not None:
        stop = float(stop)
        if stop < 0:
            raise ValueError("a stop is a price above 0 (or 0 to clear it)")
        if stop and (stop >= t["entry"] if t["side"] == "long" else stop <= t["entry"]):
            raise ValueError(f"a {t['side']}'s stop is {'below' if t['side'] == 'long' else 'above'} its entry "
                             f"({t['entry']})")
        row["stop"] = stop or None
    if checklist is not None:
        merged = {**(row.get("checklist") or {}), **checklist_answers(checklist)}
        row["checklist"] = {k: v for k, v in merged.items() if v}          # "" clears an answer
    journal.upsert("trade_notes", {"trade_id": trade_id}, row)
    return with_notes([t])[0]


def with_notes(trades: list[dict]) -> list[dict]:
    """Trades with their note fields (setup, stop, r, note, checklist) added; no note = those fields are empty."""
    notes = {n["trade_id"]: n for n in journal.load("trade_notes")}
    out = []
    for t in trades:
        n = notes.get(t.get("trade_id"), {})
        out.append({**t, "setup": n.get("setup"), "stop": n.get("stop"), "r": r_of(t, n.get("stop")),
                    "note": n.get("note"), "checklist": n.get("checklist") or {}})
    return out
