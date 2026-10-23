"""Portfolio risk: are all my bots betting on the same thing?

From ~6 months of daily closes (Alpaca SIP, your keys): how closely the bots' tickers move together (correlation),
which sector each one acts most like (the sector ETF it moves with most, measured, not a label), how much each moves
with the S&P 500 (beta), and whether the bots lean one way (long-only bots all win and lose together when the market
turns). Information only, not financial advice.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import data, loader
from .desk import SECTORS

LOOKBACK = 180       # calendar days
HIGH = 0.7           # "move together" threshold


def returns(closes: list[float]) -> list[float]:
    return [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1]]


def corr(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if n < 20:
        return None
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a); vb = sum((y - mb) ** 2 for y in b)
    if not va or not vb:
        return None
    return round(sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (va * vb) ** 0.5, 2)


def beta(a: list[float], m: list[float]) -> float | None:
    n = min(len(a), len(m))
    if n < 20:
        return None
    a, m = a[-n:], m[-n:]
    mm, ma = sum(m) / n, sum(a) / n
    vm = sum((x - mm) ** 2 for x in m)
    return round(sum((x - mm) * (y - ma) for x, y in zip(m, a)) / vm, 2) if vm else None


def analyze(rets: dict[str, list[float]], tickers: list[str], sides: dict[str, set]) -> dict:
    """rets: daily returns per symbol (tickers + SPY + sector ETFs), aligned to the same days."""
    tick = [t for t in tickers if t in rets]
    pairs = []
    for i, a in enumerate(tick):
        for b in tick[i + 1:]:
            c = corr(rets[a], rets[b])
            if c is not None:
                pairs.append({"a": a, "b": b, "corr": c})
    avg = round(sum(p["corr"] for p in pairs) / len(pairs), 2) if pairs else None
    rows, groups = [], {}
    for t in tick:
        best = max(((corr(rets[t], rets[s]) or -1, s) for s in SECTORS if s in rets), default=(None, None))
        sector = SECTORS.get(best[1]) if best[1] else None
        groups.setdefault(sector, []).append(t)
        rows.append({"symbol": t, "acts_most_like": sector, "sector_etf": best[1], "sector_corr": best[0],
                     "beta_to_spy": beta(rets[t], rets["SPY"]) if "SPY" in rets else None,
                     "bot_sides": sorted(sides.get(t, []))})
    biggest = max(groups.items(), key=lambda kv: len(kv[1])) if groups else (None, [])
    share = len(biggest[1]) / len(tick) if tick else 0
    all_sides = set().union(*sides.values()) if sides else set()
    lean = ("long only: every bot makes money only when prices rise" if all_sides == {"long"} else
            "short only: every bot makes money only when prices fall" if all_sides == {"short"} else
            "both directions")
    why = []
    if avg is not None and avg >= 0.6:
        why.append(f"the tickers move together a lot (average correlation {avg:+.2f})")
    if share >= 0.6 and len(tick) >= 3:
        why.append(f"{len(biggest[1])} of {len(tick)} tickers act most like {biggest[0]}")
    if all_sides in ({"long"}, {"short"}):
        why.append(lean)
    verdict = ("mostly ONE bet: " + "; ".join(why)) if len(why) >= 2 else \
        ("partly the same bet: " + why[0]) if why else "spread out: no single bet dominates"
    return {"verdict": verdict, "average_correlation": avg, "direction": lean,
            "move_together": sorted((p for p in pairs if p["corr"] >= HIGH), key=lambda p: -p["corr"])[:10],
            "tickers": rows, "by_sector": {k: v for k, v in groups.items()}}


def _daily_returns(symbols: list[str], fetch=None) -> dict[str, list[float]]:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=LOOKBACK)
    fetch = fetch or data.bars
    closes = {}
    for s in symbols:
        try:
            bs, _ = data.clean(fetch(s, start, end, "1Day", "sip"))
        except RuntimeError:
            raise
        except Exception:
            continue
        if len(bs) >= 2:                               # one ticker without bars must not empty the shared days
            closes[s] = {b.t.date(): b.c for b in bs}
    days = sorted(set.intersection(*(set(c) for c in closes.values()))) if closes else []
    return {s: returns([c[d] for d in days]) for s, c in closes.items()}


def portfolio_risk(only_on: bool = False, fetch=None) -> dict:
    """All bots (or only the ones switched on today) and their tickers."""
    bots, _ = loader.load_all()
    if only_on:
        from . import preflight
        on = preflight.settings_for()["bots"]
        bots = {k: v for k, v in bots.items() if on.get(k)}
    sides: dict[str, set] = {}
    for c in bots.values():
        for s in c.symbols:
            sides.setdefault(s.upper(), set()).update({"long", "short"} if c.sides == "both" else {c.sides})
    tickers = sorted(sides)
    if not tickers:
        return {"verdict": "no bots to check" + (" (none switched on today)" if only_on else ""), "tickers": []}
    rets = _daily_returns(tickers + ["SPY"] + list(SECTORS), fetch)
    missing = [t for t in tickers if t not in rets]
    out = {"bots": sorted(bots)} | analyze(rets, tickers, sides)
    if missing:                                        # say it, so a shorter list never reads as the whole picture
        out["no_data"] = f"no daily prices for {', '.join(missing)}, so they're left out of this check"
    return out | {
        "source": f"Alpaca SIP daily closes, last {LOOKBACK} days, your own keys",
        "note": "acts_most_like = the sector ETF the stock moved with most (measured). Correlation: 1 = always "
                "together, 0 = unrelated. Past behavior; it changes in crashes (things fall together). Not "
                "financial advice."}
