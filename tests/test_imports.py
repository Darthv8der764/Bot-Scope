import json
import subprocess

import pytest

from botscope import confidence, imports, journal


def test_pair_fills_fifo_by_prefix_and_symbol():
    fills = [
        {"symbol": "SPY", "side": "buy", "qty": 10, "price": 100, "time": "2026-10-01T14:00", "client_order_id": "swing-1"},
        {"symbol": "SPY", "side": "sell", "qty": 4, "price": 105, "time": "2026-10-02T14:00", "client_order_id": "swing-2"},
        {"symbol": "SPY", "side": "sell", "qty": 6, "price": 90, "time": "2026-10-03T14:00", "client_order_id": "swing-3"},
        {"symbol": "BTC/USD", "side": "sell", "qty": 1, "price": 80000, "time": "2026-10-01T00:00", "client_order_id": "x"},
        {"symbol": "BTC/USD", "side": "buy", "qty": 1, "price": 79000, "time": "2026-10-02T00:00", "client_order_id": "x"},
        {"symbol": "QQQ", "side": "buy", "qty": 1, "price": 500, "time": "2026-10-02T00:00", "client_order_id": "y"},
    ]
    out = imports.pair_fills(fills, {"prefix": {"swing-": "swing"}, "symbols": {"BTC/USD": "crypto"}})
    assert [(t["bot"], t["symbol"], t["side"], t["qty"], t["pnl"]) for t in out] == [
        ("crypto", "BTC/USD", "short", 1, 1000), ("swing", "SPY", "long", 4, 20), ("swing", "SPY", "long", 6, -60)]
    # QQQ is still open: no closing fill, not counted


def test_file_import_with_mapping_and_rerun_replaces(tmp_path):
    f = tmp_path / "log.csv"
    f.write_text("sym,dir,entry_px,exit_px,shares,R,exit_time\nSPY,long,100,102,5,1.0,2026-10-01T15:00\n"
                 "QQQ,short,500,505,1,-0.5,2026-10-02T15:00\n,long,1,2,1,,\n")
    m = {"symbol": "sym", "side": "dir", "entry": "entry_px", "exit": "exit_px", "qty": "shares", "r": "R", "closed": "exit_time"}
    out = imports.from_file(str(f), "mine", m, link_to="pullback_swing")
    b = out["bots"][0]
    assert out["skipped"] == 1 and b["trades"] == 2 and b["won"] == 1 and b["total_usd"] == 5.0 and out["read_only"]
    assert b["from"] == "2026-10-01" and b["to"] == "2026-10-02"
    imports.from_file(str(f), "mine", m, link_to="pullback_swing")
    assert len(journal.load("imported_trades")) == 2              # re-run replaces, never doubles
    assert imports.live_rs("pullback_swing") == [1.0, -0.5]
    assert confidence.for_bot("pullback_swing")["live"]["trades"] == 2   # linked trades count as live evidence


def test_json_import_and_bad_mapping(tmp_path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps({"trades": [{"symbol": "nvda", "entry": 10, "exit": 9, "side": "sell"}]}))
    out = imports.from_file(str(f), "j")
    assert out["bots"][0]["total_usd"] == 1.0                      # a short that fell made money
    with pytest.raises(ValueError, match="unknown field"):
        imports.from_file(str(f), "j", {"price": "x"})
    g = tmp_path / "x.csv"
    g.write_text("a,b\n1,2\n")
    with pytest.raises(ValueError, match="Your columns: a, b"):
        imports.from_file(str(g), "x")


def test_local_config_paths_and_never_committed(tmp_path, monkeypatch):
    f = tmp_path / "rt.csv"
    f.write_text("symbol,entry_px,exit_px\nSPY,1,2\n")
    cfg = tmp_path / "local.json"
    cfg.write_text(json.dumps({"imports": [{"name": "stock", "path": str(f), "mapping": {"entry": "entry_px", "exit": "exit_px"}}]}))
    monkeypatch.setenv("BOTSCOPE_LOCAL_CONFIG", str(cfg))
    assert imports.from_local()["imports"][0]["trades"] == 1
    ignored = subprocess.run(["git", "check-ignore", "botscope.local.json"], cwd=imports.ROOT, capture_output=True)
    assert ignored.returncode == 0


def test_alpaca_import_reads_only(monkeypatch):
    monkeypatch.setattr(imports, "_alpaca_fills", lambda days: [
        {"symbol": "SPY", "side": "buy", "qty": 1, "price": 1, "time": "2026-10-01", "client_order_id": ""},
        {"symbol": "SPY", "side": "sell", "qty": 1, "price": 3, "time": "2026-10-02", "client_order_id": ""}])
    monkeypatch.setattr("botscope.env.demo_mode", lambda: False)
    out = imports.from_alpaca(days=30)
    assert out["bots"][0]["total_usd"] == 2 and "Alpaca paper" in out["source"]
    src = open(imports.__file__).read()
    assert "submit_order" not in src and "cancel_order" not in src and "replace_order" not in src


def test_option_round_trip_counts_100_shares():
    f = [{"symbol": "SPY261016C00500000", "side": "buy", "qty": 1, "price": 2.0, "time": "1", "client_order_id": ""},
         {"symbol": "SPY261016C00500000", "side": "sell", "qty": 1, "price": 2.5, "time": "2", "client_order_id": ""}]
    assert imports.pair_fills(f)[0]["pnl"] == 50


def test_strategy_codes_get_full_names_and_trades_come_back_per_strategy(tmp_path):
    """A trade log with a strategy column: each strategy is its own bot (with its full name if given), and one
    strategy's trades can be read back on their own (Studio's My bots: click a strategy)."""
    from botscope import imports
    f = tmp_path / "rt.csv"
    f.write_text("setup,symbol,side,entry_px,exit_px,r,entry_time\nONE,AAA,long,10,11,1.0,2026-10-12 10:00\n"
                 "TWO,BBB,short,20,21,-1.0,2026-10-12 11:00\nONE,CCC,long,5,4,-1.0,2026-10-13 10:00\n")
    imports.from_file(str(f), "mybot", {"bot": "setup", "entry": "entry_px", "exit": "exit_px", "opened": "entry_time"},
                      names={"ONE": "Example strategy one"})
    bots = {b["bot"]: b for b in imports.summary("mybot")["bots"]}
    assert set(bots) == {"ONE: Example strategy one", "TWO"}                  # a code with no name stays as is
    assert bots["ONE: Example strategy one"]["trades"] == 2
    assert [t["symbol"] for t in imports.trades("mybot", "TWO")] == ["BBB"]


def test_each_strategy_links_to_its_own_bot(tmp_path):
    """link_to as {strategy code: bot id}: each strategy's trades count as live evidence for its own bot."""
    from botscope import imports
    f = tmp_path / "rt.csv"
    f.write_text("setup,symbol,side,entry_px,exit_px,r\nONE,AAA,long,10,11,1.0\nTWO,BBB,short,20,21,-1.0\nXX,CCC,long,5,4,-1\n")
    imports.from_file(str(f), "mybot", {"bot": "setup", "entry": "entry_px", "exit": "exit_px"},
                      link_to={"ONE": "one_bot", "TWO": "two_bot"}, names={"ONE": "Example strategy one"})
    assert imports.live_rs("one_bot") == [1.0] and imports.live_rs("two_bot") == [-1.0]
    assert {b["bot"]: b["linked_to"] for b in imports.summary("mybot")["bots"]} == {
        "ONE: Example strategy one": "one_bot", "TWO": "two_bot", "XX": None}
