"""Offline checks of the pullback swing example bot's RSI and its entry rules."""
from datetime import datetime, timedelta

from botscope import loader
from botscope.bot import BarData, Entry, NoTrade, View

BOT = loader.get("pullback_swing")
_rsi = BOT.entry.__globals__["_rsi"]          # bot files load outside sys.modules


def test_rsi_edges():
    assert _rsi([1, 2], 2) is None
    assert _rsi([1, 2, 3, 4], 2) == 100.0
    assert _rsi([4, 3, 2, 1], 2) == 0.0


def _entry(closes):
    t = datetime(2024, 1, 1)
    bars = [BarData(t + timedelta(days=i), c, c + 1, c - 1, c, 1000) for i, c in enumerate(closes)]
    bot = BOT()
    return bot.entry(View("SPY", bars, bot.indicators(bars)))


def test_buys_a_sharp_dip_in_an_uptrend_only():
    up = [100 + i * 0.5 for i in range(220)]
    e = _entry(up + [up[-1] - 3, up[-1] - 6])
    assert isinstance(e, Entry) and e.side == "long" and e.stop < up[-1] - 6 and e.target is None
    assert isinstance(_entry(up), NoTrade)                                       # no dip
    down = [300 - i * 0.5 for i in range(220)]
    assert "not an uptrend" in _entry(down + [down[-1] - 3]).reason
