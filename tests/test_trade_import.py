import pytest

from botscope import journal, trade_import

WEBULL = """Name,Symbol,Side,Status,Filled,Total Qty,Price,Avg Price,Time-in-Force,Placed Time,Filled Time
Apple,AAPL,Buy,Filled,10,10,@200.00,200.00,DAY,10/01/2026 08:59:00 CDT,10/01/2026 09:00:00 CDT
Apple,AAPL,Sell,Filled,4,4,@205.00,205.00,DAY,10/01/2026 09:10:00 CDT,10/01/2026 09:10:00 CDT
Apple,AAPL,Sell,Partially Filled,6,8,@190.00,190.00,DAY,10/01/2026 09:20:00 CDT,10/01/2026 09:30:00 CDT
Tesla,TSLA,Buy,Cancelled,0,5,@300.00,,DAY,10/01/2026 09:40:00 CDT,
Tesla,TSLA,Sell,Filled,5,5,@300.00,abc,DAY,10/01/2026 09:40:00 CDT,10/01/2026 09:41:00 CDT
Tesla,TSLA,Sell,Filled,2,2,@300.00,300.00,DAY,10/02/2026 09:00:00 CDT,10/02/2026 09:00:00 CDT
Tesla,TSLA,Buy,Filled,2,2,@290.00,290.00,DAY,10/02/2026 09:30:00 CDT,10/02/2026 09:30:00 CDT
"""


def test_webull_csv_round_trips_in_eastern_time(tmp_path):
    f = tmp_path / "Webull_Orders.csv"
    f.write_text(WEBULL)
    out = trade_import.from_webull(str(f), "America/Chicago")
    assert out["round_trips"] == 3 and out["not_filled"] == 1 and out["unreadable"] == 1 and out["read_only"]
    assert out["unreadable_lines"] == ["line 6: price 'abc' is not a number above 0"]     # counted, never guessed
    ts = trade_import.trades()
    assert [(t["symbol"], t["side"], t["qty"], t["pnl"]) for t in ts] == [
        ("AAPL", "long", 4, 20.0), ("AAPL", "long", 6, -60.0), ("TSLA", "short", 2, 20.0)]
    assert ts[0]["opened"] == "2026-10-01T10:00:00" and ts[0]["closed"] == "2026-10-01T10:10:00"   # Chicago -> Eastern
    assert ts[0]["source"] == "Webull file Webull_Orders.csv"


def test_webull_asks_for_the_time_zone_and_lists_unknown_columns(tmp_path):
    f = tmp_path / "w.csv"
    f.write_text(WEBULL)
    with pytest.raises(ValueError, match="which time zone"):
        trade_import.from_webull(str(f), None)
    with pytest.raises(ValueError, match="unknown time zone"):
        trade_import.from_webull(str(f), "Mars/Base")
    g = tmp_path / "other.csv"
    g.write_text("Date,Ticker,Action,Shares,Cost\n2026-10-01,SPY,BUY,1,500\n")
    with pytest.raises(ValueError, match="The file's columns: Date, Ticker, Action, Shares, Cost") as e:
        trade_import.from_webull(str(g), "America/New_York")
    assert "Symbol" in str(e.value) and "Filled Time" in str(e.value)
    assert journal.load("my_trades") == []


def test_reimport_replaces_and_keeps_the_same_trade_ids(tmp_path):
    f = tmp_path / "w.csv"
    f.write_text(WEBULL)
    trade_import.from_webull(str(f), "America/Chicago")
    ids = [t["trade_id"] for t in trade_import.trades()]
    trade_import.from_webull(str(f), "America/Chicago")
    assert [t["trade_id"] for t in trade_import.trades()] == ids and len(set(ids)) == 3
    assert trade_import.sources()[0]["trades"] == 3
    assert trade_import.forget("Webull file w.csv")["removed"] == 3 and trade_import.trades() == []


def test_fills_file_with_a_zone_per_row_and_an_open_lot(tmp_path):
    f = tmp_path / "fills.csv"
    f.write_text("# a label line is skipped\nsymbol,side,qty,price,time,tz\n"
                 "spy,buy,2,500,2026-10-05T09:31:00,America/New_York\nSPY,sell,2,501,2026-10-05T14:00:00Z,\n"
                 "QQQ,buy,1,400,2026-10-05T10:00:00,America/New_York\nQQQ,hold,1,400,2026-10-05T10:00:00,\n")
    out = trade_import.from_fills_file(str(f))
    assert out["round_trips"] == 1 and out["unreadable"] == 1 and out["still_open"]
    t = trade_import.trades()[0]
    assert t["symbol"] == "SPY" and t["closed"] == "2026-10-05T10:00:00" and t["pnl"] == 2.0   # 14:00 UTC = 10:00 ET
    with pytest.raises(ValueError, match="no file"):
        trade_import.from_fills_file(str(tmp_path / "missing.csv"))


def test_text_import_is_the_same_as_a_file():
    out = trade_import.from_text("webull", WEBULL, "upload.csv", "America/Chicago")
    assert out["round_trips"] == 3 and out["source"] == "Webull file upload.csv"
    with pytest.raises(ValueError, match="unknown file type"):
        trade_import.from_text("robinhood", WEBULL, "x.csv", "America/Chicago")


HAND = "6f1c2a3e-9b4d-4e21-8a77-0c5d3b2e1f90"       # Alpaca gives an order with no id of its own a random UUID


def test_alpaca_leaves_out_bot_orders_and_counts_them(monkeypatch):
    def o(side, price, minute, cid, symbol="SPY"):
        return {"symbol": symbol, "side": side, "qty": 1, "price": price, "time": f"2026-10-01T14:{minute}:00+00:00",
                "client_order_id": cid}
    raw = [o("buy", 100, 10, HAND), o("buy", 50, 11, "swing-1"), o("sell", 60, 12, "swing-2"), o("sell", 103, 13, HAND),
           o("buy", 10, 14, HAND, "QQQ"), o("sell", 12, 15, HAND, "QQQ")]
    monkeypatch.setattr(trade_import.imports, "_alpaca_fills", lambda days: raw)
    monkeypatch.setattr(trade_import.imports, "local_config", lambda: {"alpaca_rules": {"symbols": {"QQQ": "crypto"}}})
    monkeypatch.setattr("botscope.env.demo_mode", lambda: False)
    out = trade_import.from_alpaca(30)
    assert out["round_trips"] == 1 and out["bot_orders_skipped"] == 4
    assert [(t["symbol"], t["pnl"]) for t in trade_import.trades("Alpaca paper")] == [("SPY", 3)]


def test_rules_and_custom_ids_mark_bot_orders():
    spy = {"symbol": "SPY"}
    assert trade_import.is_bot_order(spy | {"client_order_id": "x-1"})
    assert trade_import.is_bot_order(spy | {"client_order_id": HAND}, {"prefix": {"6f1c": "b"}})
    assert not trade_import.is_bot_order(spy | {"client_order_id": HAND}) and not trade_import.is_bot_order(spy)


def test_alpaca_reads_filled_orders_only_and_converts_utc(monkeypatch):
    monkeypatch.setattr(trade_import.imports, "_alpaca_fills", lambda days: [
        {"symbol": "SPY", "side": "buy", "qty": 1, "price": 1, "time": "2026-10-01T13:31:00+00:00", "client_order_id": HAND},
        {"symbol": "SPY", "side": "sell", "qty": 1, "price": 3, "time": "2026-10-01T15:00:00+00:00", "client_order_id": ""}])
    monkeypatch.setattr("botscope.env.demo_mode", lambda: False)
    out = trade_import.from_alpaca(30)
    t = trade_import.trades("Alpaca paper")[0]
    assert out["round_trips"] == 1 and t["opened"] == "2026-10-01T09:31:00" and t["pnl"] == 2
    monkeypatch.setattr("botscope.env.demo_mode", lambda: True)
    with pytest.raises(RuntimeError, match="demo mode"):
        trade_import.from_alpaca(30)


def test_importer_never_trades_or_calls_out():
    src = open(trade_import.__file__).read()
    for word in ("submit_order", "cancel_order", "replace_order", "requests", "urllib", "http", "socket"):
        assert word not in src
