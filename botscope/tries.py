"""Settings-tried counter: how many different settings were tested on the same untested days. The more tries on the
same days, the more the best one is luck: it says so in plain words. Saved on this computer only (journal)."""
from __future__ import annotations

import json

from . import journal


def note(bot_id: str, start: str, end: str, params: dict | None, filters: dict | None) -> dict:
    setting = json.dumps({"params": params or {}, "filters": filters or {}}, sort_keys=True)
    journal.upsert("tries", {"bot": bot_id, "from": start, "to": end, "setting": setting}, {})
    n = len({r["setting"] for r in journal.find("tries", bot=bot_id, **{"from": start, "to": end})})
    out = {"settings_tried_on_these_days": n}
    if n > 1:
        out["tries_note"] = (f"{n} different settings tested on these same untested days. Picking the best of them "
                             f"turns these days into tuned days for it: test the winner on other days first.")
    return out
