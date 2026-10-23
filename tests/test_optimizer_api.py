"""Studio's Optimizer tab: run the honest optimizer from the page, watch its progress, one backtest at a time."""
import json
import shutil
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from botscope import journal, optimizer, server, view


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_DEMO", "1")                 # made-up prices: no keys, no network
    monkeypatch.setenv("BOTSCOPE_BOTS_DIR", str(tmp_path / "bots"))
    (tmp_path / "bots").mkdir()
    shutil.copy(Path(view.__file__).resolve().parent.parent / "bots" / "pullback_swing.py", tmp_path / "bots")
    return view.ensure_server()


def post(base, path, body):
    req = Request(base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urlopen(req))


def test_run_saves_a_heat_map_and_never_changes_the_bot(base, tmp_path):
    before = (tmp_path / "bots" / "pullback_swing.py").read_text()
    s = json.load(urlopen(base + "/api/optimizer/settings?bot=pullback_swing"))
    assert s["default"] == ["trend_days", "rsi_days"] and s["today"]["rsi_below"] == 10
    r = post(base, "/api/optimizer/run", {"bot": "pullback_swing", "a": "rsi_below", "b": "stop_ranges"})
    assert r["settings"] == ["rsi_below", "stop_ranges"] and r["cells_tried"] >= 9 and r["verdict"]
    saved = json.load(urlopen(base + "/api/optimizer"))[0]
    assert saved["settings"] == ["rsi_below", "stop_ranges"] and "UNTESTED" in saved["period"]
    assert (tmp_path / "bots" / "pullback_swing.py").read_text() == before
    assert json.load(urlopen(base + "/api/optimizer/progress")) == {}           # cleared when the run ends


def test_progress_counts_cells_while_running(base, monkeypatch):
    seen, real = [], optimizer.report.full_report

    def spy(*a, **k):
        seen.append(json.load(urlopen(base + "/api/optimizer/progress")))
        return real(*a, **k)
    monkeypatch.setattr(optimizer.report, "full_report", spy)
    post(base, "/api/optimizer/run", {"bot": "pullback_swing", "a": "rsi_below", "b": "stop_ranges"})
    assert seen[0]["done"] == 0 and seen[0]["total"] == 25 and seen[0]["bot"] == "Pullback swing"
    assert [p["done"] for p in seen[:25]] == list(range(25)) and "rsi_below=" in seen[3]["now"]


def test_a_second_run_while_one_is_going_says_so(base):
    assert server._one_backtest.acquire(blocking=False)
    optimizer.PROGRESS.update(bot="Pullback swing", done=3, total=25)
    try:
        r = post(base, "/api/optimizer/run", {"bot": "pullback_swing"})
    finally:
        optimizer.PROGRESS.clear()
        server._one_backtest.release()
    assert r["error"].startswith("another backtest is already running (Pullback swing: 3 of 25 cells)")
    assert journal.load("optimizer") == []


def test_bad_bot_and_bad_settings_read_plainly(base):
    r = post(base, "/api/optimizer/run", {"bot": "no_such_bot"})
    assert "no_such_bot" in r["error"] and '\\"' not in r["error"] and not r["error"].startswith('"')
    r = post(base, "/api/optimizer/run", {"bot": "pullback_swing", "a": "nope"})
    assert "number settings" in r["error"]
    assert server._one_backtest.acquire(blocking=False)              # a failed run gives the lock back
    server._one_backtest.release()
    with pytest.raises(Exception):                                  # the settings route says so with a 400
        urlopen(base + "/api/optimizer/settings?bot=no_such_bot")


def test_other_websites_cannot_start_a_run(base):
    req = Request(base + "/api/optimizer/run", data=b'{"bot":"pullback_swing"}',
                  headers={"Content-Type": "application/json", "Origin": "http://evil.example"})
    with pytest.raises(Exception, match="403"):
        urlopen(req)


def test_studio_loads_the_tab_code():
    base = view.ensure_server()
    assert b"optRun" in urlopen(base + "/optimizer.js").read()
    page = view.PAGE.with_name("studio.html").read_text()
    assert '<script src="/optimizer.js"></script>' in page and 'id="optrun"' in page
