"""Crypto (24/7) bots and defined-risk option spread plans."""
from datetime import date

import pytest

from botscope import data, demo, loader, report, spreads


def test_crypto_sessions_are_whole_utc_days_and_demo_has_weekends():
    bs = demo.bars("BTC/USD", date(2024, 3, 9), date(2024, 3, 10), "15Min")      # a weekend
    s = data.sessions(bs, "15Min", crypto=True)
    assert [len(v) for v in s.values()] == [96, 96]
    assert len(demo.bars("BTC/USD", date(2024, 3, 4), date(2024, 3, 10), "1Day")) == 7
    assert data.is_crypto("ETH/USD") and not data.is_crypto("SPY")


def test_example_crypto_bot_runs_an_honest_report():
    rep = report.full_report(loader.get("crypto_trend"), fetch=demo.bars, crashes=False, save=False)
    assert rep["untested"]["trades"] > 0 and rep["costs_bps"]["entry_bps"] > 10      # crypto costs, not stock costs


CHAIN = {"AAPL261106C00250000": {"latest_quote": {"bid_price": 6.1, "ask_price": 6.3}},
         "AAPL261106C00255000": {"latest_quote": {"bid_price": 3.4, "ask_price": 3.6}},
         "AAPL261106P00250000": {"latest_quote": {"bid_price": 5.0, "ask_price": 5.2}},
         "AAPL261106P00245000": {"latest_quote": {"bid_price": 3.0, "ask_price": 3.2}},
         "AAPL261020C00250000": {"latest_quote": {"bid_price": 2.0, "ask_price": 2.2}}}


def test_bull_call_and_bear_put_spreads_have_defined_risk():
    p = spreads.plan("long", 251.0, CHAIN, today=date(2026, 10, 17))
    assert p["spread"] == "bull call spread" and p["expiry"] == "2026-11-06"          # 3-day expiry skipped
    assert p["debit_per_share"] == 2.9 and p["max_loss_usd"] == 290.0 and p["max_gain_usd"] == 210.0
    assert p["breakeven"] == 252.9
    q = spreads.plan("short", 249.0, CHAIN, today=date(2026, 10, 17))
    assert q["spread"] == "bear put spread" and q["max_loss_usd"] == 220.0 and q["breakeven"] == 247.8


def test_no_plan_for_crypto_or_bad_quotes():
    with pytest.raises(ValueError, match="not crypto"):
        spreads.spread_plan("crypto_trend", side="long", chain=CHAIN, spot=1)
    bad = {k: {"latest_quote": {"bid_price": 0, "ask_price": 0}} for k in CHAIN}
    with pytest.raises(ValueError):
        spreads.plan("long", 251.0, bad, today=date(2026, 10, 17))
