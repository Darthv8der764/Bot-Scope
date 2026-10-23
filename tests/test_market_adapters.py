"""The free market-data adapters, offline: odd or short answers never crash a whole Desk panel."""
import pytest

from botscope.market_data import fed_odds, finra_short, fred_econ


def _obs(n, start=100.0):
    return [(f"2026-{12 - i % 12:02d}-01", start - i) for i in range(n)]


def test_fred_one_short_series_leaves_only_its_own_row_empty():
    def get(sid):
        if sid == "CPIAUCSL":
            return _obs(5)                             # a year-over-year number needs 13
        if sid == "PAYEMS":
            raise RuntimeError("api.stlouisfed.org -> HTTP 500")
        return _obs(14)
    rows = {r["fred_id"]: r for r in fred_econ.latest(get)}
    assert len(rows) == len(fred_econ.SERIES)
    assert rows["CPIAUCSL"]["value"] is None and "need 13" in rows["CPIAUCSL"]["as_of"]
    assert rows["PAYEMS"]["value"] is None and "HTTP 500" in rows["PAYEMS"]["as_of"]
    assert rows["UNRATE"]["value"] == 100.0 and rows["UNRATE"]["as_of"] == _obs(1)[0][0]
    assert all(r["source"] == "FRED" for r in rows.values())


def test_fred_year_over_year_and_change_math():
    rows = {r["fred_id"]: r for r in fred_econ.latest(lambda sid: [(f"d{i}", 113.0 - i) for i in range(14)])}
    assert rows["CPIAUCSL"]["value"] == round((113 / 101 - 1) * 100, 2)
    assert rows["PAYEMS"]["value"] == 1.0


def test_fred_without_a_key_says_where_to_get_one(monkeypatch):
    monkeypatch.setattr(fred_econ._http, "env_key", lambda name: "")
    with pytest.raises(RuntimeError, match="FRED_API_KEY missing"):
        fred_econ.latest()


def test_finra_rows_newest_first_and_broken_rows_skipped():
    raw = [{"symbolCode": "AAPL", "settlementDate": "2026-09-15", "currentShortPositionQuantity": 100},
           {"symbolCode": "AAPL", "settlementDate": "2026-09-30", "currentShortPositionQuantity": 120,
            "daysToCoverQuantity": 1.5},
           {"symbolCode": "AAPL", "settlementDate": "2026-08-29"},            # no share count
           {"symbolCode": "AAPL", "currentShortPositionQuantity": 5},         # no date
           "not a row"]
    rows = finra_short.rows_from(raw)
    assert [r["settled"] for r in rows] == ["2026-09-30", "2026-09-15"]
    assert rows[0]["days_to_cover"] == 1.5 and rows[0]["source"] == "FINRA"


def test_fed_odds_midpoint_last_trade_and_failure(monkeypatch):
    ev = {"events": [{"strike_date": "2026-12-10T00:00:00Z", "markets": [
        {"yes_sub_title": "Hold", "yes_bid_dollars": "0.60", "yes_ask_dollars": "0.70"},
        {"yes_sub_title": "Cut 25", "yes_bid_dollars": None, "yes_ask_dollars": "0.40", "last_price_dollars": "0.33"},
        {"yes_sub_title": "Hike", "yes_bid_dollars": "x"}]},
        {"strike_date": "2026-10-29T00:00:00Z", "markets": []}]}
    monkeypatch.setattr(fed_odds._http, "get", lambda *a, **k: ev)
    rows = fed_odds.fed_odds(meetings=2)
    assert [(r["outcome"], r["prob"]) for r in rows] == [("Hold", 0.65), ("Cut 25", 0.33), ("Hike", None)]
    assert rows[0]["meeting"] == "2026-12-10"

    def down(*a, **k):
        raise RuntimeError("api.elections.kalshi.com request failed: URLError")
    monkeypatch.setattr(fed_odds._http, "get", down)
    (row,) = fed_odds.fed_odds()
    assert row["prob"] is None and row["outcome"].startswith("unavailable: ") and row["source"] == "Kalshi"


def test_analyst_counts_newest_first_and_errors_named(monkeypatch):
    from botscope.market_data import analyst
    monkeypatch.setattr(analyst._http, "need_key", lambda name: "k")
    monkeypatch.setattr(analyst._http, "get", lambda *a, **k: [
        {"symbol": "AAPL", "period": "2026-08-01", "strongBuy": 1, "buy": 2, "hold": 3, "sell": 0, "strongSell": 0},
        {"symbol": "AAPL", "period": "2026-10-01", "strongBuy": 4, "buy": 5, "hold": None}, {"no": "period"}])
    rows = analyst.recommendations("aapl", months=3)
    assert [r["month"] for r in rows] == ["2026-10", "2026-08"]
    assert rows[0]["strong_buy"] == 4 and rows[0]["hold"] == 0 and rows[0]["strong_sell"] == 0
    monkeypatch.setattr(analyst._http, "get", lambda *a, **k: {"error": "You don't have access to this resource."})
    with pytest.raises(RuntimeError, match="don't have access"):
        analyst.recommendations("AAPL")


def test_watch_file_comments_are_ignored(tmp_path, monkeypatch):
    from botscope.market_data import bot_tickers
    f = tmp_path / "watch.txt"
    f.write_text("# my list\nspy\n  # indented note\nQQQ  # tech\n\n")
    monkeypatch.setattr(bot_tickers, "__file__", str(tmp_path / "bot_tickers.py"))
    assert bot_tickers.watched() == {"SPY", "QQQ"}


def test_earnings_keep_market_movers_and_skip_broken_rows(monkeypatch):
    from botscope.market_data import calendars
    monkeypatch.setattr(calendars._http, "need_key", lambda name: "k")
    monkeypatch.setattr(calendars, "movers", lambda extra=(), live=True: ["AAPL", "JPM"])
    weeks = iter([{"earningsCalendar": [{"date": "2026-10-30", "symbol": "AAPL", "hour": "amc", "epsEstimate": 1.6},
                                        {"date": "2026-10-20", "symbol": "TINY", "hour": "bmo"},
                                        {"symbol": "JPM"}, {"date": "2026-10-21"}]},
                  {"earningsCalendar": None}, {}])
    monkeypatch.setattr(calendars._http, "get", lambda *a, **k: next(weeks))
    rows = calendars.earnings(days=14)
    assert [(r["symbol"], r["when"]) for r in rows] == [("AAPL", "after close")]
    monkeypatch.setattr(calendars._http, "get", lambda *a, **k: {"ipoCalendar": None})
    assert calendars.ipos() == []

