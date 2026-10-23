"""8. Ex-dividend dates and stock splits from Alpaca corporate actions (your keys), for the given tickers."""
from datetime import date, timedelta


def _client():
    from alpaca.data.historical.corporate_actions import CorporateActionsClient
    from botscope.env import alpaca_keys
    return CorporateActionsClient(*alpaca_keys())


def rows_from(data: dict, start: date, end: date) -> list[dict]:
    """Shape Alpaca's {kind: [actions]} into calendar rows dated by the ex-date, kept inside [start, end]."""
    out = []
    for kind, acts in data.items():
        for a in acts:
            a = a if isinstance(a, dict) else a.model_dump()
            ex = a.get("ex_date")
            if ex is None or not (start <= ex <= end):
                continue
            if kind == "cash_dividends":
                ev = f"{a['symbol']} ex-dividend (${a['rate']:.2f}/share{', special' if a.get('special') else ''})"
            elif kind in ("forward_splits", "reverse_splits"):
                ev = f"{a['symbol']} {'reverse ' if kind == 'reverse_splits' else ''}split {a.get('new_rate'):g}-for-{a.get('old_rate'):g}"
            else:
                continue
            out.append({"date": str(ex), "event": ev, "source": "Alpaca corporate actions"})
    return sorted(out, key=lambda r: (r["date"], r["event"]))


def upcoming(symbols, start: date, end: date, client=None) -> list[dict]:
    from alpaca.data.requests import CorporateActionsRequest
    if not symbols:
        return []
    c = client or _client()
    r = c.get_corporate_actions(CorporateActionsRequest(symbols=sorted(set(symbols)),
                                                        start=start - timedelta(days=60), end=end + timedelta(days=30)))
    return rows_from(r.data, start, end)
