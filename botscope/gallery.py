"""Honest bot gallery: package one bot so it can be shared on GitHub WITH its nutrition label.

Writes a folder (default gallery/<bot>/, gitignored) with the bot's .py file, README.md (what it does, its rules,
the full nutrition label, tuned vs untested, data source, "not financial advice") and label.json. It never pushes,
never uploads, and never copies your journal, keys, trades or account. A bot can't be exported without a saved
honest report, and failed bots are labeled FAILED at the top. You review the folder and publish it yourself.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import date
from pathlib import Path

from . import label, loader
from .env import ROOT
from .userdata import place

OUT = place(ROOT / "gallery", "gallery")
_PERSONAL = re.compile(r"(PK|AK|SK)[A-Z0-9]{12,}|[\w.+-]+@[\w-]+\.[\w.]+|/Users/\w+|ALPACA_\w*KEY\s*=\s*\S+")


def readme(cls, lbl: dict) -> str:
    bot = cls()
    banner = ("> **FAILED its honest test.** Shared as a lesson, not a strategy.\n\n" if cls.status == "failed" else "")
    rules = "\n".join(f"- {r}" for r in getattr(cls, "rules", []) or [])
    tuned = (f"Settings were picked on {cls.tuned_on[0]} to {cls.tuned_on[1]} (TUNED: expect those days to look good). "
             "Every other day is UNTESTED, and the label below only counts those." if cls.tuned_on else
             "No tuning dates given: every day is treated as untested.")
    return f"""# {cls.name} v{cls.version}

{banner}{cls.description}

**Timeframe:** {cls.timeframe} · **Sides:** {cls.sides} · **Symbols:** {", ".join(bot.symbols)}

## Rules
{rules or "- See the code."}

## Honest numbers
{tuned}

{label.markdown(lbl)}

## How to check it yourself
1. Install BotScope, put your own free Alpaca **paper** keys in `.env`.
2. Copy `{loader.bot_id(cls)}.py` into `bots/`.
3. Ask Claude: "honest report for {cls.name}", or run `botscope honest_report {loader.bot_id(cls)}`.

Data: {lbl.get("data", "Alpaca SIP")}. Exported {date.today()} with BotScope. Paper trading only.
**Not financial advice.** Past results, after costs, are not a promise.
"""


def export(bot: str, out_dir: Path | None = None) -> dict:
    cls = loader.get(bot)
    bid = loader.bot_id(cls)
    lbl = label.build(bot)
    if any(r["label"] == "Untested trades" and r["value"] == label.MISSING for r in lbl["rows"]):
        raise ValueError(f"run honest_report for {cls.name} first: the gallery never shares a bot without its label")
    src = Path(cls.source_file)
    code = src.read_text()
    if _PERSONAL.search(code):
        raise ValueError(f"{src.name} looks like it holds a key, an email or a home-folder path; remove it first")
    dest = (out_dir or OUT) / bid
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest / f"{bid}.py")
    text = readme(cls, lbl)
    (dest / "README.md").write_text(text)
    (dest / "label.json").write_text(json.dumps({k: lbl[k] for k in ("bot", "version", "rows", "data", "note")}
                                                | {"confidence": lbl["confidence"].get("level")}, indent=1))
    return {"folder": str(dest), "files": sorted(p.name for p in dest.iterdir()), "status": cls.status,
            "next": "Read README.md first. Publishing is up to you: nothing was pushed or uploaded.",
            "note": "Only the bot file and its label were copied: no journal, trades, keys or account data."}
