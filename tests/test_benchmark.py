from datetime import date, datetime

from botscope import benchmark, report
from botscope.data import ET, BarData


def spy(*closes, start=1):
    return lambda sym, a, b, tf, feed: [BarData(datetime(2025, 3, start + i, 16, tzinfo=ET), c, c, c, c, 1)
                                         for i, c in enumerate(closes)]


def test_hold_buys_first_open_sells_last_close_minus_costs():
    h = benchmark.spy_hold(date(2025, 3, 1), date(2025, 3, 31), fetch=spy(100, 105, 110))
    assert h["pct"] == round(10 - benchmark.HOLD_COST_BPS / 100, 2) and h["usd"] == 998.0 and h["days"] == 3


def test_verdict_beat_tie_trailed():
    f = spy(100, 101)                                    # SPY +1% = about +$98
    assert benchmark.compare(500, date(2025, 3, 1), date(2025, 3, 31), fetch=f)["result"] == "beat"
    assert benchmark.compare(100, date(2025, 3, 1), date(2025, 3, 31), fetch=f)["result"] == "tie"
    c = benchmark.compare(-300, date(2025, 3, 1), date(2025, 3, 31), fetch=f)
    assert c["result"] == "trailed" and c["beat"] is False and "trailed just holding SPY by $" in c["beat_holding"]


def test_no_spy_data_says_so_never_guesses():
    c = benchmark.compare(50, date(2025, 3, 1), date(2025, 3, 31))      # offline in tests
    assert c["result"] is None and c["beat"] is None and c["beat_holding"].startswith("can't compare")


def test_report_counts_untested_years_beaten():
    rows = [{"period": "untested", "net_usd": 200, "spy_hold_usd": 100, "beat": True},
            {"period": "untested", "net_usd": -50, "spy_hold_usd": 300, "beat": False},
            {"period": "tuned", "net_usd": 900, "spy_hold_usd": 0, "beat": True}]
    v = report.vs_spy(rows)
    assert v["years_beat"] == 1 and v["untested_years"] == 2 and "1 of 2 untested years" in v["summary"]
    assert "can't compare" in report.vs_spy([])["summary"]


def test_crypto_bots_also_compared_with_holding_btc():
    seen = []

    def btc(sym, a, b, tf, feed):
        seen.append(sym)
        return [BarData(datetime(2025, 3, 1 + i, 16, tzinfo=ET), c, c, c, c, 1) for i, c in enumerate((100, 110))]
    rows = [{"period": "untested", "from": "2025-03-01", "to": "2025-03-31", "net_usd": 2000},
            {"period": "tuned", "from": "2024-03-01", "to": "2024-03-31", "net_usd": 9000}]
    v = report.vs_btc(rows, costs={"entry_bps": 50, "exit_bps": 50}, fetch=btc)
    assert seen == ["BTC/USD"]                           # tuned years are never compared
    assert v["btc_usd"] == 900.0 and v["years_beat"] == 1 and "1 of 1 untested years" in v["summary"]
    assert "can't compare with BTC" in report.vs_btc(rows)["summary"]   # offline: says so, never guesses


def test_report_names_the_crypto_data_source():
    assert report.data_line(["BTC/USD"]).startswith("Alpaca crypto history")
    assert report.data_line(["SPY"]).startswith("Alpaca SIP")
    assert "crypto: Alpaca crypto" in report.data_line(["SPY", "ETH/USD"])


def test_crypto_years_start_when_the_crypto_data_does(monkeypatch):
    from botscope import demo, loader
    monkeypatch.setattr(demo, "active", lambda: False)
    monkeypatch.delenv("BOTSCOPE_CRYPTO_DATA", raising=False)
    crypto, stock = loader.get("crypto_trend"), loader.get("pullback_swing")
    assert report.year_windows(crypto, date(2026, 10, 17))[0]["year"] == 2021
    assert report.year_windows(stock, date(2026, 10, 17))[0]["year"] == 2016
    rows = report.crash_test(crypto, fetch=lambda *a: [])["crashes"]
    assert rows[0]["result"] == report.CRYPTO_NO_DATA and "stock data" not in rows[0]["result"]


def test_tight_stops_flagged_because_they_inflate_r():
    from botscope import backtest
    mk = lambda r, risk, cost=0.1: backtest.Trade(symbol="SPY", day="2025-03-03", side="long", entry=100, exit=100,  # noqa: E731
                                                 stop=100 - risk, why_in="", why_out="", r=r, pct=r * risk,
                                                 cost_pct=cost, risk_pct=risk, t_in=f"2025-03-0{3 + int(risk)}")
    trades = [mk(1.0, 2.0) for _ in range(9)] + [mk(80.0, 0.05), mk(-40.0, 0.05), mk(60.0, 0.05)]
    s = backtest.summarize(trades, 10_000)
    assert s["tight_stop_trades"] == 3 and s["without_tight_stops_r"] == 9.0
    r = {"untested": s, "years": {"untested": [2025]}, "losing_untested_years": []}
    assert "inflates R (without them +9.0R; see docs/when-r-lies-tight-stops.md)" in report.headline(r)
    assert "tight_stop_trades" not in backtest.summarize(trades[:9], 10_000)


def test_quick_run_warns_about_tight_stops_too():
    from botscope import backtest
    assert report.tight_stops is backtest.tight_stops
    assert backtest.tight_stops({"trades": 40, "tight_stop_trades": 2, "without_tight_stops_r": 1.0}) is None
    assert "inflates R" in backtest.tight_stops({"trades": 40, "tight_stop_trades": 3, "without_tight_stops_r": 1.0})


def test_one_huge_tight_stop_trade_is_enough_to_warn():
    from botscope import backtest
    u = {"trades": 205, "tight_stop_trades": 1, "total_r": -389.0, "without_tight_stops_r": 75.0}
    assert "inflates R" in backtest.tight_stops(u)
    assert backtest.tight_stops(u | {"total_r": 80.0}) is None          # moved 5R only, 1 of 205: quiet
