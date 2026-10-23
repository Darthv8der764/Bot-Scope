"""Undo for bot changes: checkpoints of the bots folder, a before/after view, and restore.

A checkpoint is a copy of every bot file (data/checkpoints/<id>/, on this computer only). Restoring first saves a
checkpoint of how things are now, so a restore can itself be undone. Files added after the checkpoint are left in
place and listed (nothing is ever deleted). As a Claude Code hook (PreToolUse on Edit/Write), a checkpoint is saved
automatically before Claude changes a file in the bots folder (or bots_private/, your own git-ignored bots):
    .venv/bin/python -m botscope.checkpoints
"""
from __future__ import annotations

import difflib
import hashlib
import json
import shutil
import sys
from pathlib import Path

from . import journal, loader


def _store() -> Path:
    return journal.folder().parent / "checkpoints"


PRIV = "bots_private/"           # files from bots_private/ are kept under this prefix in a checkpoint


def _files(folder: Path) -> dict[str, str]:
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest()[:16] for f in sorted(folder.glob("*.py"))}


def _current() -> dict[str, str]:
    """Every bot file now: bots/ by name, bots_private/ (when there is one) as bots_private/<name>."""
    now = _files(loader.bots_dir())
    p = loader.private_dir()
    return now | ({PRIV + n: h for n, h in _files(p).items()} if p else {})


def _where(name: str) -> Path:
    """Where a checkpointed file lives now."""
    if name.startswith(PRIV):
        return (loader.private_dir() or loader.PRIVATE) / name[len(PRIV):]
    return loader.bots_dir() / name


def save(note: str = "") -> dict:
    """Copy every bot file. Skips (returns the last one) when nothing changed since the last checkpoint."""
    now = _current()
    rows = journal.load("checkpoints")
    if rows and rows[-1]["files"] == now:
        return rows[-1] | {"unchanged": True}
    row = journal.add("checkpoints", {"note": note[:300], "files": now})
    dest = _store() / row["id"]
    dest.mkdir(parents=True, exist_ok=True)
    for name in now:
        (dest / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_where(name), dest / name)
    return row


def list_all() -> dict:
    now = _current()
    out = []
    for r in reversed(journal.load("checkpoints")):
        changed = sorted(n for n in set(now) | set(r["files"]) if now.get(n) != r["files"].get(n))
        out.append({"id": r["id"], "saved_at": r["saved_at"], "note": r["note"], "files": len(r["files"]),
                    "changed_since": changed})
    return {"checkpoints": out, "folder": str(_store())}


def _get(cid: str) -> dict:
    for r in journal.load("checkpoints"):
        if r["id"] == cid:
            return r
    raise ValueError(f"no checkpoint {cid!r}; see list_checkpoints")


def changes(cid: str) -> dict:
    """Before (the checkpoint) / after (now) for every bot file that differs."""
    r = _get(cid)
    old_dir = _store() / cid
    diffs = []
    for name in sorted(set(r["files"]) | set(_current())):
        a = (old_dir / name).read_text().splitlines(keepends=True) if (old_dir / name).exists() else []
        b = _where(name).read_text().splitlines(keepends=True) if _where(name).exists() else []
        if a != b:
            diffs.append({"file": name, "diff": "".join(difflib.unified_diff(a, b, f"checkpoint/{name}", f"now/{name}"))})
    return {"checkpoint": cid, "note": r["note"], "changed_files": len(diffs), "diffs": diffs}


def restore(cid: str, confirm: bool = False) -> dict:
    r = _get(cid)
    ch = changes(cid)
    if not ch["changed_files"]:
        return {"restored": False, "note": "nothing to undo: the bots already match this checkpoint"}
    if not confirm:
        return {"question": f"Restore {ch['changed_files']} bot file(s) to checkpoint {cid} ({r['note'] or 'no note'})? "
                            "How things are now is saved first, so this can be undone too.",
                "files": [d["file"] for d in ch["diffs"]], "needs": "confirm=true"}
    safety = save(f"before restoring {cid}")
    old_dir = _store() / cid
    restored, extra = [], []
    for d in ch["diffs"]:
        if (old_dir / d["file"]).exists():
            _where(d["file"]).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old_dir / d["file"], _where(d["file"])); restored.append(d["file"])
        else:
            extra.append(d["file"])
    return {"restored": True, "files": restored, "left_in_place": extra, "undo_with": safety["id"],
            "note": "Files added after the checkpoint were left in place." if extra else ""}


def hook(event: dict) -> None:
    """PreToolUse on Edit/Write/MultiEdit: checkpoint before a bot file changes. Never blocks the edit."""
    path = (event.get("tool_input") or {}).get("file_path") or ""
    try:
        folders = [d.resolve() for d in [loader.bots_dir(), loader.private_dir()] if d]
        if path and Path(path).resolve().parent in folders:
            save(f"auto, before {event.get('tool_name', 'an edit')} of {Path(path).name}")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        hook(json.load(sys.stdin))
    except json.JSONDecodeError:
        pass
