"""6. Economic actuals from FRED (key FRED_API_KEY). Actual released numbers only; no consensus forecasts
(those are only available from scrapers, which we don't use)."""
try:
    from . import _http
except ImportError:
    import _http

SERIES = {  # name -> (FRED id, how to show it)
    "CPI inflation (YoY %)": ("CPIAUCSL", "yoy"),
    "Jobs added (thousands)": ("PAYEMS", "diff"),
    "Unemployment rate (%)": ("UNRATE", "level"),
    "Real GDP growth (annualized %)": ("A191RL1Q225SBEA", "level"),
    "Fed funds target, upper (%)": ("DFEDTARU", "level"),
    "Fed funds effective (%)": ("FEDFUNDS", "level"),
}


def series(fred_id, n=14, ttl=6 * 3600):
    key = _http.need_key("FRED_API_KEY")
    d = _http.get("https://api.stlouisfed.org/fred/series/observations",
                  {"series_id": fred_id, "sort_order": "desc", "limit": n, "file_type": "json", "api_key": key},
                  ttl=ttl, secret_params=("api_key",))
    return [(o["date"], float(o["value"])) for o in d["observations"] if o["value"] != "."]


def latest(get=series):
    """One row per indicator. One series that fails or comes back short leaves its own row empty (the reason in
    as_of) instead of blanking the whole panel. A missing key still stops everything with its own message."""
    if get is series:
        _http.need_key("FRED_API_KEY")                 # no key: one clear message, not six empty rows
    out = []
    for name, (sid, how) in SERIES.items():
        row = {"source": "FRED", "indicator": name, "fred_id": sid}
        try:
            obs = get(sid)
            need = {"yoy": 13, "diff": 2}.get(how, 1)
            if len(obs) < need:
                raise ValueError(f"only {len(obs)} released numbers, need {need}")
            if how == "yoy":
                val = round((obs[0][1] / obs[12][1] - 1) * 100, 2)
            elif how == "diff":
                val = round(obs[0][1] - obs[1][1], 1)
            else:
                val = obs[0][1]
            out.append(row | {"as_of": obs[0][0], "value": val})
        except Exception as e:                        # HTTP errors, short or odd data: this row only
            out.append(row | {"as_of": f"unavailable ({str(e)[:60] or type(e).__name__})", "value": None})
    return out
