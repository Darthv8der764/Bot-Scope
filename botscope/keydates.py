"""Stock lookup + key dates: one stock's earnings (before open / after close), splits, dividends, and its biggest
move days over the last year, plus what's coming in the next 90 days. Each past date links to the chart on that day
so you can see how a bot would have traded it.

Sources: Finnhub earnings calendar (your free key), Alpaca corporate actions and SIP daily bars (your keys). A
"big move day" is measured, not a news claim: a close-to-close move at least 3x the stock's typical day. Not
financial advice.
"""
from __future__ import annotations

import statistics
from datetime import date, timedelta

BIG_X = 3.0           # a big move day = |move| >= 3x the median absolute daily move
MAX_BIG = 8


def big_move_days(closes: list[tuple[str, float]]) -> list[dict]:
    """[(day, close)] oldest first -> the biggest move days, newest first."""
    moves = [(closes[i][0], closes[i][1] / closes[i - 1][1] - 1) for i in range(1, len(closes))]
    if len(moves) < 20:
        return []
    typical = statistics.median(abs(m) for _, m in moves)
    big = sorted(((d, m) for d, m in moves if typical and abs(m) >= BIG_X * typical), key=lambda x: -abs(x[1]))
    return sorted(({"date": d, "kind": "big move", "event": f"{'up' if m > 0 else 'down'} {abs(m) * 100:.1f}% "
                    f"({abs(m) / typical:.0f}x a typical day)", "source": "Alpaca SIP daily bars"}
                   for d, m in big[:MAX_BIG]), key=lambda r: r["date"], reverse=True)


def _earnings(symbol: str, start: date, end: date) -> list[dict]:
    from .market_data import _http
    from .market_data.calendars import HOUR, _key
    d = _http.get("https://finnhub.io/api/v1/calendar/earnings",
                  {"symbol": symbol, "from": start.isoformat(), "to": end.isoformat(), "token": _key()},
                  ttl=12 * 3600, secret_params=("token",))
    return [{"date": r["date"], "kind": "earnings",
             "event": HOUR.get(r.get('hour') or '', r.get('hour')), "source": "Finnhub"}
            for r in d.get("earningsCalendar", []) if r.get("symbol") == symbol]


def _corporate(symbol: str, start: date, end: date) -> list[dict]:
    from .market_data import corporate
    return [{**r, "kind": "split" if "split" in r["event"] else "dividend",
             "event": r["event"].replace(f"{symbol} ", "", 1)} for r in corporate.upcoming([symbol], start, end)]


def _closes(symbol: str, start: date, end: date) -> list[tuple[str, float]]:
    from . import data
    return [(str(b.t.date()), b.c) for b in data.clean(data.bars(symbol, start, end, "1Day", "sip"))[0]]


def key_dates(symbol: str, today: date | None = None, earnings=None, corporate=None, closes=None) -> dict:
    sym = "".join(c for c in symbol.upper() if c.isalnum() or c == ".")[:10]
    if not sym:
        raise ValueError("give a ticker, e.g. AAPL")
    today = today or date.today()
    start, end = today - timedelta(days=365), today + timedelta(days=90)
    rows, problems = [], []
    for name, fn, a, b in (("earnings (Finnhub)", earnings or _earnings, start, end),
                           ("splits + dividends (Alpaca)", corporate or _corporate, start, end),
                           ("big move days (Alpaca bars)", lambda s, a, b: big_move_days((closes or _closes)(s, a, b)),
                            start, today - timedelta(days=1))):
        try:
            rows += fn(sym, a, b)
        except Exception as e:      # one missing source never blanks the rest
            problems.append(f"{name}: unavailable ({type(e).__name__}: {str(e)[:80]})")
    if not any(r["kind"] == "earnings" and r["date"] < str(today) for r in rows) and not problems[:1]:
        problems.append("past earnings: none returned (Finnhub's free calendar may only list recent and upcoming "
                        "ones); big move days often fall on them")
    for r in rows:
        r["when"] = "coming" if r["date"] >= str(today) else "past"
    rows.sort(key=lambda r: r["date"], reverse=True)
    return {"symbol": sym, "coming": sorted((r for r in rows if r["when"] == "coming"), key=lambda r: r["date"]),
            "past": [r for r in rows if r["when"] == "past"], "problems": problems,
            "window": {"from": str(start), "to": str(end)},
            "note": "Click a past date to open the chart on that day with a bot. Big move days are measured from "
                    "prices, not news. Information only. Not financial advice."}
