"""Offline checks of portfolio risk (made-up returns)."""
import random

from botscope import risk


def series(seed, base, noise=0.3, n=120):
    rng = random.Random(seed)
    return [b + rng.gauss(0, noise) * 0.01 for b in base[:n]]


def test_correlation_and_beta_basics():
    rng = random.Random(1)
    m = [rng.gauss(0, 0.01) for _ in range(120)]
    assert risk.corr(m, m) == 1.0 and risk.corr(m, [-x for x in m]) == -1.0
    assert risk.beta([2 * x for x in m], m) == 2.0
    assert risk.corr(m[:10], m[:10]) is None                     # too few days


def test_one_bet_when_everything_is_tech_and_long():
    rng = random.Random(2)
    tech = [rng.gauss(0, 0.012) for _ in range(120)]
    energy = [rng.gauss(0, 0.012) for _ in range(120)]
    rets = {"XLK": tech, "XLE": energy, "SPY": [x * 0.8 for x in tech],
            **{t: series(i, tech) for i, t in enumerate(["AAPL", "MSFT", "NVDA"])}}
    out = risk.analyze(rets, ["AAPL", "MSFT", "NVDA"], {t: {"long"} for t in ("AAPL", "MSFT", "NVDA")})
    assert out["verdict"].startswith("mostly ONE bet") and out["by_sector"] == {"Tech": ["AAPL", "MSFT", "NVDA"]}
    assert out["move_together"] and out["tickers"][0]["beta_to_spy"] > 1


def test_spread_out_portfolio():
    rng = random.Random(3)
    a, b, c = ([rng.gauss(0, 0.01) for _ in range(120)] for _ in range(3))
    rets = {"XLK": a, "XLE": b, "XLU": c, "SPY": a, "AAA": series(1, a), "BBB": series(2, b), "CCC": series(3, c)}
    out = risk.analyze(rets, ["AAA", "BBB", "CCC"], {"AAA": {"long", "short"}, "BBB": {"long"}, "CCC": {"short"}})
    assert out["verdict"].startswith("spread out") and out["direction"] == "both directions"


def test_portfolio_risk_runs_on_fake_bars():
    from datetime import date, datetime, timedelta
    from botscope.bot import BarData
    from botscope.data import ET

    def fake(sym, start, end, tf, feed):
        rng = random.Random(sum(map(ord, sym)))
        px, out, d = 100.0, [], start
        while d <= end:
            if d.weekday() < 5:
                px *= 1 + rng.gauss(0, 0.01)
                out.append(BarData(datetime(d.year, d.month, d.day, tzinfo=ET), px, px, px, px, 1))
            d += timedelta(days=1)
        return out
    out = risk.portfolio_risk(fetch=fake)
    assert out["tickers"] and out["verdict"] and "NVDA" in [t["symbol"] for t in out["tickers"]]
    assert "no_data" not in out

    def one_empty(sym, *a):                            # a delisted ticker: no bars at all
        return [] if sym == "NVDA" else fake(sym, *a)
    out = risk.portfolio_risk(fetch=one_empty)
    assert "NVDA" in out["no_data"] and out["tickers"]   # the others still get their correlations
    assert "NVDA" not in [t["symbol"] for t in out["tickers"]] and out["average_correlation"] is not None
