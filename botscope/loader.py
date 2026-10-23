"""Find the user's bots: every Bot subclass in the .py files of BOTSCOPE_BOTS_DIR (default: botscope/bots, or ~/.botscope/bots in a plugin install).

In a developer checkout, bots_private/ (next to bots/, git-ignored) is read too: your own strategies live there, so
they are never committed and never reach a publish-check export, while the Studio and every tool see them as usual."""
from __future__ import annotations

import importlib.util
import inspect
import os
import re
from pathlib import Path

from .bot import Bot
from .env import ROOT


def bots_dir() -> Path:
    """BOTSCOPE_BOTS_DIR, else bots/ here (developer checkout), else ~/.botscope/bots (plugin install, see userdata)."""
    if os.getenv("BOTSCOPE_BOTS_DIR"):
        return Path(os.path.expanduser(os.environ["BOTSCOPE_BOTS_DIR"]))
    from . import userdata
    userdata.ensure()
    return userdata.place(ROOT / "bots", "bots")


PRIVATE = ROOT / "bots_private"


def private_dir() -> Path | None:
    """bots_private/ when it exists in a developer checkout; None in a plugin install or with BOTSCOPE_BOTS_DIR set
    (there, the bots folder is already your own)."""
    if os.getenv("BOTSCOPE_BOTS_DIR"):
        return None
    from . import userdata
    return PRIVATE if not userdata.plugin_install() and PRIVATE.is_dir() else None


def bot_files() -> list[Path]:
    """Every bot file: bots/ first, then bots_private/ when there is one."""
    dirs = [bots_dir()] + [d for d in [private_dir()] if d]
    return [f for d in dirs for f in sorted(d.glob("*.py")) if not f.name.startswith("_")]


def bot_id(cls) -> str:
    return re.sub(r"[^a-z0-9]+", "_", cls.name.lower()).strip("_")


def load_all() -> tuple[dict[str, type[Bot]], list[dict]]:
    """({bot_id: class}, [errors]). A file that fails to import is reported, not fatal."""
    found, errors = {}, []
    priv = private_dir()
    for f in bot_files():
        pkg = "botscope_private_bots" if priv and f.parent == priv else "botscope_user_bots"
        try:
            spec = importlib.util.spec_from_file_location(f"{pkg}.{f.stem}", f)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as e:
            errors.append({"file": f.name, "error": f"{type(e).__name__}: {e}"})
            continue
        for _, cls in inspect.getmembers(mod, inspect.isclass):
            if issubclass(cls, Bot) and cls is not Bot and cls.__module__ == mod.__name__:
                cls.source_file = str(f)          # where the class lives (make_shadow copies it)
                found[bot_id(cls)] = cls
    return found, errors


def is_mine(cls) -> bool:
    """Your own bot (not one of BotScope's example bots): anything in bots_private/, or any bot in your bots folder
    that isn't a shipped example (plugin installs keep the examples next to yours in ~/.botscope/bots)."""
    f = Path(getattr(cls, "source_file", "") or "")
    priv = private_dir()
    if priv and f.parent == priv:
        return True
    return f.parent == bots_dir() and f.parent != ROOT / "bots" and not (ROOT / "bots" / f.name).is_file()


def get(name: str) -> type[Bot]:
    """A bot by id or name. "factory/<run>/<id>" opens a strategy-factory candidate before it's adopted (read-only:
    the chart, label and reports can look at it; it stays out of the bots folder and the daily lists)."""
    if name.startswith("factory/"):
        m = re.fullmatch(r"factory/(\d{8,12})/([a-z0-9_]{1,80})", name)
        if not m:
            raise KeyError(f"{name!r} isn't a factory candidate name (factory/<run>/<id>)")
        from . import strategy_factory
        path = strategy_factory.factory_dir() / m.group(1) / f"{m.group(2)}.py"
        if not path.is_file():
            raise KeyError(f"no factory candidate {m.group(2)!r} in run {m.group(1)}")
        return strategy_factory.load_file(path)
    bots, _ = load_all()
    key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if key in bots:
        return bots[key]
    hits = [k for k in bots if key in k]
    if len(hits) == 1:
        return bots[hits[0]]
    raise KeyError(f"no bot named {name!r}; have: {', '.join(bots) or 'none'}")
