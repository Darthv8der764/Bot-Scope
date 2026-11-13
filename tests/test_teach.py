"""Offline checks of teach-me mode (made-up bars, no network)."""
import pytest

from botscope import teach, view
from test_format import fake_day


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(view.data, "day_bars", lambda sym, d, tf: (fake_day(), "made-up test bars"))


def test_lesson_follows_the_real_replay():
    out = teach.teach_me("first_hour_breakout", "TEST", "2026-09-01")
    titles = [p["title"] for p in out["lesson"]]
    assert titles[0] == "My rules" and titles[1] == "Before my first trade" and titles[2].startswith("Trade 1")
    wait = out["lesson"][1]["steps"]
    assert wait[0].startswith("09:30-") and "opening range" in wait[0]
    trade = " ".join(out["lesson"][2]["steps"])
    st = view.build("first_hour_breakout", "TEST", "2026-09-01")
    t = st["trades"][0]
    assert f"{t['entry']:.2f}" in trade and f"{t['stop']:.2f}" in trade and f"{t['r']:+.2f}R" in trade
    assert "target hit" in trade


def test_glossary_only_has_words_used_and_quiz_is_there():
    out = teach.teach_me("first_hour_breakout", "TEST", "2026-09-01")
    assert "R" in out["words_used"] and "stop" in out["words_used"]
    assert "near miss" not in out["words_used"] or any("Near miss" in p["title"] for p in out["lesson"])
    assert out["quiz"].startswith("Quiz") and "financial advice" in out["note"]


def test_waits_merge_runs_and_cap():
    reasons = {str(i * 60): {"kind": "no_trade", "reason": f"price {i} below {i + 1}"} for i in range(5)}
    reasons |= {str(600 + i * 60): {"kind": "no_trade", "reason": f"reason {chr(65 + i)}"} for i in range(20)}
    w = teach._waits(reasons, None, None)
    assert w[0] == {"from": "00:00", "to": "00:04", "reason": "price 0 below 1"}
    assert len(w) == teach.MAX_WAIT_STEPS + 1 and "more stretches" in w[teach.MAX_WAIT_STEPS // 2]["reason"]


def test_loss_explains_the_stop():
    t = {"side": "short", "entry": 100.0, "stop": 101.0, "target": 98.0, "why_in": "it broke down", "t_in": 0,
         "t_out": 600, "exit": 101.0, "why_out": "stop hit", "r": -1.05}
    s = " ".join(teach._trade_steps(t, 10_000))
    assert "sold short" in s and "2.0R away" in s and "planned one" in s


def test_page_has_teach_button_and_route():
    import json
    from pathlib import Path
    from urllib.request import urlopen
    html = (Path(view.__file__).parent / "web" / "bot_view.html").read_text()
    assert 'id="teachbtn"' in html and "/api/teach?" in html
    out = json.loads(urlopen(view.ensure_server() + "/api/teach?bot=first_hour_breakout&symbol=TEST&day=2026-09-01").read())
    assert out["lesson"][0]["title"] == "My rules"


def test_daily_bot_lessons_name_days_not_00_00():
    """A daily bot's lesson read "00:00-00:00: not enough days of history yet" (QA pass 2026-11-12)."""
    from datetime import datetime, timezone
    day = lambda d: int(datetime(2026, 6, d, tzinfo=timezone.utc).timestamp())     # noqa: E731
    st = {"bot": {"name": "Daily", "rules": ["r"], "timeframe": "1Day"}, "symbol": "SPY", "day": "2026-06-30",
          "source": "test", "account": "PAPER", "ghosts": [], "vetoed": [],
          "reasons": {str(day(1)): {"kind": "no_trade", "reason": "not enough days of history yet"},
                      str(day(2)): {"kind": "no_trade", "reason": "not enough days of history yet"},
                      str(day(3)): {"kind": "no_trade", "reason": "no signal"}},
          "trades": [{"side": "long", "t_in": day(5), "t_out": day(9), "entry": 100.0, "stop": 98.0, "target": 104.0,
                      "exit": 104.0, "why_in": "x", "why_out": "target hit", "r": 1.9}]}
    out = teach.lesson(st)
    text = " ".join(s for p in out["lesson"] for s in p["steps"])
    assert "00:00" not in text and "Jun 1-Jun 2: not enough days" in text and "Jun 3: no signal" in text
    assert "Jun 5: I bought" in text and "Jun 9: I got out" in text
