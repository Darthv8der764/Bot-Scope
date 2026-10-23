"""Devil's advocate: a small security tester for your BotScope setup. It PROBES, it never breaks anything.

Every probe runs on copies or in a throwaway sandbox (a temporary journal), and never sends an order. If a probe gets
in, the finding says so plainly ("I could've taken out the whole system, here's how") and, where a safe fix exists,
fixes it at once and saves how to undo it (undo_fix). Fixes only ever: tighten a file's permissions, add a line to
.gitignore, or switch STOP on / tighten a safety setting. Code problems are reported with how to fix them.
Not financial advice.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from . import backtest, data, guard, journal, loader, settings
from .bot import BarData
from .data import ET
from .env import ROOT, _env_file

KEY_RE = re.compile(r"\b(?:PK|AK)[A-Z0-9]{16,}\b")
SECRET_RE = re.compile(r"(?i)\b(?:secret|api_key|apikey|token|password)\b\s*[=:]\s*['\"]?[A-Za-z0-9/+_\-]{20,}")
DANGER = {r"\bsubprocess\b": "runs other programs", r"\bos\.system\b": "runs shell commands",
          r"\beval\(|\bexec\(": "runs code from text", r"\bshutil\.rmtree\b|\bos\.remove\b|\.unlink\(": "deletes files",
          r"\bsocket\b|\brequests\.|\burllib\b|\bhttpx\b": "talks to the internet",
          r"open\([^)]*['\"][wa]": "writes files", r"\b__import__\b|\bimportlib\b": "loads hidden code",
          r"\.env\b|ALPACA_SECRET|alpaca_keys": "reads your keys"}


def _finding(probe: str, result: str, what: str, how: str = "", fix: str = "", undo_id: str | None = None) -> dict:
    out = {"probe": probe, "result": result, "what": what}
    if how:
        out["how_i_got_in"] = how
    if fix:
        out["fixed"] = fix
    if undo_id:
        out["undo_id"] = undo_id
    return out


@contextmanager
def _sandbox():
    """A throwaway journal so probes never touch real settings or logs."""
    old = os.environ.get("BOTSCOPE_JOURNAL_DIR")
    with tempfile.TemporaryDirectory() as d:
        os.environ["BOTSCOPE_JOURNAL_DIR"] = d
        try:
            yield
        finally:
            if old is None:
                os.environ.pop("BOTSCOPE_JOURNAL_DIR", None)
            else:
                os.environ["BOTSCOPE_JOURNAL_DIR"] = old


def _git(*args) -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return ""


# ---------- probes ----------
def probe_secrets(fix: bool) -> list[dict]:
    out = []
    tracked = [ROOT / f for f in _git("ls-files").splitlines()]
    files = tracked + loader.bot_files()
    hits = []
    for f in files:
        if f.suffix in (".png", ".jpg", ".gif") or not f.is_file():
            continue
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if KEY_RE.search(line) or SECRET_RE.search(line):
                hits.append(f"{f.relative_to(ROOT) if f.is_relative_to(ROOT) else f}:{i}")
    if hits:
        out.append(_finding("leaked keys", "HOLE", f"key-like text in {len(hits)} place(s): {', '.join(hits[:5])}",
                            "anyone who sees these files (or the GitHub repo) could trade or read your account",
                            "not auto-fixed: move the key into .env, then make NEW keys at Alpaca (old ones are burned)"))
    else:
        out.append(_finding("leaked keys", "safe", f"no key-like text in {len(files)} tracked and bot files"))
    if (ROOT / ".git").exists():
        if ".env" in _git("ls-files").splitlines():
            out.append(_finding(".env in git", "HOLE", ".env is tracked by git",
                                "one push and your keys are public", "not auto-fixed: run git rm --cached .env, "
                                "then make new keys"))
        ignored = _git("check-ignore", ".env").strip() == ".env"
        if not ignored:
            fid = None
            if fix:
                gi = ROOT / ".gitignore"
                with gi.open("a") as fh:
                    fh.write("\n.env\n")
                fid = journal.add("security_fixes", {"kind": "gitignore_line", "path": str(gi), "line": ".env"})["id"]
            out.append(_finding(".env ignored", "HOLE", ".env is not in .gitignore",
                                "a 'git add .' would have put your keys in the repo",
                                "added .env to .gitignore" if fix else "", fid))
        else:
            out.append(_finding(".env ignored", "safe", ".env is ignored by git"))
        if ".env" in _git("log", "--all", "--name-only", "--format=").split():
            out.append(_finding(".env in history", "HOLE", "an old commit contains .env",
                                "the keys are still in the git history even if the file is gone now",
                                "not auto-fixed: make new keys at Alpaca; rewriting history needs care"))
    return out


def probe_env_permissions(fix: bool) -> list[dict]:
    f = _env_file()
    if not f.is_file():
        return [_finding("key file permissions", "safe", "no .env file found to check")]
    mode = stat.S_IMODE(f.stat().st_mode)
    if mode & 0o077:
        fid = None
        if fix:
            fid = journal.add("security_fixes", {"kind": "chmod", "path": str(f), "old_mode": mode})["id"]
            f.chmod(0o600)
        return [_finding("key file permissions", "HOLE", f"your key file can be read by other users (mode {mode:o})",
                         "any other account or app on this computer could read your Alpaca keys",
                         "set to owner-only (600)" if fix else "", fid)]
    return [_finding("key file permissions", "safe", f"key file is owner-only ({mode:o})")]


def probe_live_lock(fix: bool) -> list[dict]:
    """Try to get a live order past the guard in a sandbox. Never sends anything."""
    order = {"symbol": "SPY", "side": "buy", "qty": "1", "limit_price": "500"}
    attempts, notes = [], []
    if guard.live_switch_on():
        notes.append(_finding("live switch", "warning", "the live-money switch is ON in your .env",
                              "", "left on: you turned it on. Bots still need to graduate, and every order asks"))
    old_live = os.environ.get("BOTSCOPE_LIVE_TRADING")
    try:
        with _sandbox():
            os.environ["BOTSCOPE_LIVE_TRADING"] = "0"
            attempts.append(("live order with the switch off", guard.check_order(order, mode="live"), "deny"))
            os.environ["BOTSCOPE_LIVE_TRADING"] = "1"
            attempts.append(("bot order from a bot that never graduated",
                             guard.check_order(order, bot="first_hour_breakout", mode="live"), "deny"))
            attempts.append(("$50,000 order", guard.check_order({**order, "qty": "100"}, mode="live"), "deny"))
            attempts.append(("market order with no size", guard.check_order({"symbol": "SPY", "side": "buy", "qty": "500"},
                                                                             mode="live"), "deny"))
            attempts.append(("small order with everything on", guard.check_order(order, mode="live"), "ask"))
            settings.change(stopped=True)
            attempts.append(("any order during STOP", guard.check_order(order, mode="paper"), "deny"))
    finally:
        if old_live is None:
            os.environ.pop("BOTSCOPE_LIVE_TRADING", None)
        else:
            os.environ["BOTSCOPE_LIVE_TRADING"] = old_live
    got_in = [(name, d) for name, d, want in attempts if d["decision"] != want and want == "deny"]
    no_ask = [(name, d) for name, d, want in attempts if want == "ask" and d["decision"] == "allow"]
    holes = got_in + no_ask
    if not holes:
        return notes + [_finding("live-trading lock", "safe", f"{len(attempts)} ways in tried, all blocked or asked")]
    fid = None
    if fix:
        s = settings.load()
        fid = journal.add("security_fixes", {"kind": "setting", "old": {"stopped": s["stopped"]}})["id"]
        settings.change(stopped=True)
    names = "; ".join(f"{n} -> {d['decision']}" for n, d in holes)
    return notes + [_finding("live-trading lock", "HOLE", f"the guard let through: {names}",
                     "a live order could have gone out without your yes", "turned STOP on (blocks every order) until "
                     "the guard is fixed" if fix else "", fid)]


def probe_runaway(fix: bool) -> list[dict]:
    out = []
    order = {"symbol": "SPY", "side": "buy", "qty": "1", "limit_price": "1"}
    with _sandbox():
        settings.change(max_orders_per_day=5)
        for _ in range(5):
            guard.record(order, guard.check_order(order, mode="paper"), "devil's advocate")
        d = guard.check_order(order, mode="paper")
    if d["decision"] != "deny":
        out.append(_finding("runaway orders", "HOLE", "a 6th order went through with a limit of 5",
                            "a bot stuck in a loop could fire thousands of orders",
                            "not auto-fixed: the brake in guard.py is broken"))
    else:
        out.append(_finding("runaway orders", "safe", "the daily order brake stopped order 6 of 5"))
    s = settings.load()
    if s["max_orders_per_day"] > 200:
        fid = None
        if fix:
            fid = journal.add("security_fixes", {"kind": "setting", "old": {"max_orders_per_day": s["max_orders_per_day"]}})["id"]
            settings.change(max_orders_per_day=20)
        out.append(_finding("order brake setting", "HOLE", f"max_orders_per_day is {s['max_orders_per_day']}",
                            "the brake is set so high it would not stop a runaway bot",
                            "set back to 20" if fix else "", fid))
    if s["max_order_usd"] > 10_000:
        out.append(_finding("size cap setting", "warning", f"the live size cap is ${s['max_order_usd']:,.0f}",
                            "", "left as you set it; lower it with care"))
    return out


def _bad_bars():
    t0 = datetime(2026, 9, 1, 9, 30, tzinfo=ET)
    good = [BarData(t0 + timedelta(minutes=i), 100, 100.2, 99.8, 100.1, 1000) for i in range(60)]
    nan = float("nan")
    return good[30:] + [BarData(t0 + timedelta(minutes=5), nan, nan, nan, nan, 0),
                        BarData(t0 + timedelta(minutes=6), 0, 0, 0, 0, 0),
                        BarData(t0 + timedelta(minutes=7), 100, 99, 101, 100, 1),
                        good[8]] + good[:30]


def probe_bad_data(fix: bool) -> list[dict]:
    bot = loader.get("first_hour_breakout")() if "first_hour_breakout" in loader.load_all()[0] else None
    if bot is None:
        return [_finding("bad data", "warning", "no example bot to test bad data with")]
    try:
        trades, _, probs = backtest.run_window(bot, ["TEST"], datetime(2026, 9, 1).date(), datetime(2026, 9, 1).date(),
                                               fetch=lambda *a: _bad_bars())
        weird = [t for t in trades if t.r != t.r or abs(t.r) > 50]
        if weird:
            return [_finding("bad data", "HOLE", "broken bars produced impossible results",
                             "one bad price from a data feed could make a bot look great or trade wildly",
                             "not auto-fixed: data.clean() is not catching it")]
        return [_finding("bad data", "safe", "NaN, zero, upside-down and duplicate bars were dropped: "
                         + "; ".join(p.split(": ", 1)[-1] for p in probs[:4]))]
    except Exception as e:
        return [_finding("bad data", "HOLE", f"broken bars crashed the backtester ({type(e).__name__}: {e})",
                         "one bad price from a data feed could stop every bot mid-day",
                         "not auto-fixed: clean the bars before the bot sees them (data.clean)")]


def probe_local_page(fix: bool) -> list[dict]:
    from . import view

    class Fake:
        def __init__(self, host, origin=None):
            self.headers = {"Host": host, **({"Origin": origin} if origin else {})}
            self.server = type("S", (), {"server_address": ("127.0.0.1", 8765)})()

    tries = [("a website pretending to be localhost (DNS rebinding)", Fake("evil.example:8765")),
             ("another website posting to the page (CSRF)", Fake("127.0.0.1:8765", "https://evil.example"))]
    got_in = [n for n, f in tries if view._Handler._host_ok(f)]
    out = []
    if got_in or view.HOST != "127.0.0.1":
        out.append(_finding("chart page", "HOLE", "the local page answered: " + ", ".join(got_in or ["the whole network"]),
                            "a web page you visit could veto trades or read your journal",
                            "not auto-fixed: the Host/Origin check in view.py is broken"))
    else:
        out.append(_finding("chart page", "safe", "only answers this computer; other websites are refused"))
    return out


def probe_bot_code(fix: bool) -> list[dict]:
    out = []
    for f in loader.bot_files():
        text = f.read_text(errors="ignore")
        found = sorted({why for pat, why in DANGER.items() if re.search(pat, text)})
        if found:
            out.append(_finding(f"bot file {f.name}", "warning", f"this bot {', '.join(found)}",
                                "bots are Python: BotScope runs them with your permissions, so a downloaded bot "
                                "could do this to your computer", "not auto-fixed: read the file before running it"))
    if not out:
        out.append(_finding("bot files", "safe", "no bot runs programs, deletes files, goes online or reads keys"))
    return out


def probe_no_order_tools(fix: bool) -> list[dict]:
    src = (Path(__file__).with_name("server.py")).read_text()
    if re.search(r"submit_order|place_.*order\(|TradingClient\(.*\)\.submit", src):
        return [_finding("MCP tools", "HOLE", "a BotScope tool can place orders directly",
                         "Claude could trade without going through the guard",
                         "not auto-fixed: route it through guard.check_order")]
    return [_finding("MCP tools", "safe", "no BotScope tool places orders")]


PROBES = [probe_secrets, probe_env_permissions, probe_live_lock, probe_runaway, probe_bad_data, probe_local_page,
          probe_bot_code, probe_no_order_tools]


def run(fix: bool = True) -> dict:
    findings = []
    for p in PROBES:
        try:
            findings += p(fix)
        except Exception as e:      # a probe that breaks is reported, never fatal
            findings.append(_finding(p.__name__.replace("probe_", ""), "warning", f"probe failed: {e}"))
    holes = [f for f in findings if f["result"] == "HOLE"]
    head = ("All clear: every probe was blocked." if not holes else
            f"I could've taken out the whole system: {len(holes)} hole(s). Here's how"
            + (", and what I fixed." if fix and any(f.get("fixed") for f in holes) else "."))
    return {"headline": head, "holes": len(holes), "warnings": sum(f["result"] == "warning" for f in findings),
            "findings": findings,
            "undo": "Every automatic fix has an undo_id; undo_fix(undo_id) puts it back.",
            "note": "Probes ran on copies and a throwaway sandbox. Nothing was traded or deleted."}


def undo_fix(fix_id: str) -> dict:
    rows = [r for r in journal.load("security_fixes") if r["id"] == fix_id]
    if not rows:
        raise ValueError(f"no fix {fix_id!r}")
    r = rows[0]
    if r["kind"] == "chmod":
        Path(r["path"]).chmod(r["old_mode"])
    elif r["kind"] == "gitignore_line":
        p = Path(r["path"])
        lines = p.read_text().splitlines()
        idx = max(i for i, x in enumerate(lines) if x.strip() == r["line"])
        del lines[idx]
        p.write_text("\n".join(lines).rstrip("\n") + "\n")
    elif r["kind"] == "setting":
        settings.change(**r["old"])
    journal.remove("security_fixes", fix_id)
    return {"undone": fix_id, "kind": r["kind"]}
