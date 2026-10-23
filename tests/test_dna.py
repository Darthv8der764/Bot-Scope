"""Strategy DNA: style from the rules, holding time / time of day / lean from trades, near-twins flagged."""
from botscope import dna
from botscope.backtest import Trade
from botscope.bot import Bot


class Dip(Bot):
    name = "Dip"; description = "Buys a sharp dip"; rules = ["2-day RSI under 10", "sell on the bounce"]
    symbols = ["SPY", "QQQ"]; timeframe = "1Day"


class Trend(Bot):
    name = "Trend"; description = "Rides the trend"; rules = ["breakout above the 20-day high"]
    symbols = ["AAPL"]; timeframe = "5Min"


def _t(sym, day, side, hin, hout):
    return Trade(sym, day, side, 1, 1, 1, "", "", 0.1, 0.1, 0, t_in=f"{day}T{hin}:00-04:00", t_out=f"{day}T{hout}:00-04:00")


def test_style_hold_time_and_lean():
    assert dna.style(Dip) == "dip buying" and dna.style(Trend) == "trend following"
    f = dna.fingerprint(Trend, [_t("AAPL", "2026-10-01", "long", "09:45", "10:15"), _t("AAPL", "2026-10-02", "short", "10:00", "10:30")])
    assert f["holding_time"] == "30 min" and f["lean"] == "1 of 2 long" and f["time_of_day"].startswith("morning")
    assert dna.fingerprint(Dip, [])["lean"] == "no trades"


def test_near_twins_flagged_and_different_bots_not():
    tr = [_t("SPY", f"2026-10-0{d}", "long", "09:45", "11:00") for d in range(1, 6)]
    a, b = dna.fingerprint(Dip, tr), dna.fingerprint(Dip, tr[:4])
    s, why = dna.similarity(a, b)
    assert s >= dna.TWIN_AT and any("same symbol and day" in w for w in why)
    s2, _ = dna.similarity(a, dna.fingerprint(Trend, [_t("AAPL", "2026-10-01", "short", "15:00", "15:10")]))
    assert s2 < dna.TWIN_AT
