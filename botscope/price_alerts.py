"""Plain-English alerts: "tell me when NVDA breaks yesterday's high" becomes a saved rule, checked against finished
candles and sent to your own channels (ntfy / Discord / Telegram). Information only: an alert never trades, and
each rule fires at most once a day.

Understood: breaks / goes above / falls below yesterday's high or low, a price ("above 600", "below $590"), the
N-day average ("crosses its 50-day average"), and moves ("moves 3%", "is up 2%", "drops 2% in a day", "jumps 4%").
Bitcoin / ether by name (or BTC / ETH) mean the BTC/USD and ETH/USD pairs, and "50k" means 50,000.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta

from . import alerts, data, journal

EXAMPLES = ["tell me when NVDA breaks yesterday's high", "when SPY falls below 590", "when AAPL moves 3% today",
            "when TSLA crosses its 50-day average"]
_NOT = {"I", "A", "ME", "WHEN", "ITS", "THE", "DAY", "UP", "DOWN"}
_CRYPTO = {"bitcoin": "BTC/USD", "btc": "BTC/USD", "ether": "ETH/USD", "ethereum": "ETH/USD", "eth": "ETH/USD"}
_DOWN_MOVE = r"down|drops?|falls?|sinks?|slides?|tanks?|loses"
_UP_MOVE = r"up|rises?|jumps?|gains?|climbs?|rallies|rally|pops?"


def parse(text: str) -> dict:
    t = text.strip()
    low = t.lower()
    t = re.sub(r"(\d+(?:\.\d+)?)\s*k\b", lambda m: f"{float(m.group(1)) * 1000:g}", t, flags=re.I)   # 50k -> 50000
    low = t.lower()
    syms = [w for w in re.findall(r"\b([A-Z]{1,5}(?:/USD)?)\b", t) if w not in _NOT]
    if not syms and (m := re.search(r"\b(" + "|".join(_CRYPTO) + r")\b", low)):
        syms = [_CRYPTO[m.group(1)]]
    syms = [_CRYPTO.get(w.lower(), w) if "/" not in w else w for w in syms]
    if not syms:
        raise ValueError("name the ticker in capitals, e.g. " + "; ".join(EXAMPLES))
    sym = syms[0]
    down = bool(re.search(r"below|under|drops?|falls?|breaks? down|loses", low))
    if m := re.search(r"yesterday'?s?\s+(high|low)", low):
        level = m.group(1)
        side = "below" if down or (level == "low" and not re.search(r"above|over", low)) else "above"
        return {"symbol": sym, "kind": "yesterday", "level": level, "side": side}
    if m := re.search(r"(\d+)[- ]day (?:moving )?average", low):
        side = "below" if down else "above" if re.search(r"above|over|breaks", low) else "cross"
        return {"symbol": sym, "kind": "average", "days": int(m.group(1)), "side": side}
    if m := re.search(rf"\b({_UP_MOVE}|{_DOWN_MOVE}|moves?|swings?)\b\D{{0,12}}?(\d+(?:\.\d+)?)\s*%", low):
        word = m.group(1)
        return {"symbol": sym, "kind": "move", "pct": float(m.group(2)),
                "side": "up" if re.fullmatch(_UP_MOVE, word) else "down" if re.fullmatch(_DOWN_MOVE, word) else "either"}
    if m := re.search(r"(above|over|below|under|hits?|reaches|breaks?|falls? (?:to|below)|drops? (?:to|below))\s*\$?\s*(\d+(?:\.\d+)?)", low):
        return {"symbol": sym, "kind": "price", "price": float(m.group(2)), "side": "below" if down else "above"}
    raise ValueError("couldn't read a level from that; try e.g. " + "; ".join(EXAMPLES))


def describe(r: dict) -> str:
    s = r["symbol"]
    if r["kind"] == "yesterday":
        return f"{s} goes {r['side']} yesterday's {r['level']}"
    if r["kind"] == "average":
        return f"{s} {'crosses' if r['side'] == 'cross' else 'goes ' + r['side']} its {r['days']}-day average"
    if r["kind"] == "move":
        return f"{s} moves {'up ' if r['side'] == 'up' else 'down ' if r['side'] == 'down' else ''}{r['pct']:g}% from yesterday's close"
    return f"{s} goes {r['side']} {r['price']:g}"


def add(text: str) -> dict:
    rule = parse(text)
    row = journal.add("alert_rules", {"id": uuid.uuid4().hex[:8], "text": text.strip()[:200], "rule": rule,
                                      "reads_as": describe(rule), "fired_on": None})
    return {"added": row["id"], "reads_as": row["reads_as"],
            "next": "check_alerts checks every rule now; run `botscope check_alerts` on a schedule to keep watching.",
            "note": "Information only: an alert never places a trade."}


def remove(rule_id: str) -> dict:
    return {"removed": journal.remove("alert_rules", rule_id)}


def _hit(r: dict, today_bars, daily) -> tuple[bool, str]:
    last = today_bars[-1].c
    prev = daily[-1] if daily else None
    if r["kind"] == "yesterday":
        lvl = prev.h if r["level"] == "high" else prev.l
        ok = last > lvl if r["side"] == "above" else last < lvl
        return ok, f"{last:.2f} vs yesterday's {r['level']} {lvl:.2f}"
    if r["kind"] == "price":
        ok = last > r["price"] if r["side"] == "above" else last < r["price"]
        return ok, f"{last:.2f} vs {r['price']:g}"
    if r["kind"] == "move":
        ch = (last / prev.c - 1) * 100
        ok = ch >= r["pct"] if r["side"] == "up" else ch <= -r["pct"] if r["side"] == "down" else abs(ch) >= r["pct"]
        return ok, f"{ch:+.2f}% from yesterday's close {prev.c:.2f}"
    closes = [b.c for b in daily[-r["days"]:]]
    if len(closes) < r["days"]:
        return False, "not enough days for the average yet"
    avg = sum(closes) / len(closes)
    was_above = daily[-1].c > avg
    ok = (last > avg and not was_above) if r["side"] == "above" else (last < avg and was_above) if r["side"] == "below" \
        else (last > avg) != was_above
    return ok, f"{last:.2f} vs the {r['days']}-day average {avg:.2f}"


def check(today: date | None = None, send=None) -> dict:
    today = today or date.today()
    rows = journal.load("alert_rules")
    out, fired = [], []
    for row in rows:
        r = row["rule"]
        try:
            bs, src = data.day_bars(r["symbol"], today, "5Min")
            bs = data.clean(bs)[0]
            if not data.is_crypto(r["symbol"]):                 # stocks: regular hours only (9:30-16:00 New York)
                bs = data.by_session(bs).get(today, [])
            daily = [b for b in data.clean(data.bars(r["symbol"], today - timedelta(days=max(30, r.get("days", 0) * 2)),
                                                     today - timedelta(days=1), "1Day", "sip"))[0] if b.t.date() < today]
            if not bs or not daily:
                out.append({"id": row["id"], "reads_as": row["reads_as"], "status": "no candles yet today"}); continue
            hit, detail = _hit(r, bs, daily)
        except (RuntimeError, ValueError) as e:
            out.append({"id": row["id"], "reads_as": row["reads_as"], "status": f"can't check: {e}"}); continue
        status = "hit" if hit else "not yet"
        if hit and row.get("fired_on") == str(today):
            status = "hit (already sent today)"
        elif hit:
            res = (send or alerts.send)(f"BotScope alert: {r['symbol']}", f"{row['reads_as']}: {detail}. Info only.", "bell")
            journal.upsert("alert_rules", {"id": row["id"]}, {**{k: v for k, v in row.items() if k != "id"},
                                                               "fired_on": str(today)})
            fired.append({"id": row["id"], "sent": res.get("sent", False)} | ({} if res.get("sent") else
                                                                                {"why": res.get("why", "")}))
        out.append({"id": row["id"], "reads_as": row["reads_as"], "status": status, "detail": detail,
                    "as_of": bs[-1].t.isoformat(), "source": src})
    return {"rules": out, "fired": fired, "note": "Information only: alerts never trade. Each rule sends at most once a day."}
