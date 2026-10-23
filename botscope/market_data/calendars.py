"""7. IPO calendar and earnings dates with BMO/AMC timing from Finnhub. Earnings are kept only for market movers:
the biggest S&P 500 weights, sector bellwethers, and the tickers passed in (what the bots hold or watch)."""
from datetime import date, timedelta

try:
    from . import _http
except ImportError:
    import _http

# Largest S&P 500 weights (approximate, checked 2026-10; update when the top 10 changes).
TOP_SP500 = ["NVDA", "MSFT", "AAPL", "AMZN", "META", "AVGO", "GOOGL", "GOOG", "TSLA", "BRK.B", "JPM", "LLY"]
BELLWETHERS = ["JPM", "WMT", "COST", "TSM", "ASML", "FDX"]
HOUR = {"bmo": "before open", "amc": "after close", "dmh": "during market", "": "time not set"}


def _key():
    k = _http.need_key("FINNHUB_API_KEY")
    return k


# Candidates for "market movers": every stock that has been near the top of the S&P 500 lately. The top 10 are
# picked from these by today's market cap (Finnhub), which is close to how S&P 500 weights work.
CANDIDATES = TOP_SP500 + ["ORCL", "NFLX", "XOM", "V", "MA", "UNH", "WMT", "COST", "HD", "PG", "JNJ", "ABBV", "BAC",
                          "PLTR", "AMD", "CRM", "KO", "CVX", "MU", "INTC"]


def by_market_cap(candidates=None, top=10, ttl=7 * 86400):
    """The biggest companies right now (market cap in $ billions from Finnhub), largest first. One call per
    candidate, cached a week."""
    rows = []
    for t in dict.fromkeys(c.upper() for c in (candidates or CANDIDATES)):
        if t == "GOOG":                       # same company as GOOGL
            continue
        d = _http.get("https://finnhub.io/api/v1/stock/profile2", {"symbol": t.replace(".", "-"), "token": _key()},
                      ttl=ttl, secret_params=("token",))
        cap = d.get("marketCapitalization")
        if cap:
            rows.append({"symbol": t, "market_cap_b": round(cap / 1000, 1), "source": "Finnhub company profile"})
    rows.sort(key=lambda r: -r["market_cap_b"])
    return rows[:top]


def movers(extra=(), live=True):
    """Market movers: the 10 biggest companies by today's market cap (falls back to TOP_SP500 if Finnhub is not
    set up), the bellwethers, and the given tickers."""
    top = TOP_SP500
    if live:
        try:
            top = [r["symbol"] for r in by_market_cap()] or TOP_SP500
        except Exception:
            top = TOP_SP500
    return sorted(set(top) | set(BELLWETHERS) | {t.upper() for t in extra})


def earnings(days=14, extra=(), ttl=6 * 3600):
    # Finnhub returns at most 1,500 rows per call (a busy earnings month is more), so ask one week at a time.
    start, keep, rows = date.today(), set(movers(extra)), []
    for wk in range(0, days + 1, 7):
        a, b = start + timedelta(days=wk), start + timedelta(days=min(wk + 6, days))
        d = _http.get("https://finnhub.io/api/v1/calendar/earnings",
                      {"from": a.isoformat(), "to": b.isoformat(), "token": _key()},
                      ttl=ttl, secret_params=("token",))
        rows += [{"source": "Finnhub", "date": r["date"], "symbol": r["symbol"],
                  "when": HOUR.get(r.get("hour") or "", r.get("hour")), "eps_est": r.get("epsEstimate")}
                 for r in d.get("earningsCalendar") or [] if r.get("symbol") in keep and r.get("date")]
    return sorted(rows, key=lambda r: (r["date"], r["symbol"]))


def ipos(days=30, ttl=6 * 3600):
    start = date.today()
    d = _http.get("https://finnhub.io/api/v1/calendar/ipo",
                  {"from": start.isoformat(), "to": (start + timedelta(days=days)).isoformat(), "token": _key()},
                  ttl=ttl, secret_params=("token",))
    return sorted(({"source": "Finnhub", "date": r.get("date"), "symbol": r.get("symbol"), "name": r.get("name"),
                    "exchange": r.get("exchange"), "price": r.get("price"), "status": r.get("status"),
                    "deal_size": r.get("totalSharesValue")} for r in d.get("ipoCalendar") or []),
                  key=lambda r: r["date"] or "")
