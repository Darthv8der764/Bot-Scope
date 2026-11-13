"""Offline checks of the newer example bots: they load, follow their rules, and trade on made-up fixture bars."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from botscope import backtest, loader, scaffold
from botscope.bot import BarData, Entry, NoTrade, View

ET = ZoneInfo("America/New_York")


def _bars(closes, start=datetime(2024, 1, 2, 9, 30, tzinfo=ET), every_day=False):
    out, t = [], start
    for c in closes:
        while t.weekday() >= 5 and not every_day:
            t += timedelta(days=1)
        out.append(BarData(t, c, c + 1, c - 1, c, 1000))
        t += timedelta(days=1)
    return out


def _wavy_uptrend(n=400):
    """A steady climb with a 4-day dip every 15 days: dip buyers should trade on it."""
    closes, c = [], 100.0
    for i in range(n):
        c += -1.5 if i % 15 in (10, 11, 12, 13) else 0.8
        closes.append(c)
    return closes


def _crypto_waves(n=400):
    """Crypto candles every day, starting at midnight UTC (shown in New York time, as BotScope does): 60 days up,
    40 down, again and again."""
    closes, c = [], 100.0
    for i in range(n):
        c *= 1.01 if i % 100 < 60 else 0.99
        closes.append(c)
    return _bars(closes, datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC")).astimezone(ET), every_day=True)


@pytest.mark.parametrize("bot_id, fixture", [("double_7s", lambda: _bars(_wavy_uptrend())),
                                             ("crypto_weekly_momentum", _crypto_waves)])
def test_loads_passes_check_bot_and_trades_on_fixture_bars(bot_id, fixture):
    cls = loader.get(bot_id)
    assert cls.tuned_on == ("2016-01-01", "2020-12-31") and cls.status == "untested"
    bad = [c for c in scaffold.check_class(cls)["checks"] if not c["pass"]]
    assert not bad, bad
    bs = fixture()
    trades, problems = backtest.run_day(cls(), "SPY", bs[-1].t.date(), bs, backtest.COSTS[cls.asset],
                                        close_at_end=True)
    assert len(trades) >= 3 and not problems


def _d7(closes):
    bot = loader.get("double_7s")()
    bs = _bars(closes)
    return bot.entry(View("SPY", bs, bot.indicators(bs)))


def test_double_7s_buys_a_7_day_low_in_an_uptrend_only():
    up = [100 + i * 0.5 for i in range(220)]
    e = _d7(up + [up[-1] - 5])
    assert isinstance(e, Entry) and e.side == "long" and e.stop < up[-1] - 5 and e.target is None
    assert isinstance(_d7(up), NoTrade)                                           # no 7-day low
    down = [300 - i * 0.5 for i in range(220)]
    no = _d7(down + [down[-1] - 5])
    assert isinstance(no, NoTrade) and "not an uptrend" in no.reason and isinstance(no.almost, Entry)


def test_crypto_weekly_momentum_decides_on_the_sunday_utc_candle_only():
    cls = loader.get("crypto_weekly_momentum")
    bs = _crypto_waves(60)                                   # rising for 60 days
    bot = cls()
    sundays = [i for i, b in enumerate(bs) if i >= 30 and b.t.astimezone(ZoneInfo("UTC")).weekday() == 6]
    assert sundays and all(bs[i].t.weekday() == 5 for i in sundays)    # Saturday evening in New York
    e = bot.entry(View("BTC/USD", bs[:sundays[0] + 1], {}))
    assert isinstance(e, Entry) and e.side == "long" and e.stop < bs[sundays[0]].c
    no = bot.entry(View("BTC/USD", bs[:sundays[0] + 2], {}))
    assert isinstance(no, NoTrade) and "Sundays" in no.reason
