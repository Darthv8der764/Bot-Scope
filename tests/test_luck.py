"""Offline checks of the luck meter (made-up bars, no network)."""
import random
from datetime import date, datetime, timedelta

from botscope import loader, luck
from botscope.bot import BarData
from botscope.data import ET
from test_report import shifted


def walk_day(d: date, seed: int):
    """A random-walk day: no real pattern for any bot to find."""
    rng = random.Random(seed)
    t0, px, out = datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET), 100.0, []
    for i in range(390):
        o = px; px *= 1 + rng.gauss(0, 0.0012)
        out.append(BarData(t0 + timedelta(minutes=i), o, max(o, px) + 0.03, min(o, px) - 0.03, px, 1000))
    return out


def fetch_from(make):
    def f(sym, start, end, tf, feed):
        out, d, n = [], start, 0
        while d <= end and n < 12:
            if d.weekday() < 5:
                out += make(d, n + sum(map(ord, sym))); n += 1
            d += timedelta(days=1)
        return out
    return f


def test_shuffle_keeps_moves_but_changes_order():
    bs = walk_day(date(2026, 9, 1), 1)
    sh = luck.shuffle_bars(bs, random.Random(3))
    assert len(sh) == len(bs) and sh[0] == bs[0] and [b.t for b in sh] == [b.t for b in bs]
    rets = sorted(round(bs[i].c / bs[i - 1].c, 9) for i in range(1, len(bs)))
    assert rets == sorted(round(sh[i].c / sh[i - 1].c, 9) for i in range(1, len(sh)))
    assert [b.c for b in sh] != [b.c for b in bs]


def test_verdict_levels_are_counts_not_percentages():
    assert luck.verdict(99, 100, 12.0, -3.0)["level"] == "beats luck"
    assert luck.verdict(85, 100, 12.0, -3.0)["level"] == "unclear"
    assert luck.verdict(40, 100, 12.0, None)["level"] == "looks like luck"
    assert luck.verdict(99, 100, -2.0, None)["level"] == "looks like luck"
    v = luck.verdict(99, 100, 12.0, 15.0)
    assert v["level"] == "unclear" and any("shuffled" in w for w in v["why"])
    assert all("%" not in w for w in v["why"])


def test_luck_meter_runs_on_made_up_days():
    cls = loader.get("first_hour_breakout")
    r = luck.luck_meter(cls, ["AAA", "BBB"], fetch=fetch_from(walk_day), twins=20, shuffles=2)
    assert r["untested_trades"] >= 10
    assert r["random_twins"]["count"] == 20 and 0 <= r["random_twins"]["beat"] <= 20
    assert r["level"] in ("looks like luck", "unclear", "beats luck")


def test_luck_meter_says_when_there_are_too_few_trades():
    r = luck.luck_meter(loader.get("first_hour_breakout"), ["AAA"], fetch=fetch_from(lambda d, n: shifted(d)[:5]))
    assert r["level"] == "not enough trades"


def test_luck_meter_names_a_symbol_without_prices():
    good = fetch_from(walk_day)

    def f(sym, *a):
        if sym == "GONE":
            raise ConnectionError("no data")
        return good(sym, *a)
    r = luck.luck_meter(loader.get("first_hour_breakout"), ["AAA", "GONE"], fetch=f, twins=5, shuffles=1, save=False)
    assert "GONE" in r["no_data"] and "AAA" not in r["no_data"]
    assert "no_data" not in luck.luck_meter(loader.get("first_hour_breakout"), ["AAA"], fetch=good, twins=5,
                                            shuffles=1, save=False)
