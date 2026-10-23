"""Safety settings on this computer only (data/journal/settings.json, gitignored). Safe defaults: paper only,
nothing live, small size cap, a daily order limit. Every change is logged with the old value so it can be undone."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

from . import journal

DEFAULTS = {
    "live_bots": [],              # bots the user switched to LIVE money (each must pass the graduation test first)
    "max_order_usd": 1000.0,      # size cap per live order
    "max_orders_per_day": 20,     # runaway-order brake (paper and live)
    "stopped": False,             # STOP everything: every order is blocked until resumed
    "stopped_at": None,
    "loss_budget_r": None,        # weekly loss budget across all bots (R, paper results); None = off
    "console_confirmed_at": None,  # when Studio's Claude panel + terminal was first confirmed (it's still off at launch)
}
_lock = threading.Lock()


def _path():
    return journal.folder() / "settings.json"


def load() -> dict:
    p = _path()
    try:
        saved = json.loads(p.read_text()) if p.exists() else {}
    except json.JSONDecodeError:
        saved = {}
    return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}


def change(**updates) -> dict:
    """Set some settings; logs old -> new in journal 'settings_log' (for undo). Returns the new settings."""
    bad = set(updates) - set(DEFAULTS)
    if bad:
        raise ValueError(f"unknown settings {sorted(bad)}")
    with _lock:
        cur = load()
        old = {k: cur[k] for k in updates}
        cur.update(updates)
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(cur, indent=1))
        tmp.replace(p)
    journal.add("settings_log", {"old": old, "new": updates,
                                 "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return cur
