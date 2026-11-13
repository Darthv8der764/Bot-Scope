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
        trade_import.from_text("schwab", WEBULL, "x.csv", "America/Chicago")


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


def test_the_same_trade_from_two_sources_is_counted_once():
    from botscope import trade_import as ti
    first = [ti.fill("SPY", "buy", 2, 100, "2026-10-05T09:31:05", "America/New_York"),
             ti.fill("SPY", "sell", 2, 101, "2026-10-05T09:50:00", "America/New_York"),
             ti.fill("QQQ", "buy", 1, 50, "2026-10-06T10:00:00", "America/New_York"),
             ti.fill("QQQ", "sell", 1, 49, "2026-10-06T10:20:00", "America/New_York")]
    none = {"rows": 4, "not_filled": 0, "unreadable": 0, "unreadable_lines": []}
    ti.save("fills file a.csv", first, none)
    again = [ti.fill("SPY", "buy", 2, 100, "2026-10-05T13:31:40", "UTC"),        # same trade, other seconds and zone
             ti.fill("SPY", "sell", 2, 101, "2026-10-05T13:50:00", "UTC"),
             ti.fill("AAPL", "buy", 3, 200, "2026-10-07T10:00:00", "UTC"),
             ti.fill("AAPL", "sell", 3, 201, "2026-10-07T10:30:00", "UTC")]
    out = ti.save("Alpaca paper", again, none)
    assert out["round_trips"] == 1 and out["duplicates_skipped"] == 1 and "fills file a.csv" in out["duplicates"]
    assert len(ti.trades()) == 3
    assert ti.save("fills file a.csv", first, none)["duplicates_skipped"] == 0     # re-importing a source replaces it
    ti.forget("fills file a.csv")
    assert ti.save("Alpaca paper", again, none)["round_trips"] == 2                # gone from a.csv: it comes back


# Made-up files in the column layouts other tools' guides describe (not confirmed from real exports).
ROBINHOOD = """"Activity Date","Process Date","Settle Date","Instrument","Description","Trans Code","Quantity","Price","Amount"
"10/7/2026","10/7/2026","10/8/2026","AAPL","Apple","Sell","10","$205.50","$2,055.00"
"10/7/2026","10/7/2026","10/8/2026","AAPL","Apple","Buy","10","$200.00","($2,000.00)"
"10/6/2026","10/6/2026","10/7/2026","","Interest Payment","INT","","","$0.12"
"10/6/2026","10/6/2026","10/7/2026","SPY","SPY 10/17/2026 Call $580.00","BTO","1","$2.10","($210.00)"
"10/5/2026","10/5/2026","10/6/2026","MSFT","Microsoft","Buy","5","$500.00","($2,500.00)"
"10/9/2026","10/9/2026","10/10/2026","MSFT","Microsoft","Sell","5","$495.00","$2,475.00"
"10/9/2026","10/9/2026","10/10/2026","NVDA","Nvidia","Buy","oops","$180.00","($180.00)"
"","","","","","","","",""
"The data provided is for informational purposes only.","","","","","","","",""
"""

FIDELITY = """Brokerage

Run Date,Account,Account Number,Action,Symbol,Description,Type,Price ($),Quantity,Commission ($),Fees ($),Accrued Interest ($),Amount ($),Settlement Date
10/08/2026,Individual,X0000,"YOU SOLD TESLA INC (TSLA) (Cash)",TSLA,TESLA INC,Cash,250.00,-4,,,,1000.00,10/09/2026
10/06/2026,Individual,X0000,"YOU BOUGHT TESLA INC (TSLA) (Cash)",TSLA,TESLA INC,Cash,240.00,4,,,,-960.00,10/07/2026
10/06/2026,Individual,X0000,"DIVIDEND RECEIVED VANGUARD (VOO) (Cash)",VOO,VANGUARD,Cash,,0.000,,,,3.10,
10/05/2026,Individual,X0000,"YOU BOUGHT CALL (SPY) SPDR OCT 17 26 $580 (100 SHS) (Cash)",-SPY261017C580,CALL,Cash,2.10,1,,,,-210.00,10/06/2026
10/05/2026,Individual,X0000,"YOU BOUGHT AMD (AMD) (Cash)",AMD,AMD,Cash,150.00,USD,,,,-150.00,10/06/2026

"The data and information in this spreadsheet is provided to you solely for your use."
"""


def test_robinhood_file_is_date_only_stocks_with_the_rest_counted():
    out = trade_import.from_text("robinhood", ROBINHOOD, "rh.csv", None)
    assert out["round_trips"] == 2 and out["options_skipped"] == 1 and out["times"] == "dates only"
    assert out["not_trades"] == 1                                                     # the interest payment
    assert out["unreadable"] == 1 and "line 8" in out["unreadable_lines"][0]
    ts = {t["symbol"]: t for t in trade_import.trades()}
    assert ts["AAPL"]["side"] == "long" and ts["AAPL"]["pnl"] == 55.0 and ts["AAPL"]["opened"] == "2026-10-07"
    assert ts["MSFT"]["pnl"] == -25.0 and ts["MSFT"]["closed"] == "2026-10-09"
    assert not trade_import.has_time(ts["AAPL"])


def test_fidelity_file_skips_note_lines_options_and_other_actions():
    out = trade_import.from_text("fidelity", FIDELITY, "Accounts_History.csv", None)
    assert out["round_trips"] == 1 and out["options_skipped"] == 1 and out["not_trades"] == 1
    assert out["unreadable"] == 1 and "swapped" in out["unreadable_lines"][0]
    t = trade_import.trades()[0]
    assert (t["symbol"], t["side"], t["qty"], t["pnl"], t["opened"]) == ("TSLA", "long", 4.0, 40.0, "2026-10-06")
    older = FIDELITY.replace("Run Date,Account,Account Number,", "Trade Date,Account,Account Number,")
    trade_import.forget("Fidelity file Accounts_History.csv")      # else the same trade is a duplicate and left out
    assert trade_import.from_text("fidelity", older, "old.csv", None)["round_trips"] == 1


def test_robinhood_capital_codes_and_negative_sell_quantities():
    text = ROBINHOOD.replace('"Sell","10"', '"SELL","-10"').replace('"Buy","10"', '"BUY","10"')
    out = trade_import.from_text("robinhood", text, "rh2.csv", None)
    assert out["round_trips"] == 2 and {t["symbol"]: t["pnl"] for t in trade_import.trades()}["AAPL"] == 55.0


def test_date_only_sells_with_nothing_open_are_skipped_not_shorted():
    text = ROBINHOOD.split("\n")[0] + """
"4/1/2026","4/1/2026","4/2/2026","AAPL","Apple","Sell","10","$200.00","$2,000.00"
"4/10/2026","4/10/2026","4/11/2026","AAPL","Apple","Buy","10","$180.00","($1,800.00)"
"""
    out = trade_import.from_text("robinhood", text, "rh-late.csv", None)
    assert out["round_trips"] == 0 and out["sold_before_file"] == 10 and "opened before" in out["sold_before"]
    assert out["still_open"] and trade_import.trades() == []


def test_fidelity_shorts_and_accounts_pair_the_right_way():
    head = FIDELITY.split("\n")[2]
    rows = [
        '03/05/2026,Individual,X1,"YOU SOLD SHORT TESLA (TSLA) (Margin)",TSLA,TESLA,Margin,300.00,-5,,,,1500.00,03/06/2026',
        '03/05/2026,Individual,X1,"YOU BOUGHT TO COVER TESLA (TSLA) (Margin)",TSLA,TESLA,Margin,310.00,5,,,,-1550.00,03/06/2026',
        '03/06/2026,IRA,X2,"YOU BOUGHT AMD (AMD) (Cash)",AMD,AMD,Cash,100.00,10,,,,-1000.00,03/09/2026',
        '03/09/2026,Individual,X1,"YOU SOLD AMD (AMD) (Cash)",AMD,AMD,Cash,110.00,-10,,,,1100.00,03/10/2026',
    ]
    out = trade_import.from_text("fidelity", head + "\n" + "\n".join(rows) + "\n", "acct.csv", None)
    ts = trade_import.trades()
    assert len(ts) == 1 and out["sold_before_file"] == 10                      # AMD was bought in another account
    t = ts[0]
    assert (t["symbol"], t["side"], t["entry"], t["exit"], t["pnl"]) == ("TSLA", "short", 300.0, 310.0, -50.0)


def test_two_alike_trades_against_one_saved_keeps_one():
    from botscope import trade_import as ti
    none = {"rows": 2, "not_filled": 0, "unreadable": 0, "unreadable_lines": []}
    one = [ti.fill("SPY", "buy", 1, 500, "2026-10-05T10:00:05", "America/New_York"),
           ti.fill("SPY", "sell", 1, 501, "2026-10-05T10:20:00", "America/New_York")]
    ti.save("a", one, none)
    two = one + [ti.fill("SPY", "buy", 1, 500, "2026-10-05T10:00:40", "America/New_York"),
                 ti.fill("SPY", "sell", 1, 499, "2026-10-05T10:30:00", "America/New_York")]
    out = ti.save("b", two, none)
    assert out["duplicates_skipped"] == 1 and out["round_trips"] == 1 and len(ti.trades()) == 2


def test_demo_and_real_trades_never_mix():
    from botscope import demo_trades
    trade_import.from_demo()
    out = trade_import.from_text("robinhood", ROBINHOOD, "rh.csv", None)
    assert "demo trades were removed" in out["demo_removed"]
    assert {t["source"] for t in trade_import.trades()} == {"Robinhood file rh.csv"}
    with pytest.raises(ValueError, match="would mix"):
        trade_import.from_demo()
    assert not any(t["source"] == demo_trades.LABEL for t in trade_import.trades())


def test_same_day_order_comes_from_the_rows_newest_first():
    head = ROBINHOOD.split("\n")[0]
    sold_old_then_bought = head + """
"4/2/2026","4/2/2026","4/3/2026","MSFT","Microsoft","Buy","1","$400.00","($400.00)"
"4/1/2026","4/1/2026","4/2/2026","AAPL","Apple","Buy","10","$180.00","($1,800.00)"
"4/1/2026","4/1/2026","4/2/2026","AAPL","Apple","Sell","10","$200.00","$2,000.00"
"""
    out = trade_import.from_text("robinhood", sold_old_then_bought, "a.csv", None)
    assert out["round_trips"] == 0 and out["sold_before_file"] == 10        # the sale came first: older shares
    trade_import.forget("Robinhood file a.csv")
    day_trade = sold_old_then_bought.replace('"Buy","10","$180.00"', '"Sell","10","$190.00"', 1).replace(
        '"Sell","10","$200.00"', '"Buy","10","$185.00"', 1)
    out = trade_import.from_text("robinhood", day_trade, "b.csv", None)
    t = trade_import.trades()[0]
    assert out["round_trips"] == 1 and (t["side"], t["entry"], t["exit"]) == ("long", 185.0, 190.0)
