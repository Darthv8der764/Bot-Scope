"""Offline checks of the order guard: paper by default, live locked, size cap, STOP, runaway brake, hook output."""
import io
import json

import pytest

from botscope import guard, settings


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_JOURNAL_DIR", str(tmp_path))
    monkeypatch.setenv("BOTSCOPE_ENV_FILE", str(tmp_path / "none.env"))
    for k in ("BOTSCOPE_LIVE_TRADING", "BOTSCOPE_ACCOUNT", "ALPACA_API_KEY"):
        monkeypatch.delenv(k, raising=False)


ORDER = {"symbol": "AAPL", "side": "buy", "qty": "2", "limit_price": "200"}


def test_paper_keys_are_allowed_unknown_keys_count_as_live(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "PKTEST")
    assert guard.check_order(ORDER)["decision"] == "allow"
    monkeypatch.setenv("ALPACA_API_KEY", "AKTEST")
    assert guard.account_mode() == "live"
    monkeypatch.delenv("ALPACA_API_KEY")
    assert guard.account_mode() == "live"                       # can't tell -> treated as live (safe)


def test_live_is_locked_until_switch_then_capped_then_asks(monkeypatch):
    d = guard.check_order(ORDER, mode="live")
    assert d["decision"] == "deny" and "locked" in d["reason"]
    monkeypatch.setenv("BOTSCOPE_LIVE_TRADING", "1")
    assert guard.check_order(ORDER, mode="live")["decision"] == "ask"            # $400: real money always asks
    assert "cap" in guard.check_order({**ORDER, "qty": "10"}, mode="live")["reason"]   # $2,000 > $1,000
    assert "size" in guard.check_order({"symbol": "AAPL", "side": "buy", "qty": "1"}, mode="live")["reason"]
    assert "graduation" in guard.check_order(ORDER, bot="first_hour_breakout", mode="live")["reason"]
    settings.change(live_bots=["first_hour_breakout"])
    assert guard.check_order(ORDER, bot="first_hour_breakout", mode="live")["decision"] == "ask"


def test_options_size_counts_100_shares():
    assert guard.order_size({"qty": "1", "limit_price": "3.5", "kind": "option"}) == 350


def test_stop_blocks_everything_and_resume_needs_confirm():
    guard.stop_everything("test")
    assert "STOP" in guard.check_order(ORDER, mode="paper")["reason"]
    assert guard.resume()["still_stopped"] and settings.load()["stopped"]
    guard.resume(confirm=True)
    assert guard.check_order(ORDER, mode="paper")["decision"] == "allow"


def test_runaway_brake():
    settings.change(max_orders_per_day=3)
    for _ in range(3):
        d = guard.check_order(ORDER, mode="paper"); guard.record(ORDER, d, "test")
    assert "runaway" in guard.check_order(ORDER, mode="paper")["reason"]


def test_hook_denies_live_order_and_ignores_other_tools(monkeypatch, capsys):
    monkeypatch.setenv("ALPACA_API_KEY", "AKLIVE")
    ev = {"tool_name": "mcp__alpaca__place_stock_order", "tool_input": ORDER}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(ev)))
    guard.main()
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "locked" in out["permissionDecisionReason"]
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"tool_name": "mcp__alpaca__get_clock", "tool_input": {}})))
    guard.main()
    assert capsys.readouterr().out == ""
    monkeypatch.setenv("ALPACA_API_KEY", "PKPAPER")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(ev)))
    guard.main()
    assert capsys.readouterr().out == ""                                    # paper: allowed, no output
