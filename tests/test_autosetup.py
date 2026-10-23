from botscope import autosetup, journal

BOT = '''
import alpaca
SYMBOLS = ["SPY", "QQQ"]
TIMEFRAME = "5Min"
stop_loss = 0.02
take_profit = 0.04
def run(df):
    df["ema"] = df.close.ewm(span=20).mean()
    rsi = compute_rsi(df)
    if df.close.iloc[-1] > df.ema.iloc[-1]:
        api.submit_order(symbol="SPY", qty=1, side="buy")
'''


def test_scan_reads_code_and_logs_without_running(tmp_path):
    d = tmp_path / "theirbot"
    d.mkdir()
    (d / "bot.py").write_text(BOT + "\nraise SystemExit('never run me')\n")
    (d / "trades.csv").write_text("Ticker,Direction,Entry Price,Exit Price,Shares,Exit Time\nSPY,long,1,2,1,2026-10-01\n")
    (d / "notes.csv").write_text("a,b\n1,2\n")
    (d / ".venv").mkdir()
    (d / ".venv" / "x.py").write_text("'AAPL'\n")
    out = autosetup.scan(str(d))
    s = out["suggested"]
    assert s["symbols"][:2] == ["SPY", "QQQ"] and "AAPL" not in s["symbols"] and s["timeframe"] == "5Min"
    assert {"ema", "rsi"} <= set(s["indicators"]) and s["stop_hints"] and s["target_hints"]
    assert [c["file"] for c in out["code_files"]] == ["bot.py"]
    log = out["trade_logs"][0]
    assert log["file"] == "trades.csv" and log["mapping"] == {"symbol": "Ticker", "side": "Direction", "entry": "Entry Price",
                                                              "exit": "Exit Price", "qty": "Shares", "closed": "Exit Time"}
    assert any("submit_order" in c for c in out["needs_your_check"]) and out["read_only"]


def test_scan_flags_missing_stop_and_pine(tmp_path):
    f = tmp_path / "s.pine"
    f.write_text('//@version=5\nstrategy("x")\nif ta.crossover(close, ta.sma(close, 20))\n    strategy.entry("L", strategy.long)\n')
    out = autosetup.scan(str(f))
    assert "import_pine" in out["next"] and any("none found" in c for c in out["needs_your_check"])


def test_finish_reports_and_saves():
    out = autosetup.finish("nr7_swing", "their_bot/", ["buy on an NR7 day"], ["scales in twice"], ["a 2% stop"])
    md = out["mapping_report"]
    assert "## Not translated (needs your check)\n- scales in twice" in md and "a 2% stop" in md
    assert out["check"]["checks"] and out["next"] == 'honest_report("nr7_swing")'
    assert journal.load("auto_setup")[-1]["not_translated"] == ["scales in twice"]


def test_finish_on_a_bot_that_does_not_exist():
    from botscope import server
    assert "no bot named" in server.auto_setup(how="finish", bot="no_such_bot")["error"]
