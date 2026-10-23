"""3. FINRA short interest (published twice a month, settlement mid-month and month-end). Free public API, no
account needed for this dataset (checked 2026-10-15). Shares sold short, days to cover, change vs last report."""
import json
import urllib.request
from datetime import date, timedelta

try:
    from . import _http
except ImportError:
    import _http

URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"


def _post(body, ttl):
    import hashlib, time
    key = hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()
    path = _http.CACHE_DIR / f"finra_{key}.json"
    if path.exists() and time.time() - path.stat().st_mtime < ttl:
        return json.loads(path.read_text())
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "application/json",
                                          "User-Agent": _http.DEFAULT_UA})
    try:
        with urllib.request.urlopen(req, timeout=30, context=_http._ctx()) as r:
            text = r.read().decode()
    except Exception as e:
        raise RuntimeError(f"FINRA short interest request failed: {type(e).__name__} {getattr(e, 'code', '')}") from None
    _http.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "[]")
    return json.loads(text or "[]")


def short_interest(symbol, days=75, ttl=12 * 3600):
    """Latest reports for one symbol, newest first."""
    body = {"compareFilters": [{"compareType": "equal", "fieldName": "symbolCode", "fieldValue": symbol.upper()}],
            "dateRangeFilters": [{"fieldName": "settlementDate",
                                  "startDate": (date.today() - timedelta(days=days)).isoformat(),
                                  "endDate": date.today().isoformat()}],
            "limit": 20}
    return rows_from(_post(body, ttl))


def rows_from(raw):
    """FINRA rows, newest first. A row missing its date or share count is skipped, never a crash."""
    keep = [r for r in raw if isinstance(r, dict) and r.get("settlementDate")
            and isinstance(r.get("currentShortPositionQuantity"), (int, float))]
    return [{"source": "FINRA", "symbol": r.get("symbolCode"), "settled": r["settlementDate"],
             "short_shares": r["currentShortPositionQuantity"], "change_pct": r.get("changePercent"),
             "days_to_cover": r.get("daysToCoverQuantity")}
            for r in sorted(keep, key=lambda r: r["settlementDate"], reverse=True)]
