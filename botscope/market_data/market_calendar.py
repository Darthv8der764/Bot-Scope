"""Market calendar: one list of dated events, each labeled with its source. Information only.
  holidays / half days   Alpaca trading calendar (your keys)
  options expiration     computed: 3rd Friday of each month (Thursday if that Friday is a holiday)
  Fed decisions          Kalshi KXFEDDECISION market dates (public)
  CPI, jobs, GDP, PCE... FRED release calendar (FRED_API_KEY)
  earnings               Finnhub, market movers + your bots' tickers only, before open / after close (FINNHUB_API_KEY)
  ex-dividends, splits   Alpaca corporate actions, same tickers (your keys)
A source that fails adds one 'unavailable' row instead of stopping the rest."""
import re
from datetime import date, timedelta

try:
    from . import _http, bot_tickers, calendars
except ImportError:
    import _http, bot_tickers, calendars  # noqa: E401

FRED_RELEASES = {"Employment Situation": "Jobs report", "Consumer Price Index": "CPI inflation",
                 "Producer Price Index": "PPI inflation", "Gross Domestic Product": "GDP",
                 "Personal Income and Outlays": "PCE inflation",
                 "Advance Monthly Sales for Retail and Food Services": "Retail sales"}


def _alpaca_days(start, end):
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetCalendarRequest
    from botscope.env import alpaca_keys
    cal = TradingClient(*alpaca_keys(), paper=True).get_calendar(GetCalendarRequest(start=start, end=end))
    return {c.date: c.close.strftime("%H:%M") for c in cal}


def market_hours(start, end):
    days, rows = _alpaca_days(start, end), []
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in days:
            rows.append({"date": str(d), "event": "Market closed (holiday)", "source": "Alpaca calendar"})
        elif d in days and days[d] < "16:00":
            rows.append({"date": str(d), "event": f"Half day, closes {days[d]} ET", "source": "Alpaca calendar"})
        d += timedelta(days=1)
    return rows, days


def opex(start, end, open_days=None):
    rows, m = [], date(start.year, start.month, 1)
    while m <= end:
        fri = m + timedelta(days=(4 - m.weekday()) % 7 + 14)
        if open_days is not None and fri not in open_days:
            fri -= timedelta(days=1)
        if start <= fri <= end:
            rows.append({"date": str(fri), "event": "Monthly options expiration", "source": "computed (3rd Friday)"})
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    return rows


def fed_meetings(start, end):
    d = _http.get("https://api.elections.kalshi.com/trade-api/v2/events",
                  {"series_ticker": "KXFEDDECISION", "status": "open"}, ttl=6 * 3600)
    out = []
    for e in d.get("events", []):
        day = (e.get("strike_date") or "")[:10]
        if day and str(start) <= day <= str(end):
            out.append({"date": day, "event": "Fed rate decision (2:00 PM ET)", "source": "Kalshi market date"})
    return out


def _short(e) -> str:
    """'X missing: long how-to' -> 'X missing (see .env.example)', so the table stays readable."""
    msg = str(e)
    if re.search(r"\b401\b|unauthorized", msg, re.I):        # not a raw "401 Authorization Required" web page
        return "Alpaca didn't accept your keys (make new paper keys at alpaca.markets)"
    return msg.split(":")[0] + " (free: add it in Studio's Get started tab)" if "missing" in msg.split(":")[0] else msg


def econ_releases(start, end):
    key = _http.need_key("FRED_API_KEY")
    base, kp = "https://api.stlouisfed.org/fred/", {"api_key": key, "file_type": "json"}
    rels = _http.get(base + "releases", {**kp, "limit": 1000}, ttl=7 * 86400, secret_params=("api_key",))
    ids = {r["name"]: r["id"] for r in rels["releases"] if r["name"] in FRED_RELEASES}
    out = []
    for name, rid in ids.items():
        d = _http.get(base + "release/dates", {**kp, "release_id": rid, "realtime_start": str(start),
                                               "realtime_end": str(end + timedelta(days=60)),
                                               "include_release_dates_with_no_data": "true"},
                      ttl=12 * 3600, secret_params=("api_key",))
        for r in d.get("release_dates", []):
            if str(start) <= r["date"] <= str(end):
                out.append({"date": r["date"], "event": f"{FRED_RELEASES[name]} (8:30 AM ET)", "source": "FRED release calendar"})
    return out


def earnings(start, end):
    rows = calendars.earnings((end - start).days, extra=bot_tickers.bot_tickers())
    return [{"date": r["date"], "event": f"{r['symbol']} earnings, {r['when']}", "source": "Finnhub"} for r in rows]


def dividends_splits(start, end):
    try:
        from . import corporate
    except ImportError:
        import corporate
    return corporate.upcoming(calendars.movers(bot_tickers.bot_tickers()), start, end)


def upcoming(days=30):
    start = date.today()
    end = start + timedelta(days=days)
    rows, open_days = [], None
    try:
        hours, open_days = market_hours(start, end)
        rows += hours
    except Exception as e:
        rows.append({"date": None, "event": f"holidays unavailable: {_short(e)}", "source": "Alpaca calendar"})
    rows += opex(start, end, open_days)
    for name, fn in (("Kalshi", fed_meetings), ("FRED", econ_releases), ("Finnhub", earnings),
                     ("Alpaca corporate actions", dividends_splits)):
        try:
            rows += fn(start, end)
        except Exception as e:
            rows.append({"date": None, "event": f"unavailable: {_short(e)}", "source": name})
    return sorted(rows, key=lambda r: (r["date"] or "9999", r["event"]))
