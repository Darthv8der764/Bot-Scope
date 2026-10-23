import pytest

from botscope import view


@pytest.fixture(autouse=True)
def _demo(monkeypatch):
    monkeypatch.setenv("BOTSCOPE_DEMO", "1")


@pytest.mark.parametrize("span,candle", [("2d", "5Min"), ("5d", "15Min"), ("10d", "30Min"), ("1m", "1Hour"),
                                         ("3m", "1Day"), ("6m", "1Day")])
def test_ranges_grow_candles_and_trades_sit_on_candles(span, candle):
    o = view.build_span("first_hour_breakout", None, "2026-10-16", span)
    times = {c["time"] for c in o["candles"]}
    assert o["candle"] == candle and 40 <= len(o["candles"]) <= 200     # never a jumble of thousands of bars
    assert o["trades"] and all(t["t_in"] in times and t["t_out"] in times for t in o["trades"])
    assert candle in o["source"] and "DEMO" in o["source"].upper()


def test_snap_and_bad_span():
    assert view.snap([10, 20, 30], 25) == 20 and view.snap([10, 20], 5) == 10
    with pytest.raises(ValueError, match="range must be"):
        view.build_span("first_hour_breakout", None, "2026-10-16", "7y")


def test_page_has_range_picker():
    html = view.PAGE.read_text()
    assert all(f'value="{k}"' in html for k in view.SPANS) and 'id="f-span"' in html
