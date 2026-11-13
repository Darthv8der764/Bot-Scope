from datetime import date, datetime

from botscope import demo_trades


def test_same_trades_every_time_and_labelled_made_up(tmp_path):
    assert demo_trades.fills() == demo_trades.fills()
    assert "MADE-UP" in demo_trades.LABEL
    p = demo_trades.write_csv(tmp_path / "demo.csv")
    first, header = p.read_text().splitlines()[:2]
    assert first.startswith("# MADE-UP") and header == "symbol,side,qty,price,time,tz"


def test_fills_are_whole_round_trips_inside_market_hours():
    f = demo_trades.fills()
    assert len(f) == 2 * len(demo_trades.planted()) >= 120
    for o, c in zip(f[::2], f[1::2]):
        assert o["symbol"] == c["symbol"] and o["qty"] == c["qty"] and o["side"] != c["side"]
        assert "09:30:00" <= o["time"][11:] < c["time"][11:] <= "16:00:00"


def test_the_three_planted_patterns_are_there():
    p = demo_trades.planted()
    after = [x for x in p if x["kind"] == "after_loss"]
    fri = [x for x in p if x["kind"] == "friday_pm"]
    assert len(after) >= 10 and sum(x["win"] for x in after) * 3 < len(after)        # mostly lose
    assert len(fri) >= 5 and sum(x["win"] for x in fri) * 2 < len(fri)
    assert all(datetime.fromisoformat(x["opened"]).weekday() == 4 for x in fri)
    held = lambda x: (datetime.fromisoformat(x["closed"]) - datetime.fromisoformat(x["opened"])).seconds / 60  # noqa: E731
    losers = [held(x) for x in p if not x["win"] and not x["closed"].endswith("15:55:00")]   # not cut at the close
    assert min(losers) > max(held(x) for x in p if x["win"])                                  # losers held longer
    tilt = [x for x in p if x["kind"] == "tilt"]
    assert len(tilt) >= 8 and sum(x["win"] for x in tilt) * 4 < len(tilt)            # after 2 losses: mostly lose
    ns = demo_trades.notes()
    assert len(ns) == len(p) and all(n["checklist"]["setup"] == n["setup"] for n in ns)


def test_no_demo_trade_on_a_weekend_or_market_holiday():
    days = {datetime.fromisoformat(x["opened"]).date() for x in demo_trades.planted()}
    assert date(2026, 9, 7) in demo_trades.HOLIDAYS
    assert all(d.weekday() < 5 and d not in demo_trades.HOLIDAYS for d in days)
