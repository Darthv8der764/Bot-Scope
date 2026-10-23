import json
import urllib.request

from botscope import imports, view


def _row(sym, side, status, when, cid="", filled=None):
    return {"symbol": sym, "side": side, "qty": 1.0, "filled_qty": 1.0 if filled else 0.0, "type": "limit", "limit": 100.0,
            "stop": None, "filled_price": filled, "status": status, "submitted": when, "filled": None, "client_order_id": cid}


def test_orders_grouped_by_bot_open_and_past(monkeypatch):
    monkeypatch.setattr(imports, "local_config", lambda: {})
    live = [_row("SPY", "buy", "new", "2026-10-17T14:00:00", "swing-9")]
    past = [_row("SPY", "sell", "filled", "2026-10-10T15:00:00", "swing-8", 101.0),
            _row("SPY", "buy", "canceled", "2026-10-12T15:00:00", "swing-7"),
            _row("BTC/USD", "buy", "filled", "2026-10-11T00:00:00", "x", 80000.0)]
    monkeypatch.setattr(imports, "_alpaca_orders", lambda days: (live, past))
    monkeypatch.setattr("botscope.env.demo_mode", lambda: False)
    out = imports.orders(rules={"prefix": {"swing-": "swing"}, "symbols": {"BTC/USD": "crypto"}})
    g = {b["bot"]: b for b in out["bots"]}
    assert out["read_only"] and set(g) == {"crypto", "swing"}
    assert len(g["swing"]["open"]) == 1 and [r["status"] for r in g["swing"]["past"]] == ["canceled", "filled"]  # newest first
    assert imports.orders(bot="crypto", rules={"symbols": {"BTC/USD": "crypto"}})["bots"][0]["past"][0]["symbol"] == "BTC/USD"
    assert imports.orders(limit=1, rules={"prefix": {"swing-": "swing"}})["bots"][-1]["past_total"] == 2


def test_orders_code_only_reads():
    src = open(imports.__file__).read()
    for word in ("submit_order", "cancel_order", "replace_order", "close_position", "close_all"):
        assert word not in src


def test_imported_api_and_studio_tab():
    base = view.ensure_server()
    got = json.load(urllib.request.urlopen(base + "/api/imported?orders=1"))
    assert "bots" in got and ("orders" in got or "orders_error" in got)
    studio = view.PAGE.with_name("studio.html").read_text()
    assert '["imported", "My bots", null]' in studio and "never places, changes or cancels" in studio
