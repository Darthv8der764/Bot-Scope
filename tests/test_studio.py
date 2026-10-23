"""BotScope Studio: one page whose tabs are the existing pages, plus the factory results tab."""
import json
from pathlib import Path
from urllib.request import Request, urlopen

from botscope import journal, server, view

WEB = Path(__file__).resolve().parent.parent / "botscope" / "web"


def test_studio_has_every_tab_and_reuses_the_pages():
    html = (WEB / "studio.html").read_text() + (WEB / "factory.js").read_text()      # the Factory tab's own file
    for path in ("/?bot=", "/desk", "/playground?bot=", "/map", "/api/factory", "lesson=1", "/label?bot=", "/preflight", "/flight?bot="):
        assert path in html
    assert "@media (max-width: 600px)" in html and "overflow-x: auto" in html      # phone width: tabs scroll


def test_studio_is_served_and_lists_factory_runs():
    base = view.ensure_server()
    assert b"BotScope Studio" in urlopen(base + "/studio").read()
    journal.add("factory_runs", {"goal": "g1", "run": "1"}); journal.add("factory_runs", {"goal": "g2", "run": "2"})
    runs = json.loads(urlopen(base + "/api/factory").read())
    assert [r["goal"] for r in runs][:2] == ["g2", "g1"]                            # newest first


def test_factory_from_the_page_waits_for_a_running_backtest():
    base = view.ensure_server()
    server._one_backtest.acquire()
    try:
        req = Request(base + "/api/factory", data=b'{"goal": "a calm daily ETF bot"}',
                      headers={"Content-Type": "application/json"})
        assert "already running" in json.loads(urlopen(req).read())["error"]
    finally:
        server._one_backtest.release()


def test_open_studio_tool_returns_a_local_url():
    out = server.open_studio("pullback_swing")
    assert out["url"].startswith("http://127.0.0.1:") and out["url"].endswith("/studio?bot=pullback_swing")


def test_factory_endpoint_refuses_other_sites_and_plain_forms():
    """A web page elsewhere can't start a factory run: JSON only, and only for this computer's own pages."""
    from urllib.error import HTTPError
    base = view.ensure_server()
    for headers in ({"Content-Type": "text/plain"}, {"Content-Type": "application/json", "Host": "evil.example"}):
        req = Request(base + "/api/factory", data=b'{"goal": "x"}', headers=headers)
        try:
            urlopen(req)
            raise AssertionError("should have been refused")
        except HTTPError as e:
            assert e.code == 403


def test_factory_progress_is_served_while_a_run_goes():
    from botscope import strategy_factory as sf
    base = view.ensure_server()
    sf.PROGRESS.update(goal="g", done=1, total=3, now="Dip buy", kept=0)
    try:
        assert json.loads(urlopen(base + "/api/factory/progress").read())["now"] == "Dip buy"
    finally:
        sf.PROGRESS.clear()
    assert json.loads(urlopen(base + "/api/factory/progress").read()) == {}


def test_preflight_and_optimizer_explain_themselves():
    from botscope import view
    studio = view.PAGE.with_name("studio.html").read_text()
    pre = view.PAGE.with_name("preflight.html").read_text()
    assert "Pre-flight = your daily on/off list" in studio and 'href="#preflight">Pre-flight</a>: your daily on/off list' in studio
    assert "Your daily on/off list" in pre and "No answer = yesterday's settings" in pre
    assert "What this page does, in plain English" in studio and "held-out year" in studio


def test_your_own_bots_are_marked_mine_and_listed():
    """Studio puts your own bots first and opens on one: bots_private/ (or non-example bots) count as yours."""
    from botscope import loader

    class Fake:
        source_file = ""
    ex = type("Ex", (Fake,), {"source_file": str(loader.ROOT / "bots" / "crypto_trend.py")})
    assert not loader.is_mine(ex)
    mine = type("Mine", (Fake,), {"source_file": str(loader.PRIVATE / "my_bot.py")})
    assert loader.is_mine(mine) == bool(loader.private_dir())
    html = (WEB / "studio.html").read_text()
    assert 'optgroup label="My bots"' in html and "botscope-studio-bot" in html
