"""Where your own files live. In a developer checkout: right here (bots/, data/, gallery/), as always. In a Claude Code
plugin install: ~/.botscope (or BOTSCOPE_HOME), because Claude Code replaces the plugin's own folder on every update.
BOTSCOPE_BOTS_DIR / BOTSCOPE_JOURNAL_DIR (and the other BOTSCOPE_*_DIR settings) still win over both.

The first run in plugin mode copies anything found in the old in-plugin places (this folder, and older versions of
the plugin next to it) into ~/.botscope once: missing files only, the old copy is never deleted, nothing already in
~/.botscope is overwritten. A new ~/.botscope/bots gets the example bots; an existing one is never touched."""
from __future__ import annotations

import json
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import env

MARKER = ".copied-from-plugin-folder.json"
TOP_FILES = ("botscope.local.json", "botscope.private.json")   # your import paths, your private strategy list
_lock = threading.Lock()
_done = False


def home() -> Path:
    return Path(os.path.expanduser(os.getenv("BOTSCOPE_HOME") or "~/.botscope"))


def plugin_install(root: Path | None = None) -> bool:
    """True when this copy of BotScope is an installed Claude Code plugin: it sits under ~/.claude/plugins, or Claude
    Code started it as a plugin (CLAUDE_PLUGIN_ROOT is this folder) and it isn't a git checkout. A developer checkout,
    even one loaded with --plugin-dir, keeps its own folders. BOTSCOPE_PLUGIN_MODE=1/0 forces it."""
    v = os.getenv("BOTSCOPE_PLUGIN_MODE", "").lower()
    if v in ("1", "true", "on", "yes"):
        return True
    if v in ("0", "false", "off", "no"):
        return False
    root = (root or env.ROOT).resolve()
    plugins = (Path.home() / ".claude" / "plugins").resolve()
    if root == plugins or plugins in root.parents:
        return True
    pr = os.getenv("CLAUDE_PLUGIN_ROOT")
    return bool(pr) and Path(os.path.expanduser(pr)).resolve() == root and not (root / ".git").exists()


def place(dev: Path, rel: str) -> Path:
    """`dev` in a developer checkout, ~/.botscope/<rel> in a plugin install."""
    return home() / rel if plugin_install() else dev


def _pairs(old: Path) -> list[tuple[Path, str]]:
    """(old place, new place under ~/.botscope) for everything that holds your data. data/cache is left behind:
    it's downloaded prices, fetched again when needed."""
    out = [(old / "bots", "bots"), (old / "gallery", "gallery")] + [(old / f, f) for f in TOP_FILES]
    data = old / "data"
    if data.is_dir():
        out += [(p, p.name) for p in sorted(data.iterdir()) if p.name != "cache"]
    return out


def _copy_missing(src: Path, dest: Path) -> int:
    """Copy files from src that dest doesn't have yet. Never overwrites, never deletes. Skips .env files."""
    files = [src] if src.is_file() else sorted(p for p in src.rglob("*") if p.is_file()) if src.is_dir() else []
    n = 0
    for f in files:
        if f.name.startswith(".env") or "__pycache__" in f.parts or f.name == MARKER:
            continue
        to = dest if src.is_file() else dest / f.relative_to(src)
        if to.exists():
            continue
        to.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, to)
        n += 1
    return n


def _old_folders(root: Path) -> list[Path]:
    """Older plugin versions next to this one (Claude Code keeps each version in its own folder), newest first."""
    plugins = (Path.home() / ".claude" / "plugins").resolve()
    if plugins not in root.parents:
        return []
    try:
        sib = [d for d in root.parent.iterdir() if d.is_dir() and d.resolve() != root and (d / "botscope").is_dir()]
    except OSError:
        return []
    return sorted(sib, key=lambda d: d.stat().st_mtime, reverse=True)


def ensure() -> None:
    """Once per run in plugin mode: the one-time copy from the old places, then example bots for a new bots folder."""
    global _done
    if _done or not plugin_install():
        return
    with _lock:
        if _done:
            return
        h, root = home(), env.ROOT.resolve()
        new_bots = not (h / "bots").exists()
        if not (h / MARKER).exists():
            copied, sources = 0, []
            for old in [*_old_folders(root), root]:
                n = sum(_copy_missing(src, h / rel) for src, rel in _pairs(old) if not (old == root and rel == "bots"))
                if n:
                    copied += n
                    sources.append(str(old))
            h.mkdir(parents=True, exist_ok=True)
            (h / MARKER).write_text(json.dumps({"copied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                "files": copied, "from": sources}, indent=1))
        if new_bots and not os.getenv("BOTSCOPE_BOTS_DIR"):
            (h / "bots").mkdir(parents=True, exist_ok=True)
            for f in sorted((root / "bots").glob("*.py")):        # the examples (and anything else left in there)
                if not (h / "bots" / f.name).exists():
                    shutil.copy2(f, h / "bots" / f.name)
        _done = True


def status() -> dict:
    """For doctor: where your files are, and what the one-time copy did."""
    if not plugin_install():
        return {"plugin": False, "folder": str(env.ROOT), "detail": f"developer checkout: bots/ and data/ in {env.ROOT}"}
    h = home()
    detail = f"{h} (outside the plugin folder, so plugin updates keep it)"
    try:
        m = json.loads((h / MARKER).read_text())
    except (OSError, ValueError):
        m = None
    if m and m.get("files"):
        detail += (f". Copied {m['files']} file{'s' * (m['files'] != 1)} from the old plugin folder on "
                   f"{m['copied_at'][:10]}; the old copy was left as it was")
    return {"plugin": True, "folder": str(h), "detail": detail, "copied": m}
