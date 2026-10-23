"""Backup: one zip of your bots and your journal (paper results, reports, checkpoints list, settings), saved on
this computer outside the BotScope folder, so a plugin update or a reinstall can't take them. Keys (.env files) are
never included. Nothing is uploaded."""
from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

from . import journal, loader


def backup(path: str | None = None) -> dict:
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    out = Path(path).expanduser() if path else Path.home() / ".botscope" / "backups" / f"botscope-{stamp}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    counts = {}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        folders = [("bots", loader.bots_dir())] + [("bots_private", p) for p in [loader.private_dir()] if p]
        for name, folder in (*folders, ("journal", journal.folder())):
            files = [f for f in sorted(folder.rglob("*")) if f.is_file() and not f.name.startswith(".env")
                     and "__pycache__" not in f.parts]
            for f in files:
                z.write(f, f"{name}/{f.relative_to(folder)}")
            counts[name] = len(files)
    journal.add("backups", {"path": str(out), "files": counts})     # after zipping, so it's not in this backup
    return {"path": str(out), "files": counts, "size_kb": round(out.stat().st_size / 1024, 1),
            "restore": "unzip it and copy bots/ (and bots_private/) and journal/ back (or point BOTSCOPE_BOTS_DIR / BOTSCOPE_JOURNAL_DIR "
                       "at the unzipped folders)",
            "note": "Saved on this computer only. Keys (.env) are never in a backup."}


def last_age_days(today=None) -> int | None:
    """Days since the newest backup that still exists on disk, or None (never, or the zip was moved)."""
    from datetime import date
    for r in reversed(journal.load("backups")):
        if Path(r["path"]).is_file():
            return ((today or date.today()) - journal.local_day(r["saved_at"])).days
    return None
