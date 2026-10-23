"""Project map: an Obsidian-style picture of BotScope itself, plus each bot's family tree.

- Project tab: one dot per module (size = lines), lines between modules that import each other, the MCP tools each
  module serves, and when it first appeared (from git), so the page can play a timelapse of the build.
- Bot family tab: one dot per change to a bot file (from git), with the commit message and the version string at
  that commit; the newest dot carries the latest results saved on this computer (untested trades, confidence).

Read-only: it reads the source files, `git log` and the local journal. Nothing is sent anywhere.
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

from . import confidence, journal, loader
from .env import ROOT

PKG = ROOT / "botscope"


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _first_added() -> dict[str, str]:
    """{path: ISO time of the commit that added it}."""
    out, when = {}, None
    for line in _git("log", "--reverse", "--diff-filter=A", "--name-only", "--format=@%aI").splitlines():
        if line.startswith("@"):
            when = line[1:]
        elif line.strip() and line not in out:
            out[line.strip()] = when
    return out


def _tools_by_module() -> dict[str, list[str]]:
    """Which module each MCP tool calls into (the `from . import x` / `x.` used inside the tool)."""
    src = (PKG / "server.py").read_text()
    out: dict[str, list[str]] = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and any(
                isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "tool" for d in node.decorator_list):
            body = ast.get_source_segment(src, node) or ""
            mods = [m for m in re.findall(r"\b(\w+)\.\w+", body.split('"""')[-1])
                    if (PKG / f"{m}.py").exists() and m not in ("loader", "server")]
            mod = next((m for m in mods if m != "view"), mods[0] if mods else "server")   # view = page helpers
            out.setdefault(mod, []).append(node.name)
    return out


def modules() -> dict:
    added = _first_added()
    tools = _tools_by_module()
    nodes, links = [], []
    for f in sorted(PKG.glob("*.py")):
        if f.name == "__init__.py":
            continue
        src = f.read_text()
        tree = ast.parse(src)
        doc = " ".join((ast.get_docstring(tree) or "").strip().split("\n\n")[0].split())   # first paragraph
        imports = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.level == 1:
                if n.module:
                    imports.add(n.module.split(".")[0])
                else:
                    imports |= {a.name for a in n.names}
        nodes.append({"id": f.stem, "doc": doc, "lines": src.count("\n") + 1,
                      "added": added.get(f"botscope/{f.name}"), "tools": tools.get(f.stem, [])})
        links += [{"source": f.stem, "target": i} for i in sorted(imports) if (PKG / f"{i}.py").exists() and i != f.stem]
    return {"nodes": nodes, "links": links}


def bot_family() -> list[dict]:
    bots, _ = loader.load_all()
    out = []
    for bid, cls in bots.items():
        path = Path(cls.source_file or Path(loader.bots_dir()) / f"{bid}.py")
        try:
            rel = path.resolve().relative_to(ROOT.resolve())
        except ValueError:
            rel = None
        versions = []
        if rel:
            for line in _git("log", "--reverse", "--format=%h%x09%aI%x09%s", "--", str(rel)).splitlines():
                h, when, msg = line.split("\t", 2)
                text = _git("show", f"{h}:{rel}")
                m = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.M)
                versions.append({"commit": h, "when": when, "change": msg, "version": m.group(1) if m else "?"})
        if not versions or versions[-1]["version"] != cls.version or _git("status", "--porcelain", "--", str(rel or "")):
            versions.append({"commit": "now", "when": None, "change": "current file (not committed yet)" if versions
                             else "current file", "version": cls.version})
        last = (journal.find("backtests", bot=bid) or [{}])[-1].get("untested") or {}
        conf = confidence.for_bot(bid)
        versions[-1] |= {"untested_trades": last.get("trades"), "untested_avg_r": last.get("avg_r"),
                         "confidence": conf["level"]}
        out.append({"id": bid, "name": cls.name, "status": cls.status, "timeframe": cls.timeframe,
                    "versions": versions})
    return out


def build() -> dict:
    return {"project": modules(), "bots": bot_family(),
            "commits": _git("rev-list", "--count", "HEAD").strip() or "0",
            "note": "Read from your own files and git history on this computer."}
