"""Export the live paper log as a CSV for your own spreadsheet. Read only: it copies rows from this computer's
journal into a file on this computer. Every row is a live PAPER trade (not a backtest). Not financial advice."""
from __future__ import annotations

import csv
from pathlib import Path

from . import journal

COLUMNS = ["day", "bot", "symbol", "side", "r", "why_out", "trade_id", "period"]


def paper_csv(bot: str | None = None, path: str | None = None) -> dict:
    rows = journal.find("paper_results", **({"bot": bot} if bot else {}))
    rows = sorted(rows, key=lambda r: (r.get("day", ""), r.get("bot", ""), r.get("trade_id", "")))
    out = Path(path).expanduser() if path else journal.folder() / "exports" / "paper_results.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "period": "paper"})
    days = sorted({r["day"] for r in rows if r.get("day")})
    return {"path": str(out), "trades": len(rows), "bots": sorted({r["bot"] for r in rows}),
            "days": f"{days[0]} to {days[-1]}" if days else "none",
            "total_r": round(sum(r.get("r") or 0 for r in rows), 2),
            "note": "Live paper trades only (not a backtest), in R after the paper fills. Saved on this computer only."}
