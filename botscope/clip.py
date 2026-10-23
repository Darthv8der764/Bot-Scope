"""Trade clip: one trade's replay as a short WebM video with its honest label burned in (paper, tuned or untested
day, result in R after costs, the bot's confidence level, "one trade says little"). The /clip page draws the
candles one by one and records them in the browser; the file is saved on this computer only (data/clips/), never
uploaded. WebM (not GIF): browsers record it without extra software."""
from __future__ import annotations

import re
from datetime import date, datetime

from . import confidence, demo, journal, loader, report, view

MAX_BYTES = 8_000_000
BEFORE, AFTER = 30, 10
MAX_CANDLES = 120


def folder():
    p = journal.folder().parent / "clips"
    p.mkdir(parents=True, exist_ok=True)
    return p


def clip_data(bot: str, symbol: str | None = None, day: str | None = None, trade_id: str | None = None) -> dict:
    st = view.build(bot, symbol, day)
    done = [t for t in st["trades"] if not t["open"]]
    if not done:
        raise ValueError(f"no finished trade for {st['bot']['id']} on {st['symbol']} {st['day']}: pick another day")
    t = next((x for x in done if x["id"] == trade_id), done[-1])
    times = [c["time"] for c in st["candles"]]
    i0 = max(0, next(i for i, x in enumerate(times) if x >= t["t_in"]) - BEFORE)
    i1 = min(len(times), next((i for i, x in enumerate(times) if x >= t["t_out"]), len(times) - 1) + AFTER + 1)
    cs = st["candles"][i0:i1]
    k = -(-len(cs) // MAX_CANDLES)                          # long trades: merge candles so the clip stays short
    if k > 1:
        cs = [{"time": g[0]["time"], "open": g[0]["open"], "close": g[-1]["close"], "high": max(c["high"] for c in g),
               "low": min(c["low"] for c in g)} for g in (cs[j:j + k] for j in range(0, len(cs), k))]
    cls = loader.get(bot)
    d = date.fromisoformat(st["day"])
    period = "TUNED day (settings were picked here)" if report._tuned(cls, d, d) else "UNTESTED day"
    lvl = confidence.for_bot(st["bot"]["id"])["level"]
    label = [f"{st['bot']['name']} · {st['symbol']} · {st['day']} · {t['side']}",
             f"{'DEMO DATA · ' if demo.active() else ''}{st['account']} · {period}",
             f"Result {t['r']:+.2f}R after costs ({t['why_out']}) · confidence {lvl}",
             "One trade says little: see the bot's nutrition label. Not financial advice."]
    return {"bot": st["bot"]["id"], "symbol": st["symbol"], "day": st["day"], "trade": t,
            "candles": cs, "merged": k, "label": label, "timeframe": cls.timeframe,
            "name": re.sub(r"[^A-Za-z0-9_-]+", "_", f"{st['bot']['id']}_{st['symbol']}_{st['day']}_{t['id']}")}


def save(name: str, blob: bytes) -> dict:
    if not blob.startswith(b"\x1a\x45\xdf\xa3"):          # every WebM file starts with the EBML magic number
        raise ValueError("not a WebM video")
    if len(blob) > MAX_BYTES:
        raise ValueError("clip too big (8 MB max)")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name)[:120] or "clip"
    p = folder() / f"{safe}_{datetime.now():%H%M%S}.webm"
    p.write_bytes(blob)
    return {"saved": str(p), "bytes": len(blob), "note": "Saved on this computer only. Nothing was uploaded."}
