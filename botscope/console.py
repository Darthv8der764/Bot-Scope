"""Studio's console: a Claude chat panel (your own Claude Code, headless `claude -p`, your own login) and a terminal
(a shell on this computer, in a local pty), on every Studio tab. Off at every launch until you switch it on in
Studio's settings; the very first switch-on ever asks for a confirmation (remembered in settings.json).

Safety, on every console request and WebSocket: the page server listens on 127.0.0.1 only; the client must be
127.0.0.1; the Host must be exactly 127.0.0.1:<port> or localhost:<port>; the Origin must be exactly that origin
(missing = refused); and a random token made fresh at each launch (never saved, only written into the Studio page,
which other websites can't read) must match. Claude runs in the botscope folder with its normal permission rules,
plus BotScope's live-order guard attached as a hook on every run, so live orders stay blocked even if the plugin
isn't installed. Paper only: nothing here places an order.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone

from .env import ROOT

TOKEN = secrets.token_urlsafe(24)          # new every launch, never saved
STATE = {"on": False}                      # off at every launch, never saved
MAX_PROMPT = 8000
MAX_FRAME = 1 << 16
TABS = {"bot": "Bot view", "desk": "Desk", "preflight": "Pre-flight", "playground": "Rule playground",
        "map": "Family tree", "factory": "Factory", "compare": "Compare", "optimizer": "Honest optimizer",
        "imported": "My bots", "flight": "Flight sim", "tutorial": "Tutorial"}
ORDER_MATCHER = "mcp__alpaca__(place_.*_order|replace_order_by_id|exercise_options_position)"
_chat_lock = threading.Lock()              # one chat turn at a time
_live: set = set()                         # running chat processes and terminals, closed when switched off
_live_lock = threading.Lock()


# ---------- who may use it ----------
def allowed(client_ip: str, host: str | None, origin: str | None, token: str | None, port: int) -> str | None:
    """None when the request may use the console, else why not (for a 403)."""
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    if client_ip != "127.0.0.1":
        return "only this computer"
    if host not in hosts:
        return "wrong host"
    if origin not in {f"http://{h}" for h in hosts}:
        return "wrong origin"
    if not token or not hmac.compare_digest(token.encode(), TOKEN.encode()):
        return "wrong token"
    return None


def status() -> dict:
    from . import settings
    return {"on": STATE["on"], "claude_found": bool(shutil.which("claude")),
            "confirmed_before": bool(settings.load().get("console_confirmed_at")),
            "note": "Your own Claude Code and a shell on this computer. Off at every launch. Paper only: the "
                    "live-order guard is attached to every Claude run."}


CONFIRM_TEXT = ("Switch on the Claude panel and terminal? They run your own Claude Code and a shell on this computer, "
                "with the same access you have in a terminal. Only this page can use them (this computer, this "
                "port, a token made fresh at each launch), they switch off again at every launch, and the "
                "live-order guard stays on.")


def switch(on: bool, confirm: bool = False) -> dict:
    from . import settings
    if on and not settings.load().get("console_confirmed_at") and not confirm:
        return {**status(), "question": CONFIRM_TEXT, "needs": "confirm=true"}
    if on and not settings.load().get("console_confirmed_at"):
        settings.change(console_confirmed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    STATE["on"] = bool(on)
    if not on:
        close_all()
    return status()


def close_all() -> None:
    with _live_lock:
        items = list(_live)
    for x in items:
        try:
            x.close() if hasattr(x, "close") else _kill(x)
        except OSError:
            pass


def need_on() -> None:
    if not STATE["on"]:
        raise PermissionError("the Claude panel is off: switch it on in Studio settings first")


def _env() -> dict:
    """This process's environment minus anything inherited from a Claude session that started it (its session ids,
    messaging token and auth proxy): the panel's `claude` uses your own login, and the shell never sees them."""
    hosted = "CLAUDECODE" in os.environ or any(k.startswith("CLAUDE_CODE_") for k in os.environ)
    drop = lambda k: ((k.startswith("CLAUDE") and k != "CLAUDE_CONFIG_DIR")             # noqa: E731
                      or (hosted and k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN")))
    return {k: v for k, v in os.environ.items() if not drop(k)}


def _kill(p: subprocess.Popen) -> None:
    if p.poll() is None:
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            p.terminate()


def _hangup(p: subprocess.Popen) -> None:
    """End a shell and everything it started: SIGHUP (an interactive shell ignores SIGTERM), then SIGKILL."""
    def go():
        for sig, wait in ((signal.SIGHUP, 2), (signal.SIGKILL, 2)):
            if p.poll() is not None:
                return
            try:
                os.killpg(p.pid, sig)
            except (OSError, ProcessLookupError):
                return
            try:
                p.wait(timeout=wait)
            except subprocess.TimeoutExpired:
                pass
    threading.Thread(target=go, daemon=True).start()


# ---------- chat: claude -p, streamed ----------
def guard_settings() -> str:
    """Settings JSON for every Claude run: BotScope's live-order guard as a PreToolUse hook."""
    cmd = f"{shlex.quote(sys.executable)} -m botscope.guard"
    return json.dumps({"hooks": {"PreToolUse": [{"matcher": ORDER_MATCHER,
                                                 "hooks": [{"type": "command", "command": cmd}]}]}})


def chat_command(session: str | None) -> list[str]:
    """The prompt goes on stdin, never on the command line (a message like "--flag" can't become an option)."""
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("Claude Code isn't installed or isn't on the PATH (the `claude` command)")
    cmd = [exe, "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
           "--settings", guard_settings()]
    if session:
        if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z-]{0,63}", session):     # never starts with "-": not an option
            raise ValueError("bad session id")
        cmd += ["--resume", session]
    return cmd


def context_line(tab: str | None, bot: str | None) -> str:
    """What the user is looking at, so "this bot" or "these results" make sense. Only known tabs and plain bot ids."""
    parts = [f"the {TABS[tab]} tab" if tab in TABS else "Studio"]
    if bot and len(bot) <= 80 and all(c.isalnum() or c in "_-/." for c in bot):
        parts.append(f"bot {bot}")
    return f"[BotScope Studio: {', '.join(parts)}. Paper only.]\n"


def chat(prompt: str, session: str | None = None, tab: str | None = None, bot: str | None = None, write=None) -> None:
    """Run one turn and pass each simplified event to write(dict). If write fails (the page stopped reading or the
    Stop button was pressed), Claude is stopped too."""
    need_on()
    prompt = (prompt or "").strip()[:MAX_PROMPT]
    if not prompt:
        raise ValueError("type a message first")
    if not _chat_lock.acquire(blocking=False):
        raise RuntimeError("Claude is still answering the last message; wait or press Stop")
    try:
        cmd = chat_command(session)
        with tempfile.TemporaryFile() as err:
            p = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err,
                                 env=_env(), text=True, start_new_session=True)
            with _live_lock:
                _live.add(p)
            try:
                p.stdin.write(context_line(tab, bot) + prompt)
                p.stdin.close()
                s = Simplifier()
                for line in p.stdout:
                    for ev in s.feed(line):
                        write(ev)
                p.wait(timeout=10)
                if p.returncode:
                    err.seek(0)
                    tail = err.read()[-1500:].decode("utf-8", "replace").strip()
                    write({"type": "error", "text": tail or f"Claude Code stopped (exit code {p.returncode}). If it "
                                   "says it isn't logged in, open the Terminal tab, run `claude` once and log in."})
                write({"type": "end", "code": p.returncode})
            finally:
                _kill(p)
                with _live_lock:
                    _live.discard(p)
    finally:
        _chat_lock.release()


class Simplifier:
    """stream-json lines -> small events for the page: delta (text as it's typed), text (a whole block when it
    wasn't streamed), tool (name only), session, result."""

    def __init__(self):
        self.streamed = False

    def feed(self, line: str) -> list[dict]:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            return []
        t = e.get("type")
        if t == "system" and e.get("session_id"):
            return [{"type": "session", "id": e["session_id"]}]
        if t == "stream_event":
            ev = e.get("event") or {}
            if ev.get("type") == "message_start":
                self.streamed = False
            d = ev.get("delta") or {}
            if ev.get("type") == "content_block_delta" and d.get("type") == "text_delta" and d.get("text"):
                self.streamed = True
                return [{"type": "delta", "text": d["text"]}]
            return []
        if t == "assistant":
            out = []
            for c in (e.get("message") or {}).get("content", []):
                if c.get("type") == "text" and not self.streamed:
                    out.append({"type": "text", "text": c.get("text", "")})
                elif c.get("type") == "tool_use":
                    out.append({"type": "tool", "name": c.get("name", "")})
            return out
        if t == "result":
            return [{"type": "result", "error": bool(e.get("is_error")), "session": e.get("session_id"),
                     "cost_usd": e.get("total_cost_usd")}]
        return []


# ---------- terminal: a shell in a local pty, over a WebSocket ----------
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def ws_accept(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()


def ws_frame(payload: bytes, opcode: int = 2) -> bytes:
    n = len(payload)
    head = bytes([0x80 | opcode])
    if n < 126:
        head += bytes([n])
    elif n < 1 << 16:
        head += bytes([126]) + struct.pack(">H", n)
    else:
        head += bytes([127]) + struct.pack(">Q", n)
    return head + payload


def ws_read(rfile) -> tuple[int, bytes] | None:
    """One client frame (must be masked, at most 64 KB). None = closed or broken."""
    h = rfile.read(2)
    if len(h) < 2:
        return None
    op, masked, n = h[0] & 0x0F, h[1] & 0x80, h[1] & 0x7F
    if n == 126:
        n = struct.unpack(">H", rfile.read(2))[0]
    elif n == 127:
        n = struct.unpack(">Q", rfile.read(8))[0]
    if not masked or n > MAX_FRAME:
        return None
    mask = rfile.read(4)
    data = bytearray(rfile.read(n))
    if len(data) < n:
        return None
    for i in range(n):
        data[i] ^= mask[i % 4]
    return op, bytes(data)


class Terminal:
    """One shell per WebSocket. Closing the socket (or switching the console off) ends the shell."""

    def __init__(self, send, cols: int = 100, rows: int = 30):
        import pty
        need_on()
        self.send, self.closed = send, False
        self.fd, slave = pty.openpty()
        self.resize(cols, rows, slave)
        env = {**_env(), "TERM": "xterm-256color", "BOTSCOPE_CONSOLE": "1"}
        self.proc = subprocess.Popen([os.environ.get("SHELL") or "/bin/zsh", "-l"], stdin=slave, stdout=slave,
                                     stderr=slave, cwd=ROOT, env=env, start_new_session=True, close_fds=True)
        os.close(slave)
        with _live_lock:
            _live.add(self)
        threading.Thread(target=self._pump, daemon=True, name="botscope-pty").start()

    def resize(self, cols: int, rows: int, fd: int | None = None) -> None:
        import fcntl
        import termios
        rows, cols = max(5, min(int(rows), 200)), max(20, min(int(cols), 400))
        fcntl.ioctl(self.fd if fd is None else fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def _pump(self) -> None:
        """Reads the shell's output until it ends. Only this thread closes the pty (closing it while another thread
        reads it can hang on macOS)."""
        while True:
            try:
                got = os.read(self.fd, 16384)
            except OSError:
                break
            if not got:
                break
            try:
                if not self.closed:
                    self.send(got)
            except OSError:
                self.close()
        self.close()
        try:
            os.close(self.fd)
        except OSError:
            pass

    def write(self, data: str) -> None:
        if not STATE["on"]:
            self.close()
            return
        os.write(self.fd, data.encode()[:MAX_FRAME])

    def handle(self, msg: bytes) -> None:
        try:
            m = json.loads(msg)
        except json.JSONDecodeError:
            return
        if m.get("type") == "in":
            self.write(str(m.get("data", "")))
        elif m.get("type") == "resize":
            self.resize(m.get("cols", 100), m.get("rows", 30))

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        _hangup(self.proc)
        with _live_lock:
            _live.discard(self)
        try:
            self.send(None)            # tells the socket side to send a close frame
        except OSError:
            pass
