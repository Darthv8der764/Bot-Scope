"""Shadow mode: a new version of a bot runs beside the old one on paper, and an end-of-day scoreboard shows each
version's result. A bot joins its family by naming the bot it replaces: `shadows = "first_hour_breakout"`.

Every bot is already replayed on paper after the close (log_paper_results), so a shadow costs nothing extra and
never places an order. The scoreboard only compares days BOTH versions were tracked (from the newest version's first
paper result), so an older bot's longer history can't make it look better. Results in R, counts, and the confidence
level; never a win %. Not financial advice.
"""
from __future__ import annotations

from . import confidence, journal, loader


def families(bots: dict | None = None) -> dict[str, list[str]]:
    """{root bot id: [root, shadow, shadow-of-shadow, ...]} for every family with at least one shadow."""
    bots = bots if bots is not None else loader.load_all()[0]

    def root(b, seen=()):
        p = getattr(bots.get(b), "shadows", None)
        return b if not p or p not in bots or p in seen else root(p, seen + (b,))
    fam: dict[str, list[str]] = {}
    for b in bots:
        fam.setdefault(root(b), []).append(b)
    return {r: [r] + sorted(m for m in ms if m != r) for r, ms in fam.items() if len(ms) > 1}


def scoreboard(day: str | None = None, bots: dict | None = None) -> dict:
    bots = bots if bots is not None else loader.load_all()[0]
    fams = families(bots)
    if not fams:
        return {"families": [], "how": 'No shadows yet. Copy a bot file, give it a new name, change it, and add  shadows = "<old bot id>"  '
                                       "to the new class; both then run on paper and show up here."}
    rows = journal.load("paper_results")
    out = []
    for root, members in fams.items():
        mine = {m: [r for r in rows if r["bot"] == m] for m in members}
        starts = [min(r["day"] for r in rs) for rs in mine.values() if rs]
        since = max(starts) if len(starts) == len(members) else None
        last = day or max((r["day"] for rs in mine.values() for r in rs), default=None)
        board = []
        for m in members:
            both = [r for r in mine[m] if since and since <= r["day"] <= (last or r["day"])]
            today = [r["r"] for r in both if r["day"] == last]
            board.append({"bot": m, "name": bots[m].name, "version": bots[m].version,
                          "role": "original" if m == root else f"shadow of {bots[m].shadows}",
                          "day_r": round(sum(today), 2) if today else None, "day_trades": len(today),
                          "total_r": round(sum(r["r"] for r in both), 2), "trades": len(both),
                          "confidence": confidence.for_bot(m)["level"]})
        out.append({"family": root, "day": last, "compared_since": since, "versions": board,
                    "verdict": verdict(board, since)})
    return {"families": out, "note": "Paper only. Same days for every version (from the newest one's first paper "
                                     "result). Totals in R after costs. Not financial advice."}


def verdict(board: list[dict], since: str | None) -> str:
    if not since:
        return "waiting: every version needs at least one paper result before they can be compared"
    n = min(b["trades"] for b in board)
    if n < 20:
        return f"too early to pick: fewest trades is {n} (need 20+ each on the same days before the totals mean much)"
    best = max(board, key=lambda b: b["total_r"])
    return (f"{best['name']} v{best['version']} leads on the same days ({best['total_r']:+.2f}R over "
            f"{best['trades']} trades); check its confidence before switching")


def phone_line(day: str, bots: dict | None = None) -> str:
    """'Shadows today: ORB v1.0 -2.04R, v2.0 +0.40R' for the end-of-day alert; '' with no shadows or no trades."""
    parts = []
    for f in scoreboard(day, bots).get("families", []):
        if f["day"] != day or all(v["day_r"] is None for v in f["versions"]):
            continue
        vs = [f"v{v['version']} {v['day_r']:+.2f}R" if v["day_r"] is not None else f"v{v['version']} no trades"
              for v in f["versions"]]
        parts.append(f"{f['versions'][0]['name']}: " + ", ".join(vs))
    return ("Shadows today: " + "; ".join(parts)) if parts else ""
