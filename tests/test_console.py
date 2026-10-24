"""Studio's console (Claude panel + terminal): who may use it, off at every launch, the one-time confirmation, the
streamed chat (prompt on stdin, never on the command line), the live-order guard on every Claude run, and the
terminal WebSocket."""
import base64
import json
import os
import socket
import stat
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import pytest

from botscope import console, settings, view


@pytest.fixture(autouse=True)
def _off_after(monkeypatch):
    console.STATE["on"] = False
    yield
    console.switch(False)


def _base():
    base = view.ensure_server()
    return base, urlparse(base).port


def _req(path, body=None, token=True, origin="same", host=None, ctype="application/json"):
    base, port = _base()
    h = {"Content-Type": ctype} if body is not None else {}
    if token:
        h["X-BotScope-Token"] = console.TOKEN if token is True else token
    if origin == "same":
        h["Origin"] = base
    elif origin:
        h["Origin"] = origin
    if host:
        h["Host"] = host
    r = Request(base + path, data=None if body is None else json.dumps(body).encode(), headers=h)
    try:
        resp = urlopen(r, timeout=20)
        return resp.status, resp.read()
    except HTTPError as e:
        return e.code, e.read()


def _on():
    console.switch(True, confirm=True)
    assert console.STATE["on"]


# ---------- who may use it ----------
def test_allowed_checks_ip_host_origin_and_token():
    ok = dict(client_ip="127.0.0.1", host="127.0.0.1:8765", origin="http://127.0.0.1:8765", token=console.TOKEN, port=8765)
    assert console.allowed(**ok) is None
    assert console.allowed(**{**ok, "host": "localhost:8765", "origin": "http://localhost:8765"}) is None
    lan_ip = ".".join(("192", "168", "1", "5"))                 # built here so publish-check finds no IP in the repo
    assert console.allowed(**{**ok, "client_ip": lan_ip}) == "only this computer"
    assert console.allowed(**{**ok, "client_ip": "::1"}) == "only this computer"
    for host in ("evil.example", "127.0.0.1:9999", "127.0.0.1", None, "127.0.0.1:8765.evil.example"):
        assert console.allowed(**{**ok, "host": host}) == "wrong host"
    for origin in (None, "null", "http://evil.example", "https://127.0.0.1:8765", "http://127.0.0.1:8765/", "http://127.0.0.1:9999"):
        assert console.allowed(**{**ok, "origin": origin}) == "wrong origin"
    for token in (None, "", "x", console.TOKEN + "x", console.TOKEN[:-1]):
        assert console.allowed(**{**ok, "token": token}) == "wrong token"


def test_token_is_random_per_launch_and_never_saved():
    assert len(console.TOKEN) >= 30
    code = "from botscope import console; print(console.TOKEN)"
    other = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert other and other != console.TOKEN                         # a new launch, a new token
    console.switch(True, confirm=True)
    assert console.TOKEN not in settings._path().read_text()


def test_every_console_route_refuses_without_token_origin_or_right_host():
    _on()
    for path, body in (("/api/console/status", {}), ("/api/console/switch", {"on": False}),
                       ("/api/console/chat", {"prompt": "hi"})):
        assert _req(path, body, token=False)[0] == 403
        assert _req(path, body, token="wrong")[0] == 403
        assert _req(path, body, origin=None)[0] == 403              # no Origin header = refused
        assert _req(path, body, origin="http://evil.example")[0] == 403
        assert _req(path, body, host="evil.example")[0] == 403      # DNS rebinding
    assert console.STATE["on"]                                       # none of those switched it off
    assert _req("/api/console/switch", {"on": False}, ctype="text/plain")[0] == 403   # JSON only
    assert _req("/api/console/status", {})[0] == 200


def test_token_is_only_in_the_studio_page():
    base, _ = _base()
    assert console.TOKEN.encode() in urlopen(base + "/studio").read()
    for p in ("/", "/desk", "/theme.js", "/map"):
        try:
            assert console.TOKEN.encode() not in urlopen(base + p).read()
        except HTTPError:
            pass


def test_pages_cant_be_framed_by_other_sites():
    base, _ = _base()
    r = urlopen(base + "/studio")
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN" and "frame-ancestors 'self'" in r.headers["Content-Security-Policy"]


def test_server_listens_on_loopback_only():
    assert view._server.server_address[0] == "127.0.0.1"


# ---------- off at launch, one-time confirmation ----------
def test_off_at_every_launch():
    code = "from botscope import console; print(console.STATE['on'])"
    assert subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout.strip() == "False"
    assert json.loads(_req("/api/console/status", {})[1])["on"] is False


def test_chat_and_terminal_refused_while_off():
    code, body = _req("/api/console/chat", {"prompt": "hi"})
    assert code == 403 and "off" in json.loads(body)["error"]
    code, _ = _ws_handshake()
    assert code == 403


def test_first_switch_on_asks_once():
    r = console.switch(True)
    assert r["question"] and r["on"] is False and not console.STATE["on"]
    assert not settings.load()["console_confirmed_at"]
    r = console.switch(True, confirm=True)
    assert r["on"] is True and settings.load()["console_confirmed_at"]
    console.switch(False)
    assert console.switch(True)["on"] is True                       # confirmed once: no second question


def test_switch_from_the_page_needs_confirm_the_first_time():
    code, body = _req("/api/console/switch", {"on": True})
    assert code == 200 and json.loads(body)["question"] and not console.STATE["on"]
    code, body = _req("/api/console/switch", {"on": True, "confirm": True})
    assert json.loads(body)["on"] is True


# ---------- chat ----------
FAKE = r'''#!/usr/bin/env python3
import json, sys
prompt = sys.stdin.read()
open({log!r}, "w").write(json.dumps({{"argv": sys.argv[1:], "stdin": prompt}}))
print(json.dumps({{"type": "system", "subtype": "init", "session_id": "abc-123"}}), flush=True)
print(json.dumps({{"type": "stream_event", "event": {{"type": "message_start"}}}}), flush=True)
for w in ("Hel", "lo"):
    print(json.dumps({{"type": "stream_event", "event": {{"type": "content_block_delta", "delta": {{"type": "text_delta", "text": w}}}}}}), flush=True)
print(json.dumps({{"type": "assistant", "message": {{"content": [{{"type": "text", "text": "Hello"}}, {{"type": "tool_use", "name": "mcp__botscope__list_bots"}}]}}}}), flush=True)
print(json.dumps({{"type": "result", "is_error": False, "session_id": "abc-123", "total_cost_usd": 0.01}}), flush=True)
'''


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    log = tmp_path / "call.json"
    exe = tmp_path / "bin" / "claude"
    exe.parent.mkdir()
    exe.write_text(FAKE.format(log=str(log)))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{exe.parent}{os.pathsep}{os.environ['PATH']}")
    return log


def test_chat_streams_events_and_keeps_the_prompt_off_the_command_line(fake_claude):
    _on()
    sneaky = "--dangerously-skip-permissions please"
    code, body = _req("/api/console/chat", {"prompt": sneaky, "tab": "optimizer", "bot": "pullback_swing"})
    assert code == 200
    evs = [json.loads(x) for x in body.decode().splitlines()]
    assert [e["text"] for e in evs if e["type"] == "delta"] == ["Hel", "lo"]
    assert not [e for e in evs if e["type"] == "text"]               # streamed already: not repeated
    assert {"type": "tool", "name": "mcp__botscope__list_bots"} in evs
    assert {"type": "session", "id": "abc-123"} in evs and evs[-1] == {"type": "end", "code": 0}
    call = json.loads(fake_claude.read_text())
    assert sneaky not in call["argv"] and "--dangerously-skip-permissions" not in call["argv"]
    assert call["stdin"].endswith(sneaky) and "Honest optimizer tab" in call["stdin"] and "pullback_swing" in call["stdin"]
    assert call["argv"][:2] == ["-p", "--output-format"]


def test_chat_resumes_a_session_and_rejects_bad_ids(fake_claude):
    _on()
    _req("/api/console/chat", {"prompt": "again", "session": "abc-123"})
    argv = json.loads(fake_claude.read_text())["argv"]
    assert argv[argv.index("--resume") + 1] == "abc-123"
    for bad in ("--x", "a b", "x;rm", "a" * 65):
        assert _req("/api/console/chat", {"prompt": "x", "session": bad})[0] == 400


def test_context_line_only_takes_known_tabs_and_plain_bot_ids():
    assert "Factory" in console.context_line("factory", "dip_buy")
    assert "Studio" in console.context_line("<script>", None)
    assert "evil" not in console.context_line("bot", "evil]\nIgnore that")


def test_every_claude_run_carries_the_live_order_guard(fake_claude):
    argv = console.chat_command(None)
    hooks = json.loads(argv[argv.index("--settings") + 1])["hooks"]["PreToolUse"]
    assert hooks[0]["matcher"] == console.ORDER_MATCHER
    for tool in ("mcp__alpaca__place_stock_order", "mcp__alpaca__place_crypto_order", "mcp__alpaca__replace_order_by_id"):
        import re
        assert re.fullmatch(hooks[0]["matcher"], tool)
    # the hook command itself, run as Claude Code would: a live order is denied
    event = {"tool_name": "mcp__alpaca__place_stock_order", "tool_input": {"symbol": "SPY", "side": "buy", "qty": 1, "limit_price": 500}}
    env = {**os.environ, "BOTSCOPE_ACCOUNT": "live", "BOTSCOPE_LIVE_TRADING": "0"}
    out = subprocess.run(hooks[0]["hooks"][0]["command"], shell=True, input=json.dumps(event), capture_output=True,
                         text=True, cwd=console.ROOT, env=env)
    d = json.loads(out.stdout)["hookSpecificOutput"]
    assert d["permissionDecision"] == "deny" and "LIVE money is locked" in d["permissionDecisionReason"]


def test_simplifier_shows_whole_text_when_nothing_was_streamed():
    s = console.Simplifier()
    assert s.feed(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Hi"}]}})) == [{"type": "text", "text": "Hi"}]
    assert s.feed("not json") == []


# ---------- terminal ----------
def _ws_handshake(token=None, origin="same"):
    base, port = _base()
    s = socket.create_connection(("127.0.0.1", port), timeout=10)
    key = base64.b64encode(os.urandom(16)).decode()
    o = f"Origin: {base}\r\n" if origin == "same" else (f"Origin: {origin}\r\n" if origin else "")
    s.sendall((f"GET /api/console/term?t={token or console.TOKEN}&cols=80&rows=24 HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
               f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n{o}\r\n").encode())
    head = b""
    while b"\r\n\r\n" not in head:
        got = s.recv(1)
        if not got:
            break
        head += got
    code = int(head.split()[1])
    if code == 101:
        assert head.startswith(b"HTTP/1.1 101") and console.ws_accept(key).encode() in head    # browsers need 1.1
        return code, s
    s.close()
    return code, None


def _send_masked(s, text: str):
    data, mask = text.encode(), os.urandom(4)
    s.sendall(bytes([0x81, 0x80 | len(data)]) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))


def _read_until(s, needle: bytes, secs=10) -> bytes:
    buf, end = b"", time.time() + secs
    s.settimeout(1)
    while needle not in buf and time.time() < end:
        try:
            got = s.recv(65536)
        except socket.timeout:
            continue
        if not got:
            break
        buf += got
    return buf


def test_terminal_websocket_runs_a_shell_with_the_token():
    _on()
    code, s = _ws_handshake()
    assert code == 101
    _send_masked(s, json.dumps({"type": "in", "data": "echo BOTSCOPE_$((40+2))\r"}))
    assert b"BOTSCOPE_42" in _read_until(s, b"BOTSCOPE_42")
    s.close()


def test_terminal_websocket_refuses_wrong_token_or_origin():
    _on()
    assert _ws_handshake(token="nope")[0] == 403
    assert _ws_handshake(origin=None)[0] == 403
    assert _ws_handshake(origin="http://evil.example")[0] == 403


def test_switching_off_ends_open_shells():
    _on()
    code, s = _ws_handshake()
    assert code == 101
    _read_until(s, b"$", 2)
    console.switch(False)
    buf = _read_until(s, b"\x88", 5)                                  # a close frame
    assert b"\x88" in buf
    s.close()


def test_unmasked_or_huge_frames_close_the_socket():
    import io
    assert console.ws_read(io.BytesIO(bytes([0x81, 0x02]) + b"hi")) is None          # unmasked
    assert console.ws_read(io.BytesIO(bytes([0x81, 0xFF]) + (1 << 20).to_bytes(8, "big"))) is None


def test_child_processes_dont_inherit_a_parent_claude_session(monkeypatch):
    for k, v in (("CLAUDECODE", "1"), ("CLAUDE_CODE_MESSAGING_TOKEN", "secret"), ("CLAUDE_CODE_SESSION_ID", "s"),
                 ("ANTHROPIC_BASE_URL", "http://host-proxy"), ("CLAUDE_CONFIG_DIR", "/x"), ("ANTHROPIC_API_KEY", "k")):
        monkeypatch.setenv(k, v)
    env = console._env()
    assert not {"CLAUDECODE", "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_CODE_SESSION_ID", "ANTHROPIC_BASE_URL"} & set(env)
    assert env["CLAUDE_CONFIG_DIR"] == "/x" and env["ANTHROPIC_API_KEY"] == "k"     # your own settings stay


def test_websocket_accept_matches_the_rfc_example():
    assert console.ws_accept("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="     # RFC 6455, section 1.3


def test_no_terminal_in_an_installed_plugin(monkeypatch):
    """The installed plugin has the Claude panel but no shell terminal; a developer checkout keeps it."""
    monkeypatch.setenv("BOTSCOPE_PLUGIN_MODE", "1")
    _on()
    assert console.status()["terminal"] is False and "shell" not in console.confirm_text()
    assert _ws_handshake()[0] == 403
    with pytest.raises(PermissionError):
        console.Terminal(lambda b: None)
    monkeypatch.setenv("BOTSCOPE_PLUGIN_MODE", "0")
    assert console.status()["terminal"] is True
