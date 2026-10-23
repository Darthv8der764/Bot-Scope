"""Honest optimizer: a heat map of two settings, the best spot, and how much luck is in it.

Every cell is a full honest report on the UNTESTED years up to a year ago (the factory's held-out rule), so the
best cell is picked without the last year. Then three honesty checks:
  1. Settings tried: the best of N cells looks better than it is; the note says by how much it beats the middle.
  2. Neighbors: a real edge is a plateau (the cells around the best also make money), not a lone island.
  3. Held-out year: the best cell and today's settings both run on the year no cell saw.
It never changes the bot: a better spot is a lead to test on paper (make_shadow), not a fix.
"""
from __future__ import annotations

from . import data, journal, loader, report, strategy_factory as sf, tries
from .bot import Bot

STEPS_DAILY = (0.6, 0.8, 1.0, 1.2, 1.4)
STEPS_INTRADAY = (0.75, 1.0, 1.25)
PROGRESS: dict = {}     # the run in progress, for Studio's progress line: {bot, settings, done, total}


def _values(v, steps) -> list:
    out = []
    for f in steps:
        x = max(1, round(v * f)) if isinstance(v, int) else float(f"{v * f:.3g}")    # 3 significant figures: 0.002 -> 0.0015
        if x not in out:
            out.append(x)
    return out


def _variant(cls, p: dict):
    look = cls.lookback_days
    if look:
        grow = max((p[k] / cls.params[k]) for k in p if isinstance(cls.params[k], (int, float)) and cls.params[k])
        look = int(look * max(grow, 1.0)) + 1
    return type(cls.__name__, (cls,), {"params": {**cls.params, **p}, "lookback_days": look,
                                       "source_file": cls.source_file})


def _once(fetch):
    """The same bars for every cell: each symbol and window is fetched once per run, not once per cell. Errors
    are never kept, so a symbol without data says so in every cell, as before."""
    fetch, seen = fetch or data.bars, {}

    def get(*args):
        if args not in seen:
            seen[args] = fetch(*args)
        return list(seen[args])
    return get


def number_settings(cls) -> list[str]:
    return [k for k, v in cls.params.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]


def pick_settings(cls, a: str | None, b: str | None) -> tuple[str, str]:
    nums = number_settings(cls)
    if a and a not in nums or b and b not in nums:
        raise ValueError(f"settings must be number settings of {cls.name}: {', '.join(nums)}")
    rest = [k for k in nums if k not in (a, b)]
    a = a or (rest.pop(0) if rest else None)
    b = b or (rest.pop(0) if rest else None)
    if not a or not b or a == b:
        raise ValueError(f"{cls.name} needs two different number settings to map (has: {', '.join(nums) or 'none'})")
    return a, b


def optimize(cls: type[Bot], a: str | None = None, b: str | None = None, symbols: list[str] | None = None,
             fetch=None, save: bool = True) -> dict:
    a, b = pick_settings(cls, a, b)
    steps = STEPS_DAILY if cls.timeframe == "1Day" else STEPS_INTRADAY
    va, vb = _values(cls.params[a], steps), _values(cls.params[b], steps)
    syms = [s.upper() for s in (symbols or cls.symbols)][:5]
    cut = sf.holdout_start()
    fetch = _once(fetch)
    grid = []
    PROGRESS.clear(); PROGRESS.update(bot=cls.name, settings=[a, b], done=0, total=len(va) * len(vb))
    try:
        _fill(cls, a, b, va, vb, syms, cut, fetch, grid)
        PROGRESS.update(done=PROGRESS["total"], now="held-out year")
        return _judge(cls, a, b, va, vb, syms, cut, fetch, grid, save)
    finally:
        PROGRESS.clear()


def _fill(cls, a, b, va, vb, syms, cut, fetch, grid) -> None:
    for x in va:
        row = []
        for y in vb:
            PROGRESS.update(now=f"{a}={x}, {b}={y}")
            u = report.full_report(_variant(cls, {a: x, b: y}), syms, fetch=fetch, crashes=False, save=False,
                                   today=cut)["untested"]
            row.append({a: x, b: y, "trades": u.get("trades", 0), "avg_r": u.get("avg_r"), "total_r": u.get("total_r")}
                       | ({"tight_stops": True} if report.tight_stops(u) else {}))
            PROGRESS["done"] = PROGRESS.get("done", 0) + 1
        grid.append(row)


def _judge(cls, a, b, va, vb, syms, cut, fetch, grid, save) -> dict:
    cells = [c for r in grid for c in r]
    tried = {}
    if save:       # each cell is a setting tried on these untested years; reruns with other settings add up
        first = next((w["from"] for w in report.year_windows(cls, cut) if w["period"] == "untested"), None)
        for c in cells if first else []:
            tried = tries.note(loader.bot_id(cls), str(first), str(cut), dict(cls.params) | {a: c[a], b: c[b]}, None)
    ok = [c for c in cells if c["trades"] >= 30 and c["avg_r"] is not None and not c.get("tight_stops")]
    base = {"bot": cls.name, "settings": [a, b], "values": {a: va, b: vb}, "grid": grid, "symbols": syms,
            "cells_tried": len(cells), "period": f"UNTESTED years up to {cut}; the year after is held out",
            "today": {a: cls.params[a], b: cls.params[b]}}
    if any(c.get("tight_stops") for c in cells):
        base["tight_stop_cells"] = (f"{sum(bool(c.get('tight_stops')) for c in cells)} cells had stops closer than "
                                    "their costs, so their R can't be trusted (marked ⚠, never picked as best; "
                                    "docs/when-r-lies-tight-stops.md)")
    if tried.get("settings_tried_on_these_days", 0) > len(cells):
        n = tried["settings_tried_on_these_days"]
        base["tries_across_runs"] = (f"{n} different settings have now been tried on these untested years across "
                                     f"optimizer runs (this run: {len(cells)}). The more tries, the more the best "
                                     "one is luck: the held-out year matters more than the heat map")
    if not ok:
        why = ("every cell with 30+ trades has R from stops closer than their costs, so no cell can be called best: "
               "widen the stop first (docs/when-r-lies-tight-stops.md)"
               if any(c.get("tight_stops") and c["trades"] >= 30 for c in cells)
               else "not enough trades in any cell (30+ needed) to say anything")
        out = base | {"verdict": why, "note": NOTE}
        return _save(cls, out, save)
    best = max(ok, key=lambda c: c["avg_r"])
    i, j = next((i, j) for i, r in enumerate(grid) for j, c in enumerate(r) if c is best)
    nb = [grid[i + di][j + dj] for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1))
          if 0 <= i + di < len(grid) and 0 <= j + dj < len(grid[0])]
    nb_ok = [c for c in nb if c["trades"] >= 30 and (c["avg_r"] or 0) > 0]
    plateau = len(nb_ok) == len(nb) and all(c["avg_r"] >= best["avg_r"] / 2 for c in nb_ok)
    mids = sorted(c["avg_r"] for c in ok)
    middle = mids[len(mids) // 2]
    cur = next((c for c in cells if c[a] == cls.params[a] and c[b] == cls.params[b]), None)
    ho_best = sf.held_out(_variant(cls, {a: best[a], b: best[b]}), {"symbols": syms}, fetch, cut)
    ho_now = sf.held_out(cls, {"symbols": syms}, fetch, cut)
    better_fresh = (ho_best["trades"] and ho_now["trades"] and (ho_best["avg_r"] or 0) > (ho_now["avg_r"] or 0))
    if best["avg_r"] <= 0:
        verdict = (f"no cell makes money after costs on the untested years (best {best['avg_r']:+.2f}R a trade): "
                   f"changing {a} and {b} doesn't fix this bot, so look at its rules, costs or symbols instead")
    elif best is cur:
        verdict = "today's settings are already the best cell; nothing to change"
    elif plateau and better_fresh and best["avg_r"] > 0:
        verdict = (f"lead to test: {a}={best[a]}, {b}={best[b]} sits on a plateau and also did better on the held-out "
                   "year. Test it on paper beside today's version (make_shadow), don't just switch")
    else:
        verdict = ("keep today's settings: the best cell " + ("is a lone island (its neighbors don't hold up)"
                   if not plateau else "didn't do better on the held-out year") + ", so it's probably luck")
    out = base | {
        "best": best, "current": cur, "middle_avg_r": middle,
        "luck_in_best": (f"best of {len(cells)} cells: {best['avg_r']:+.2f}R a trade vs {middle:+.2f}R for the middle "
                         f"cell. Picking the best of {len(cells)} on the same years flatters it, so expect part of that "
                         "gap to be luck"),
        "neighbors": {"cells": nb, "plateau": plateau,
                      "summary": f"{len(nb_ok)} of {len(nb)} neighbors make money" + (" (a plateau)" if plateau else
                                                                                    " (an island)")},
        "held_out": {"best": ho_best, "today": ho_now},
        "verdict": verdict, "note": NOTE}
    return _save(cls, out, save)


NOTE = ("Each cell is a full honest report on untested years (costs taken out). The bot file is never changed. "
        "Counts and R, not probabilities. Not financial advice.")


def _save(cls, out: dict, save: bool) -> dict:
    if save:
        journal.upsert("optimizer", {"bot": loader.bot_id(cls), "settings": out["settings"]},
                       {k: v for k, v in out.items() if k != "note"})
    return out


def markdown(out: dict) -> str:
    a, b = out["settings"]
    lines = [f"Rows: {a}. Columns: {b}. Cell = R a trade after costs (trades), untested years.", "",
             "| " + a + " \\ " + b + " | " + " | ".join(str(v) for v in out["values"][b]) + " |",
             "|---|" + "---|" * len(out["values"][b])]
    for row in out["grid"]:
        cells = []
        for c in row:
            mark = " ★" if (out.get("best") is c or (out.get("best") and c == out["best"])) \
                and (c["avg_r"] or 0) > 0 else ""                      # no star on a losing "best"
            mark += " ⚠" if c.get("tight_stops") else ""
            mark += " (today)" if c[a] == out["today"][a] and c[b] == out["today"][b] else ""
            cells.append(("–" if c["avg_r"] is None else f"{c['avg_r']:+.2f}R") + f" ({c['trades']}){mark}")
        lines.append(f"| {row[0][a]} | " + " | ".join(cells) + " |")
    if out.get("tight_stop_cells"):
        lines += ["", out["tight_stop_cells"] + "."]
    if out.get("tries_across_runs"):
        lines += ["", out["tries_across_runs"] + "."]
    if out.get("luck_in_best"):
        lines += ["", f"Luck in the best: {out['luck_in_best']}.", f"Neighbors: {out['neighbors']['summary']}."]
    ho = out.get("held_out") or {}
    if ho.get("best") and ho.get("today"):
        f = lambda h: f"{h['avg_r']:+.2f}R a trade over {h['trades']}" if h.get("trades") else "no trades"
        lines.append(f"Held-out {ho['today']['from']} to {ho['today']['to']}: best cell {f(ho['best'])}, "
                     f"today's settings {f(ho['today'])}.")
    if out.get("verdict"):
        lines += ["", f"**Verdict:** {out['verdict']}."]
    return "\n".join(lines)
