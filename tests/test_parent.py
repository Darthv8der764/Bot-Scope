"""Parent view: read-only summary + page with nothing that can change a setting."""
import re
from pathlib import Path

from botscope import guard, journal, parent, settings

PAGE = Path(parent.__file__).with_name("web") / "parent.html"


def test_summary_shows_lock_limits_bots_and_recent_activity(monkeypatch):
    monkeypatch.delenv("BOTSCOPE_LIVE_TRADING", raising=False)
    journal.add("paper_results", {"bot": "nr7_swing", "symbol": "SPY", "day": "2026-10-16", "side": "long", "r": 0.5,
                                  "trade_id": "x", "why_out": "target"})
    guard.stop_everything("test")
    s = parent.summary()
    assert s["read_only"] and s["live_lock_on"] and "LOCKED" in s["live_lock"] and s["stopped"]
    assert s["limits"]["max_order_usd"] == settings.DEFAULTS["max_order_usd"]
    assert s["bots"] and all(b["money"].startswith("paper") and not b["on_today"] for b in s["bots"])
    assert s["recent_paper_trades"][0]["r"] == 0.5 and s["recent_alerts"][0]["source"] == "STOP"


def test_page_has_no_controls_and_only_reads():
    html = PAGE.read_text()
    assert not re.search(r"<(button|input|form|select|textarea)\b", html, re.I)
    assert "method" not in html and "POST" not in html and html.count("fetch(") == 1 and 'fetch("/api/parent")' in html


def test_server_only_serves_it_on_get():
    src = (Path(parent.__file__).with_name("view.py")).read_text()
    post = src.split("def do_POST", 1)[1]
    assert "/api/parent" in src.split("def do_POST", 1)[0] and "parent" not in post
