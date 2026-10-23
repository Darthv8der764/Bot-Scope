"""Offline checks of the bot format and the backtester on made-up bars (no keys, no network)."""
from datetime import date, datetime, timedelta

from botscope import backtest, loader
from botscope.bot import BarData, Entry, NoTrade
from botscope.data import ET


def fake_day(break_up=True):
    t0 = datetime(2026, 9, 1, 9, 30, tzinfo=ET)
    bars = []
    for i in range(390):
        if i < 60:
            px = 100 + (0.5 if i % 2 else -0.5)        # first-hour (opening) range 99.4-100.6
        elif i < 75:
            px = 100.2
        else:
            px = 100.2 + (0.05 * (i - 74) if break_up else -0.05 * (i - 74))
        bars.append(BarData(t0 + timedelta(minutes=i), px, px + 0.1, px - 0.1, px, 1000))
    return bars


def test_loader_finds_example_bot():
    bots, errors = loader.load_all()
    assert "first_hour_breakout" in bots and not errors


def test_entry_long_on_first_break_then_target():
    cls = loader.get("first hour breakout")
    bot = cls()
    trades, problems = backtest.run_day(bot, "TEST", date(2026, 9, 1), fake_day(), backtest.COSTS[bot.asset])
    assert not problems and len(trades) == 1
    t = trades[0]
    assert t.side == "long" and t.why_out == "target hit" and 1.8 < t.r < 2.0   # 2R minus costs


def test_short_side_and_no_peek():
    bot = loader.get("first_hour_breakout")()
    bars = fake_day(break_up=False)
    trades, _ = backtest.run_day(bot, "TEST", date(2026, 9, 1), bars, backtest.COSTS[bot.asset])
    assert trades[0].side == "short"
    assert backtest.no_peek_check(bot, bars) is None


def test_no_trade_has_reason():
    bot = loader.get("first_hour_breakout")()
    from botscope.bot import View
    bars = fake_day()[:10]
    d = bot.entry(View("TEST", bars, {k: v for k, v in bot.indicators(bars).items()}))
    assert isinstance(d, NoTrade) and "opening range" in d.reason
    assert not isinstance(d, Entry)
