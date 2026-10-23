"""Zoom stack: the same moment on 1-minute, 15-minute and daily candles, stacked, so you can see the small move
inside the bigger picture. Information only. Data: Alpaca SIP with your own keys (cached on this computer)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import data
from .data import ET

LEVELS = [("1Min", 0, "1-minute: that day"), ("15Min", 7, "15-minute: the week up to it"),
          ("1Day", 180, "Daily: about 6 months up to it")]


def chart_time(t: datetime) -> int:
    """New York wall-clock time as the chart's UTC seconds (same as the bot view)."""
    return int(t.timestamp() + t.utcoffset().total_seconds())


def _day0(d: date) -> int:
    return chart_time(datetime.combine(d, datetime.min.time(), ET))


def stack(symbol: str, day: str, hhmm: str | None = None, fetch=None) -> dict:
    fetch = fetch or data.bars
    d = date.fromisoformat(day)
    at = datetime.combine(d, datetime.strptime(hhmm or "09:30", "%H:%M").time(), ET)
    out, problems = [], []
    for tf, back, title in LEVELS:
        try:
            bs, _ = data.clean(fetch(symbol.upper(), d - timedelta(days=back), d, tf, "sip"))
        except RuntimeError:
            raise
        except Exception as e:
            problems.append(f"{tf}: no data ({type(e).__name__})"); bs = []
        if tf != "1Day":
            bs = [b for b in bs if (9, 30) <= (b.t.hour, b.t.minute) < (16, 0)]
        mark = chart_time(at) if tf != "1Day" else _day0(d)
        out.append({"timeframe": tf, "title": title, "mark": mark,
                    "candles": [{"time": chart_time(b.t) if tf != "1Day" else _day0(b.t.date()),
                                 "open": b.o, "high": b.h, "low": b.l, "close": b.c} for b in bs]})
    return {"symbol": symbol.upper(), "day": day, "at": at.strftime("%H:%M"), "levels": out,
            "problems": problems, "source": "Alpaca SIP (all US exchanges), your own keys",
            "note": "The yellow line marks the same moment on each chart. Information only, not financial advice."}
