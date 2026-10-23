"""Doctor: is this setup ready? Checks keys (present or not, never their values), where the .env was found, optional
keys, bots, the page port, STOP and the live lock. Reads only; changes nothing."""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

from . import env, loader, settings, userdata
from .market_data import _http

PURPOSE = ("BotScope gives you stock information for your own personal trading decisions. You can also use it with paper trading. It never places real orders for you and isn't financial advice.")


def _port_free() -> int | None:
    from .view import FIRST_PORT, HOST
    for port in range(FIRST_PORT, FIRST_PORT + 20):
        with socket.socket() as s:
            if s.connect_ex((HOST, port)) != 0:
                return port
    return None


def _claude_sees_botscope(home: Path | None = None, cwd: Path | None = None) -> str | None:
    """Where Claude Code registers the botscope MCP server, or None. Reads server NAMES only, never their settings."""
    home, cwd = home or Path.home(), cwd or Path.cwd()

    def names(f: Path, *keys) -> set:
        try:
            d = json.loads(f.read_text())
        except (OSError, ValueError):
            return set()
        for k in keys:
            d = d.get(k, {}) if isinstance(d, dict) else {}
        return set(d) if isinstance(d, dict) else set()

    if "botscope" in names(home / ".claude.json", "mcpServers"):
        return "~/.claude.json (all projects)"
    try:
        projects = json.loads((home / ".claude.json").read_text()).get("projects", {})
    except (OSError, ValueError, AttributeError):
        projects = {}
    for d in (cwd, *cwd.parents):
        if "botscope" in names(d / ".mcp.json", "mcpServers"):
            return str(d / ".mcp.json")
        if isinstance(projects.get(str(d)), dict) and "botscope" in (projects[str(d)].get("mcpServers") or {}):
            return f"~/.claude.json (project {d.name})"
    if any(k.split("@")[0] == "botscope" for k in names(home / ".claude" / "settings.json", "enabledPlugins")):
        return "the botscope plugin"
    return None


HOOKS = {"botscope-guard": "Order guard hook", "botscope.checkpoints": "Auto-checkpoint hook"}


def _hooks_set(home: Path | None = None, cwd: Path | None = None) -> dict[str, str | None]:
    """Where each BotScope hook is set up in Claude Code (the plugin brings both), or None. Reads hook commands only."""
    home, cwd = home or Path.home(), cwd or Path.cwd()
    if _claude_sees_botscope(home, cwd) == "the botscope plugin":
        return {h: "the botscope plugin" for h in HOOKS}
    files = [home / ".claude" / n for n in ("settings.json", "settings.local.json")]
    files += [d / ".claude" / n for d in (cwd, *cwd.parents) for n in ("settings.json", "settings.local.json")]
    found: dict[str, str | None] = {h: None for h in HOOKS}
    for f in files:
        try:
            hooks = json.loads(f.read_text()).get("hooks", {}).get("PreToolUse", [])
            cmds = [h.get("command", "") for g in hooks for h in g.get("hooks", [])]
        except (OSError, ValueError, AttributeError):
            continue
        for h in HOOKS:
            if found[h] is None and any(h in c for c in cmds):
                found[h] = str(f).replace(str(home), "~", 1)
    return found


def _broken_settings(home: Path | None = None, cwd: Path | None = None) -> list[str]:
    """Claude Code settings files that don't read as JSON (Claude Code may skip them, hooks included).
    Says the file and line only, never what's in it."""
    home, cwd = home or Path.home(), cwd or Path.cwd()
    files = [home / ".claude" / n for n in ("settings.json", "settings.local.json")]
    files += [d / ".claude" / n for d in (cwd, *cwd.parents) for n in ("settings.json", "settings.local.json")]
    out = []
    for f in dict.fromkeys(files):
        try:
            json.loads(f.read_text())
        except OSError:
            continue
        except ValueError as e:
            out.append(f"{str(f).replace(str(home), '~', 1)} (line {getattr(e, 'lineno', '?')})")
    return out


def check(via_mcp: bool = False) -> dict:
    rows = []
    add = lambda what, ok, detail, fix="": rows.append({"check": what, "ok": ok, "detail": detail,  # noqa: E731
                                                        "fix": "" if ok else fix})
    add("Python", sys.version_info >= (3, 10), sys.version.split()[0], "needs Python 3.10+ (uv venv picks one)")
    f = env._env_file()
    from_env = bool(env.os.getenv("ALPACA_API_KEY"))
    add(".env file", f.is_file() or from_env, str(f) if f.is_file() else "keys come from the environment" if from_env
        else "none found",
        "open Studio's Get started tab: it saves your Alpaca PAPER keys in ~/.botscope/.env for you"
        if userdata.plugin_install() else "cp .env.example .env (or ~/.botscope/.env) and add your Alpaca PAPER keys")
    k, s = env.key("ALPACA_API_KEY"), env.key("ALPACA_SECRET_KEY")
    if k and s:
        paper = k.startswith("PK")
        add("Alpaca keys", paper, "set (paper key)" if paper else "set, but NOT a paper key (paper keys start PK)",
            "" if paper else "use paper keys: BotScope treats anything else as live and blocks it")
    else:
        add("Alpaca keys", False, "missing", "add ALPACA_API_KEY and ALPACA_SECRET_KEY (paper) to the .env above")
    where = userdata.status()
    add("Your files", True, where["detail"])
    from . import demo
    add("Data", True, ("DEMO DATA: made-up prices (no Alpaca keys found, or BOTSCOPE_DEMO=1). Every tool works; "
                       "results mean nothing about real markets. " + demo.HOW_TO_SWITCH) if demo.active()
        else "real data: Alpaca, your own keys (BOTSCOPE_DEMO=1 switches to made-up demo prices)")
    demo_dir = userdata.place(env.ROOT / "data" / "demo", "demo")
    if demo_dir.is_dir() and not demo.active():
        n = sum(1 for p in demo_dir.rglob("*") if p.is_file())
        add("Demo results (optional)", True, f"{n} file{'s' * (n != 1)} in {demo_dir} from demo mode (made-up prices), kept apart "
                                             "from your real journal; delete the folder any time")
    for name, use in (("FRED_API_KEY", "yield curve, economy, release dates"), ("FINNHUB_API_KEY", "earnings, analysts")):
        add(name + " (optional)", bool(env.key(name)), "set" if env.key(name) else f"not set: {use} stay empty",
            "" if env.key(name) else f"get one {_http.WHERE[name]}")
    from . import alerts
    on = [n for n, ok in alerts.channels().items() if ok]
    add("Alert channels (optional)", bool(on), ", ".join(on) + " on" if on else "none on: phone alerts stay off",
        "" if on else "set NTFY_TOPIC, DISCORD_WEBHOOK_URL or TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in your .env "
                      "(only if you want alerts)")
    ua = env.key("SEC_USER_AGENT")
    real = bool(ua) and "example.com" not in ua
    add("SEC_USER_AGENT (optional)", real, "set" if real else "not set: insider trades + 8-Ks stay empty",
        "" if real else 'SEC_USER_AGENT="BotScope you@yourmail.com" (your own contact; only if you want it)')
    bots, errors = loader.load_all()
    add("Bots", bool(bots) and not errors, f"{len(bots)} load" + (f", {len(errors)} broken" if errors else ""),
        "; ".join(f"{e['file']}: {e['error']}" for e in errors)[:200])
    seen = "you're asking from Claude, so yes" if via_mcp else _claude_sees_botscope()
    add("Claude Code sees BotScope", bool(seen), seen or "not registered: Claude has no botscope tools",
        'in this folder: claude mcp add botscope -- "$PWD/.venv/bin/python" -m botscope.server '
        "(or install the plugin), then restart Claude Code. Free mode (botscope <tool>) works without it")
    hk = _hooks_set()
    add("Order guard hook (optional)", bool(hk["botscope-guard"]), hk["botscope-guard"] or
        "not set: Claude's Alpaca order tools aren't checked against STOP and your limits",
        "add the PreToolUse hook from the README's Safety section (or install the plugin)")
    add("Auto-checkpoint hook (optional)", bool(hk["botscope.checkpoints"]), hk["botscope.checkpoints"] or
        "not set: no automatic undo point before Claude edits a bot",
        "add the Edit|Write PreToolUse hook from the README (or install the plugin)")
    broken = _broken_settings()
    add("Claude settings files read (optional)", not broken, "all read" if not broken else "don't read: " + "; ".join(broken),
        "fix the JSON at that line (often two {...} blocks pasted one after the other)")
    from .backup import last_age_days
    age = last_age_days()
    add("Backup (optional)", age is not None and age <= 7,
        "never" if age is None else "today" if age == 0 else f"{age} day{'s' * (age != 1)} ago",
        "backup_my_data (one zip of your bots and journal, never keys)")
    port = _port_free()
    add("Page port", port is not None, f"{port} is free" if port else "8765-8784 all busy", "close old page servers")
    st = settings.load()
    add("STOP", not st.get("stopped"), "on: every order blocked" if st.get("stopped") else "off",
        "resume_trading when you're ready" if st.get("stopped") else "")
    from .guard import live_switch_on
    add("Live money", True, "unlocked in .env (still needs graduation + your yes)" if live_switch_on() else "locked (paper only)")
    bad = [r for r in rows if not r["ok"] and "optional" not in r["check"]
           and not r["check"].startswith("Claude")]       # free mode works without Claude
    if demo.active():                                     # missing keys don't block trying BotScope in demo mode
        bad = [r for r in bad if r["check"] not in (".env file", "Alpaca keys")]
        summary = ("ready in DEMO mode (made-up prices). " + demo.HOW_TO_SWITCH) if not bad else \
            f"{len(bad)} thing(s) to fix first (demo mode)"
        return {"ready": not bad, "demo": True, "summary": summary, "checks": rows, "purpose": PURPOSE,
                "note": "Key values are never shown. Nothing was changed."}
    return {"ready": not bad, "summary": "ready" if not bad else f"{len(bad)} thing(s) to fix first", "purpose": PURPOSE,
            "checks": rows, "note": "Key values are never shown. Nothing was changed."}
