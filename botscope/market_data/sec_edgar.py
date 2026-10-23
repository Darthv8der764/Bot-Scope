"""5. SEC EDGAR: full-text search (efts.sec.gov) and new 8-Ks for tickers. User-Agent and the <10 requests/sec
limit are handled in _http (SEC_USER_AGENT, SEC_MIN_GAP)."""
from datetime import date, timedelta

try:
    from . import _http
except ImportError:
    import _http


def _cik_map(ttl=7 * 86400):
    d = _http.get("https://www.sec.gov/files/company_tickers.json", ttl=ttl)
    return {v["ticker"].upper(): int(v["cik_str"]) for v in d.values()}


def full_text_search(query, forms="8-K", days=30, limit=10, ttl=3600):
    """Search the words inside filings, e.g. '"going concern"' or '"guidance"'."""
    end = date.today()
    d = _http.get("https://efts.sec.gov/LATEST/search-index",
                  {"q": query, "forms": forms, "dateRange": "custom",
                   "startdt": (end - timedelta(days=days)).isoformat(), "enddt": end.isoformat()}, ttl=ttl)
    out = []
    for h in d.get("hits", {}).get("hits", []):
        s = h.get("_source", {})
        out.append({"source": "SEC EDGAR", "filed": s.get("file_date"), "form": s.get("form"),
                    "company": (s.get("display_names") or [""])[0], "items": ",".join(s.get("items") or [])})
    return sorted(out, key=lambda x: x["filed"] or "", reverse=True)[:limit]


def recent_8ks(tickers, days=7, ttl=1800):
    """8-Ks filed in the last `days` days for each ticker (one SEC call per ticker, rate limited)."""
    ciks, since, out = _cik_map(), (date.today() - timedelta(days=days)).isoformat(), []
    for t in tickers:
        cik = ciks.get(t.upper().replace(".", "-"))
        if not cik:
            continue
        r = _http.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", ttl=ttl)["filings"]["recent"]
        for i, form in enumerate(r["form"]):
            if form == "8-K" and r["filingDate"][i] >= since:
                acc = r["accessionNumber"][i]
                out.append({"source": "SEC EDGAR", "ticker": t.upper(), "filed": r["filingDate"][i], "items": r["items"][i],
                            "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{r['primaryDocument'][i]}"})
    return sorted(out, key=lambda x: x["filed"], reverse=True)
