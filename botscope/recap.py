"""Weekly recap: one shareable image of the week's paper results, honest numbers only.

Built from the live paper log on this computer (closed trades only) and each bot's last untested backtest, so every
number on the card is one BotScope actually measured. Results are in R (multiples of the risk), after costs; there
are no dollar amounts, no win streak bragging, and a small week says it's small. Not financial advice.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from html import escape

from . import journal, loader
from .env import ROOT

SMALL = 10
W, ROW_H = 640, 34
INK, MUTED, LINE, UP, DOWN, BG = "#1d1d1b", "#6b6b66", "#e3e2dd", "#1a9e6a", "#d64545", "#ffffff"


def week_of(day: date) -> tuple[date, date]:
    mon = day - timedelta(days=day.weekday())
    return mon, mon + timedelta(days=4)


def _names() -> dict[str, str]:
    bots, _ = loader.load_all()
    return {k: c.name for k, c in bots.items()}


def build(day: date | None = None, results: list[dict] | None = None, backtests: list[dict] | None = None,
          names: dict[str, str] | None = None) -> dict:
    mon, fri = week_of(day or date.today())
    results = journal.load("paper_results") if results is None else results
    backtests = journal.load("backtests") if backtests is None else backtests
    names = _names() if names is None else names
    expect = {b["bot"]: (b.get("untested") or {}).get("avg_r") for b in backtests}
    week = [r for r in results if str(mon) <= r["day"] <= str(fri)]
    by_bot: dict[str, list[float]] = defaultdict(list)
    by_day: dict[str, float] = defaultdict(float)
    for r in week:
        by_bot[r["bot"]].append(r["r"])
        by_day[r["day"]] += r["r"]
    rows = []
    for bid, rs in sorted(by_bot.items(), key=lambda kv: -sum(kv[1])):
        e = expect.get(bid)
        rows.append({"bot": names.get(bid, bid), "trades": len(rs), "wins": sum(x > 0 for x in rs),
                     "total_r": round(sum(rs), 2), "best_r": round(max(rs), 2), "worst_r": round(min(rs), 2),
                     "backtest_avg_r": e,
                     "vs_backtest": None if e is None else
                     "better than the backtest" if sum(rs) / len(rs) > e else "worse than the backtest"})
    vetoes = [v for v in journal.load("vetoes") if str(mon) <= v.get("day", "") <= str(fri)]
    n = len(week)
    days = [str(mon + timedelta(days=i)) for i in range(5)]
    out = {"week": {"from": str(mon), "to": str(fri)}, "account": "PAPER", "trades": n,
           "total_r": round(sum(r["r"] for r in week), 2), "bots": rows,
           "by_day": [{"day": d, "total_r": round(by_day.get(d, 0.0), 2)} for d in days],
           "vetoes": len(vetoes),
           "honesty": (f"Small week: {n} trade{'s' if n != 1 else ''} is too few to judge any bot."
                       if n < SMALL else "One week is still a small sample; the honest report is the real test."),
           "note": "Paper trading, closed trades only, after costs, in R (multiples of the risk). Not financial advice."}
    return out


def svg(rc: dict) -> str:
    """The recap card as a self-contained SVG (fixed light colors so it looks the same wherever it's shared)."""
    def t(x, y, s, size=14, fill=INK, weight=400, anchor="start"):
        return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}" '
                f'text-anchor="{anchor}">{escape(str(s))}</text>')
    sign = lambda v: f"{v:+.2f}R"                                    # noqa: E731
    color = lambda v: UP if v > 0 else DOWN if v < 0 else MUTED       # noqa: E731
    rows = rc["bots"] or [{"bot": "No closed paper trades this week", "trades": 0, "wins": 0, "total_r": 0.0,
                           "backtest_avg_r": None, "vs_backtest": None}]
    top = 150
    h = top + 30 + ROW_H * len(rows) + 162
    a = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" '
         f'font-family="-apple-system, Helvetica, Arial, sans-serif" role="img" '
         f'aria-label="BotScope weekly recap {rc["week"]["from"]} to {rc["week"]["to"]}">',
         f'<rect width="{W}" height="{h}" rx="16" fill="{BG}" stroke="{LINE}"/>',
         t(28, 44, "BotScope weekly recap", 22, weight=700),
         t(28, 68, f"Week of {rc['week']['from']} to {rc['week']['to']} · PAPER trading", 13, MUTED),
         t(28, 116, sign(rc["total_r"]), 40, color(rc["total_r"]), 800),
         t(W - 28, 98, f"{rc['trades']} closed trades", 15, anchor="end"),
         t(W - 28, 120, f"{rc['vetoes']} vetoes", 13, MUTED, anchor="end"),
         t(28, top, "Bot", 12, MUTED, 600), t(330, top, "Trades", 12, MUTED, 600, "end"),
         t(420, top, "Week", 12, MUTED, 600, "end"), t(W - 28, top, "Backtest per trade", 12, MUTED, 600, "end"),
         f'<line x1="28" y1="{top + 8}" x2="{W - 28}" y2="{top + 8}" stroke="{LINE}"/>']
    y = top + 30
    for r in rows:
        bt = "not measured" if r["backtest_avg_r"] is None else sign(r["backtest_avg_r"])
        a += [t(28, y, r["bot"][:34], 14, weight=600), t(330, y, f"{r['trades']} ({r['wins']} won)", 13, anchor="end"),
              t(420, y, sign(r["total_r"]), 14, color(r["total_r"]), 700, "end"),
              t(W - 28, y, bt, 13, MUTED, anchor="end")]
        y += ROW_H
    # by-day bars
    base, scale = y + 40, 34 / max(1.0, max(abs(d["total_r"]) for d in rc["by_day"]))
    a.append(f'<line x1="28" y1="{base}" x2="{W - 28}" y2="{base}" stroke="{LINE}"/>')
    step = (W - 56) / 5
    for i, d in enumerate(rc["by_day"]):
        x = 28 + i * step + step * 0.3
        hgt = abs(d["total_r"]) * scale
        a.append(f'<rect x="{x:.1f}" y="{base - hgt if d["total_r"] > 0 else base:.1f}" width="{step * 0.4:.1f}" '
                 f'height="{max(hgt, 1):.1f}" fill="{color(d["total_r"])}"><title>{d["day"]}: {sign(d["total_r"])}</title></rect>')
        a.append(t(x + step * 0.2, base + 52, date.fromisoformat(d["day"]).strftime("%a"), 12, MUTED, anchor="middle"))
    a += [t(28, base + 80, rc["honesty"], 13, INK, 600),
          t(28, base + 102, rc["note"], 11, MUTED), "</svg>"]
    return "\n".join(a)


def save(day: date | None = None) -> dict:
    rc = build(day)
    from . import userdata
    folder = userdata.place(ROOT / "data" / "recaps", "recaps")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"week-{rc['week']['from']}.svg"
    path.write_text(svg(rc))
    return rc | {"image": str(path)}
