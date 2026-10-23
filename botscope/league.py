"""Friends league: compare bots by an honest score, not raw profit. Each person exports a small league card (one
JSON file: untested results after costs, trade count, range, luck level, confidence; no keys, no account, no
dollars, no file paths) and shares it by hand (chat, USB, email). Cards dropped in data/league/ are read as data
only, never run. No server, no account.

Honest score = the bad end of the untested range per trade (5th percentile total / trades), in R, then lowered one
step for "looks like luck" on the luck meter and zeroed under 30 untested trades. Ties go to more trades."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from . import confidence, demo, journal, loader, report

VERSION = 1
MIN_TRADES = 30
FIELDS = {"bot": str, "owner": str, "timeframe": str, "untested_trades": int, "avg_r": float, "total_r": float,
          "range_low_r": float, "costs_r": float, "losing_years": int, "untested_years": int, "luck": str,
          "confidence": str, "report_day": str, "data": str}


def folder() -> Path:
    p = journal.folder().parent / "league"
    p.mkdir(parents=True, exist_ok=True)
    return p


def card(bot: str, owner: str = "me") -> dict:
    cls = loader.get(bot)
    bid = loader.bot_id(cls)
    rep = report.saved(cls)
    if not rep or not (rep.get("untested") or {}).get("trades"):
        raise ValueError(f"{bid} has no saved honest report yet: run honest_report first")
    u = rep["untested"]
    lk = (journal.find("luck", bot=bid) or [{}])[-1]
    c = {"league_card": VERSION, "bot": cls.name[:60], "owner": re.sub(r"[^\w .-]", "", owner)[:30] or "me",
         "timeframe": cls.timeframe, "untested_trades": u["trades"], "avg_r": u["avg_r"], "total_r": u["total_r"],
         "range_low_r": (u.get("total_r_range_5_50_95") or [u["total_r"]])[0], "costs_r": u.get("costs_r", 0.0),
         "losing_years": len(rep.get("losing_untested_years") or []),
         "untested_years": len((rep.get("years") or {}).get("untested") or []),
         "luck": lk.get("level", "not measured"), "confidence": confidence.for_bot(bid)["level"],
         "report_day": str(rep.get("saved_at", ""))[:10] or str(date.today()),
         "data": "DEMO (made-up prices)" if demo.active() else "real market data"}
    return c


def export(bot: str, owner: str = "me") -> dict:
    c = card(bot, owner)
    p = folder() / f"{re.sub(r'[^a-z0-9]+', '_', (c['owner'] + '_' + c['bot']).lower())}.league.json"
    p.write_text(json.dumps(c, indent=1))
    return {"file": str(p), "card": c,
            "note": "Share this one file by hand (chat, USB, email). It has no keys, no account, no dollars and no "
                    "file paths. Nothing is uploaded."}


def read(p: Path) -> dict | None:
    """A friend's card, checked field by field (anything else in the file is ignored). None if it isn't one."""
    try:
        raw = json.loads(p.read_text()[:20_000])
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict) or raw.get("league_card") != VERSION:
        return None
    out = {}
    for k, t in FIELDS.items():
        v = raw.get(k)
        if t is float and isinstance(v, int) and not isinstance(v, bool):
            v = float(v)
        if not isinstance(v, t) or isinstance(v, bool):
            return None
        out[k] = v[:60] if isinstance(v, str) else v
    return out


def score(c: dict) -> tuple[float, str]:
    n = c["untested_trades"]
    if n < MIN_TRADES:
        return 0.0, f"only {n} untested trades (need {MIN_TRADES}+): no score yet"
    s = round(c["range_low_r"] / n, 3)
    why = f"bad end of the range {c['range_low_r']:+.1f}R over {n} trades"
    if c["luck"] == "looks like luck":
        s = round(s - abs(s) - 0.05, 3); why += "; luck meter says it looks like luck: lowered"
    return s, why


def league() -> dict:
    rows, skipped = [], []
    for p in sorted(folder().glob("*.json")):
        c = read(p)
        if c is None:
            skipped.append(p.name); continue
        s, why = score(c)
        if not c["data"].startswith("real"):
            s, why = 0.0, "made on DEMO prices: no score"
        rows.append(c | {"honest_score": s, "why": why})
    rows.sort(key=lambda r: (r["honest_score"], r["untested_trades"]), reverse=True)
    for i, r in enumerate(rows, 1):
        r["place"] = i
    return {"folder": str(folder()), "table": rows, "skipped_files": skipped,
            "how": ("Honest score = the bad end of the untested range per trade, after costs (5th percentile of "
                    f"1,000 reshuffles / trades), lowered when the luck meter says luck, 0 under {MIN_TRADES} trades. "
                    "Raw profit isn't used: a lucky or tiny sample can't come out on top."),
            "note": "Cards are friends' own numbers, read as data and never run. Not financial advice."}
