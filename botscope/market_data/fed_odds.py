"""1. Fed rate odds from Kalshi's public market data (no account). Every row says its source.
Kalshi: series KXFEDDECISION (cut / hold / hike per meeting). Polymarket is left out: it is blocked on some home
networks. Prediction-market odds can differ from CME FedWatch (paid).
Price of a YES contract in dollars ~= the market's probability. Kalshi rows use the bid/ask midpoint when both
exist, else the last trade."""
try:
    from . import _http
except ImportError:
    import _http

KALSHI = "https://api.elections.kalshi.com/trade-api/v2/events"


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def kalshi(meetings=2, ttl=900):
    d = _http.get(KALSHI, {"series_ticker": "KXFEDDECISION", "status": "open", "with_nested_markets": "true"}, ttl=ttl)
    events = sorted(d.get("events", []), key=lambda e: e.get("strike_date") or "")[:meetings]
    rows = []
    for e in events:
        for m in e.get("markets", []):
            bid, ask, last = _f(m.get("yes_bid_dollars")), _f(m.get("yes_ask_dollars")), _f(m.get("last_price_dollars"))
            p = (bid + ask) / 2 if bid and ask else last
            rows.append({"source": "Kalshi", "meeting": (e.get("strike_date") or "")[:10],
                         "outcome": m.get("yes_sub_title"), "prob": None if p is None else round(p, 3)})
    return rows


def fed_odds(meetings=2):
    """Kalshi odds; if Kalshi fails, one row with the error instead of numbers."""
    try:
        return kalshi(meetings)
    except Exception as e:
        return [{"source": "Kalshi", "meeting": None, "outcome": f"unavailable: {e}", "prob": None}]
