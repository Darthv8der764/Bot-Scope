"""My trades: the MCP tools and the Studio tab's page routes (demo trades and a made-up CSV only)."""
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from botscope import journal, server, view

WEB = Path(__file__).resolve().parent.parent / "botscope" / "web"
CSV = "symbol,side,qty,price,time,tz\nSPY,buy,1,100,2026-10-05T09:31:00,America/New_York\nSPY,sell,1,103,2026-10-05T09:50:00,America/New_York\n"


def _post(path, body, headers=None):
    req = Request(view.ensure_server() + path, data=json.dumps(body).encode(),
                  headers=headers or {"Content-Type": "application/json"})
    try:
        return 200, json.loads(urlopen(req).read())
    except HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_tools_import_list_note_and_patterns():
    out = server.import_my_trades("demo")
    assert out["round_trips"] > 50 and "MADE-UP" in out["demo"]
    assert server.import_my_trades()["sources"][0]["trades"] == out["round_trips"]
    listed = server.my_trades(limit=3)
    assert listed["shown"] == 3 and listed["total"] == out["round_trips"]
    t = listed["trades"][0]
    noted = server.note_my_trade(t["trade_id"], setup="gap fill", note="made-up test note")
    assert noted["setup"] == "gap fill" and noted["stop"] == t["stop"]                 # the stop stayed
    p = server.my_trade_patterns()
    assert any(r["group"] == "gap fill" and not r["enough"] for r in p["by_setup"])
    assert "error" in server.note_my_trade("nope", setup="x")
    assert "time zone" in server.import_my_trades("webull", path=__file__)["error"]
    assert "error" in server.import_my_trades("webull")


def test_page_routes_import_note_forget_and_refuse_other_sites():
    code, r = _post("/api/mytrades/import", {"broker": "fills", "text": CSV, "name": "t.csv"})
    assert code == 200 and r["round_trips"] == 1
    got = json.loads(urlopen(view.ensure_server() + "/api/mytrades").read())
    assert got["total"] == 1 and got["patterns"]["all"]["total_usd"] == 3.0 and "feeling" in got["choices"]
    tid = got["trades"][0]["trade_id"]
    code, t = _post("/api/mytrades/note", {"trade_id": tid, "setup": "breakout", "stop": 99, "note": "",
                                            "checklist": {"feeling": "calm", "risk": ""}})
    assert code == 200 and t["r"] == 3.0 and t["checklist"] == {"feeling": "calm"}
    code, t = _post("/api/mytrades/note", {"trade_id": tid, "stop": 101})
    assert code == 400 and "below" in t["error"]
    assert _post("/api/mytrades/import", {"broker": "fills", "text": CSV}, {"Content-Type": "text/plain"})[0] == 403
    assert _post("/api/mytrades/forget", {"source": "fills file t.csv"},
                 {"Content-Type": "application/json", "Host": "evil.example"})[0] == 403
    assert _post("/api/mytrades/forget", {"source": "fills file t.csv"})[1]["removed"] == 1
    assert journal.load("my_trades") == [] and len(journal.load("trade_notes")) == 1      # the note stays


def test_studio_has_the_my_trades_tab_at_phone_width():
    html = (WEB / "studio.html").read_text()
    js = (WEB / "mytrades.js").read_text()
    assert '["mytrades", "My trades", null]' in html and '<script src="/mytrades.js">' in html
    assert b"mytradesShell" in urlopen(view.ensure_server() + "/mytrades.js").read()
    assert "@media (max-width: 600px)" in js and 'class="trades"' in js and "var(--" in js     # phone + themes
    assert "Coach" not in js and "coach" not in js.lower()                                  # no paid parts here
    for bad in ("submit_order", "place_", "should ", "revenge", "habit"):
        assert bad not in js, bad


def test_dollars_always_show_cents():
    js = (WEB / "mytrades.js").read_text()
    usd = next(line for line in js.splitlines() if "const usd = " in line)
    assert "minimumFractionDigits: 2" in usd and "maximumFractionDigits: 2" in usd          # "$764.40", not "$764.4"
    px = next(line for line in js.splitlines() if "const px = " in line)
    assert "minimumFractionDigits: 2" in px                                                 # "$646.80", not "$646.8"


def test_hidden_rows_stay_hidden():
    js = (WEB / "mytrades.js").read_text()
    assert ".mt [hidden] { display: none !important; }" in js       # else .row's display: flex shows them anyway
    assert '$("mtFileRow").hidden = !file; $("mtTzRow").hidden = !(b === "webull" || b === "fills");' in js   # date-only files: no zone


def test_demo_is_one_click_from_get_started_and_the_empty_tab():
    js, start = (WEB / "mytrades.js").read_text(), (WEB / "start.js").read_text()
    assert "data-demo" in js and "window.tryMyTradesDemo" in js and 'broker: "demo"' in js
    assert 'id="gsdemo"' in start and "tryMyTradesDemo()" in start and "made-up" in start


def test_export_has_every_trade_with_notes_and_defuses_formulas():
    from urllib.request import urlopen
    from botscope import trade_import, trade_notes
    trade_import.from_demo()
    t = trade_import.trades()[0]
    trade_notes.note(t["trade_id"], setup="=HYPERLINK(1)", note="+made-up")
    text = urlopen(view.ensure_server() + "/api/mytrades/export.csv").read().decode()
    rows = text.strip().splitlines()
    assert rows[0].startswith("trade_id,source,symbol") and len(rows) == len(trade_import.trades()) + 1
    assert "'=hyperlink(1)" in text and "'+made-up" in text and "checklist_feeling" in rows[0]
    assert "Download my trades and notes (CSV)" in (WEB / "mytrades.js").read_text()


def test_calendar_draws_from_the_trades_and_says_what_colors_mean():
    js = (WEB / "mytrades.js").read_text()
    assert "function drawCalendar" in js and "drawCalendar();" in js and 'id="mtCal"' in js
    assert "+ made money, − lost" in js and "aria-label" in js                   # not color alone
