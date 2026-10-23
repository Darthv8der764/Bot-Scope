"""Offline checks of 'days like today' (made-up SPY closes and random-walk days, no network)."""
from datetime import date

from botscope import alike, loader
from test_luck import walk_day
from test_weather import series


def test_nearest_picks_the_matching_days_spread_apart():
    feats = {f"2025-01-{i:02d}": {f: (5.0 if i in (3, 20) else 0.0) for f in alike.FEATURES} | {"weather": "choppy"}
             for i in range(1, 29)}
    today = {f: 5.0 for f in alike.FEATURES}
    picks = alike.nearest(feats, today, k=2)
    assert [p["day"] for p in picks] == ["2025-01-03", "2025-01-20"] and picks[0]["distance"] == 0
    near = alike.nearest(feats, today, k=3)
    days = sorted(int(p["day"][-2:]) for p in near)
    assert all(b - a >= alike.MIN_GAP for a, b in zip(days, days[1:]))       # never a cluster of neighbours


def test_features_never_use_the_same_day():
    closes = [100 * 1.004 ** i for i in range(80)] + [50]
    f = alike.day_features(series(closes))
    assert f[max(f)]["weather"] == "trending up"                             # the crash isn't known at its open


def test_days_like_today_replays_the_bot_on_matched_days():
    spy = series([100 + (i % 7) - 3 + i * 0.05 for i in range(300)])
    last = spy[-1].t.date()

    def fetch(sym, a, b, tf, feed):
        if sym == "SPY":
            return [x for x in spy if a <= x.t.date() <= b]
        return walk_day(b, b.toordinal())
    out = alike.days_like_today(loader.get("first_hour_breakout"), "AAPL", k=5, today=date.fromordinal(last.toordinal() + 1),
                                fetch=fetch)
    assert len(out["days"]) == 5
    assert all(r["period"] in ("tuned", "untested") and r["open"].startswith("/?bot=") for r in out["days"])
    assert all(r["day"] < str(spy[-alike.SKIP_RECENT].t.date()) for r in out["days"])
    assert "%" not in out["summary"] and "Not financial advice" in out["note"]
