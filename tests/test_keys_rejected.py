"""Alpaca refusing the saved keys (HTTP 401) reads as one plain sentence on every Studio tab, page and tool: never
its raw HTML page, never a dropped connection, never an empty chart or a "0 trades" result. No network: the fake
Alpaca in alpaca401.py answers every request with the real 401 page."""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import alpaca401  # noqa: E402
from botscope import desk, server, signals, view  # noqa: E402
from botscope.errtext import KEYS_REJECTED, KeysRejected, keys_rejected, say, short  # noqa: E402

BOT, DAY = "first_hour_breakout", "2026-11-02"
GETS = [f"/api/view?bot={BOT}&symbol=SPY&day={DAY}", f"/api/view?bot={BOT}&symbol=SPY&day={DAY}&span=5d",
        f"/api/zoom?symbol=SPY&day={DAY}", f"/api/flight?bot={BOT}&symbol=SPY&day={DAY}", "/api/signals?examples=1",
        f"/api/clip?bot={BOT}&symbol=SPY&day={DAY}", "/api/weather_calendar", f"/api/playground?bot={BOT}",
        f"/api/eventdays?bot={BOT}", f"/api/whatif?bot={BOT}&refresh=1", f"/api/timemap?bot={BOT}",
        f"/api/alike?bot={BOT}", f"/api/teach?bot={BOT}&symbol=SPY&day={DAY}"]
POSTS = [("/api/factory", {"goal": "a calm daily ETF bot"}), ("/api/optimizer/run", {"bot": BOT}),
         ("/api/mytrades/import", {"broker": "alpaca"}),
         ("/api/move", {"bot": BOT, "symbol": "SPY", "day": DAY, "trade_id": "x", "stop": 1})]
PANELS = ["board", "movers", "news", "options", "risk", "weather"]


@pytest.fixture
def refused(monkeypatch, tmp_path):
    signals._cache.clear()
    return alpaca401.refuse(monkeypatch, tmp_path)


def _answer(req) -> dict:
    """The JSON the page gets back, whatever the status (a dropped connection fails the test)."""
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        assert e.headers.get("Content-Type") == "application/json"
        return json.load(e)


def _plain(got: dict, where: str):
    assert got.get("error") == KEYS_REJECTED, f"{where}: {str(got)[:300]}"


def test_every_page_route_says_the_keys_were_refused(refused):
    base = view.ensure_server()
    for path in GETS:
        _plain(_answer(base + path), path)
    for path, body in POSTS:
        req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        _plain(_answer(req), path)
    assert any("alpaca" in u for u in refused)                 # the refusal really came from (fake) Alpaca


def test_desk_panels_say_it_instead_of_html(refused):
    for name in PANELS:
        _plain(desk.panel(name), name)
    lines = " ".join(desk.panel("brief")["lines"])
    assert KEYS_REJECTED in lines and "<html" not in lines
    kd = desk.panel("keydates", {"symbol": "AAPL"})
    assert not any("<html" in p for p in kd["problems"]) and any(KEYS_REJECTED in p for p in kd["problems"])


def test_imported_orders_say_it_and_the_summary_still_shows(refused):
    got = _answer(view.ensure_server() + "/api/imported?orders=1")
    assert got["orders_error"] == KEYS_REJECTED and "bots" in got


def test_signals_stop_once_with_the_keys_sentence_not_one_line_per_symbol(refused):
    with pytest.raises(KeysRejected):
        signals.scan(True)


def test_mcp_tools_say_it(refused):
    for out in (server.open_bot_view(BOT, "SPY", DAY), server.run_backtest(BOT, ["SPY"], days=5),
                server.market_board()):
        _plain(out, str(out)[:80])


def test_safe_keeps_other_surprises_as_they_were():
    def boom():
        raise ZeroDivisionError("x")
    with pytest.raises(ZeroDivisionError):
        server._safe(boom)


class APIError(Exception):          # the same name and field as alpaca.common.exceptions.APIError
    def __init__(self, msg, status):
        super().__init__(msg)
        self.status_code = status


def test_refusal_is_found_through_a_wrapped_error():
    try:
        try:
            raise APIError(alpaca401.PAGE, 401)
        except APIError as e:
            raise RuntimeError("could not load SPY") from e
    except RuntimeError as wrapped:
        assert keys_rejected(wrapped) and say(wrapped) == KEYS_REJECTED and short(wrapped) == KEYS_REJECTED
    assert not keys_rejected(APIError("rate limited", 429)) and short(ValueError("bad day")) == "ValueError: bad day"


def test_pages_show_the_error_field():
    web = Path(view.__file__).with_name("web")
    assert "didn't accept your saved keys" in (web / "desk.html").read_text()        # desk: the keys note + Get started link
    for page in ("zoom.html", "flight.html", "playground.html", "clip.html", "weather.html", "signals.js",
                 "optimizer.js", "factory.js", "mytrades.js"):
        assert ".error" in (web / page).read_text(), page


def test_account_summary_says_it_too(refused):
    """The paper-account tool calls Alpaca's trading API directly (not the bars), so it gets its own check."""
    _plain(server.account_summary(), "account_summary")


def test_offline_reads_as_couldnt_reach_on_the_page(refused, monkeypatch):
    """No internet: the chart says "Couldn't reach data.alpaca.markets", not requests' connection-pool dump."""
    import requests

    def offline(self, method, url, *a, **k):
        raise requests.ConnectionError(f"HTTPSConnectionPool(host='data.alpaca.markets', port=443): Max retries "
                                       f"exceeded with url: {url}", request=requests.Request(method, url).prepare())
    monkeypatch.setattr(requests.Session, "request", offline)
    got = _answer(view.ensure_server() + f"/api/view?bot={BOT}&symbol=SPY&day={DAY}")
    assert got["error"].startswith("Couldn't reach data.alpaca.markets (is this computer online?)")
