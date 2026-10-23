"""Your local notes about trades: vetoes, moved stops/targets, rule ideas and chart drawings. Plain JSON files on
this computer only (data/journal, gitignored; ~/.botscope/journal in a plugin install; or BOTSCOPE_JOURNAL_DIR). Nothing here is ever uploaded."""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .env import ROOT

_lock = threading.Lock()
FILES = ("vetoes", "trade_overrides", "rule_ideas", "drawings", "backtests", "paper_results", "reports", "luck",
         "settings_log", "orders_log", "preflight", "checkpoints", "security_fixes",
         "live_since", "weather_fit", "whatif", "tries", "quiz", "scam_overrides", "event_fit", "brief_pushed", "backups",
         "factory_runs", "robustness", "optimizer", "flights", "alert_rules", "questions", "loss_budget", "league", "checkup", "imported_trades", "phantom", "phantom_results", "auto_setup", "friends")


def folder() -> Path:
    """data/journal, or data/demo/journal in demo mode, so made-up demo results never mix with real ones (a report
    saved on demo prices would otherwise show on the nutrition label once real keys are added)."""
    if os.getenv("BOTSCOPE_JOURNAL_DIR"):
        return Path(os.path.expanduser(os.environ["BOTSCOPE_JOURNAL_DIR"]))
    from . import userdata
    from .env import demo_mode
    userdata.ensure()
    rel = "demo/journal" if demo_mode() else "journal"
    return userdata.place(ROOT / "data" / rel, rel)       # ~/.botscope/journal in a plugin install


def local_day(stamp: str):
    """The day a saved_at stamp falls on here. Stamps are UTC, so after 8 PM in New York the UTC date is already
    tomorrow; ages compare against date.today() (local), so they must use the local day too."""
    from datetime import date
    try:
        t = datetime.fromisoformat(stamp)
    except ValueError:
        return date.fromisoformat(stamp[:10])
    return t.astimezone().date() if t.tzinfo else t.date()


def _path(name: str) -> Path:
    assert name in FILES
    return folder() / f"{name}.json"


def load(name: str) -> list[dict]:
    p = _path(name)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return []


def _save(name: str, rows: list[dict]) -> None:
    p = _path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, indent=1, default=str))
    tmp.replace(p)


def add(name: str, row: dict) -> dict:
    row = {"id": uuid.uuid4().hex[:8], "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **row}
    with _lock:
        rows = load(name)
        rows.append(row)
        _save(name, rows)
    return row


def upsert(name: str, key: dict, row: dict) -> dict:
    """Replace the row whose fields match `key` (e.g. one override per trade), else add it."""
    with _lock:
        rows = [r for r in load(name) if any(r.get(k) != v for k, v in key.items())]
        new = {"id": uuid.uuid4().hex[:8], "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               **key, **row}
        rows.append(new)
        _save(name, rows)
    return new


def remove(name: str, row_id: str) -> bool:
    with _lock:
        rows = load(name)
        keep = [r for r in rows if r.get("id") != row_id]
        _save(name, keep)
    return len(keep) != len(rows)


def find(name: str, **match) -> list[dict]:
    return [r for r in load(name) if all(v is None or r.get(k) == v for k, v in match.items())]
