"""4. Analyst recommendation trends from Finnhub (free key FINNHUB_API_KEY): count of strong buy / buy / hold /
sell / strong sell per month."""
try:
    from . import _http
except ImportError:
    import _http


def recommendations(symbol, months=3, ttl=12 * 3600):
    key = _http.need_key("FINNHUB_API_KEY")
    d = _http.get("https://finnhub.io/api/v1/stock/recommendation", {"symbol": symbol.upper(), "token": key},
                  ttl=ttl, secret_params=("token",))
    if not isinstance(d, list):                    # Finnhub answers errors as {"error": "..."}
        raise RuntimeError(f"Finnhub analyst counts unavailable: {str((d or {}).get('error', d))[:100]}")
    rows = sorted((r for r in d if isinstance(r, dict) and r.get("period")), key=lambda r: r["period"], reverse=True)
    return [{"source": "Finnhub", "symbol": r.get("symbol", symbol.upper()), "month": r["period"][:7],
             **{k: r.get(f, 0) or 0 for k, f in (("strong_buy", "strongBuy"), ("buy", "buy"), ("hold", "hold"),
                                                  ("sell", "sell"), ("strong_sell", "strongSell"))}}
            for r in rows[:months]]
