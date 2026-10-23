"""The bot nutrition label: one standard card, the same for every bot, built only from results saved on this
computer (the last honest report, luck meter and live paper log). Anything not measured yet says so instead of
showing a number. Not financial advice."""
from __future__ import annotations

from . import benchmark, confidence, journal, loader, report

MISSING = "not measured yet"


def _fmt_r(x, signed=True):
    return MISSING if x is None else (f"{x:+.2f}R" if signed else f"{x:.2f}R")


def build(bot: str) -> dict:
    cls = loader.get(bot)
    bid = loader.bot_id(cls)
    rep = report.saved(cls) or {}
    lk = (journal.find("luck", bot=bid) or [{}])[-1]
    rb = (journal.find("robustness", bot=bid) or [{}])[-1]
    op = max(journal.find("optimizer", bot=bid), key=lambda r: r.get("saved_at") or "", default={})
    conf = confidence.for_bot(bid)
    u = rep.get("untested") or {}
    yrs = (rep.get("years") or {}).get("untested") or []
    rng = u.get("total_r_range_5_50_95")
    crashes = [c for c in rep.get("crashes", []) if c.get("tested")]
    rows = [
        ("Status", cls.status),
        ("Timeframe / sides", f"{cls.timeframe}, {cls.sides}"),
        ("Untested years", f"{len(yrs)} ({yrs[0]}-{yrs[-1]})" if yrs else MISSING),
        ("Untested trades", str(u["trades"]) if u.get("trades") else MISSING),
        ("Per trade, after costs", _fmt_r(u.get("avg_r"))),
        ("Total, after costs", _fmt_r(u.get("total_r"))),
        ("Range (bad / middle / good)", " / ".join(f"{x:+.0f}R" for x in rng) if rng else MISSING),
        ("Worst drop", _fmt_r(u.get("max_drawdown_r"))),
        ("Worst losing streak", f"{u['worst_losing_streak']} trades" if "worst_losing_streak" in u else MISSING),
        ("Costs took", (_fmt_r(u.get("costs_r"), signed=False) + _per_trade_usd(u, rep))
         if "costs_r" in u else MISSING),
        ("If costs doubled", _fmt_r(round(u["total_r"] - u["costs_r"], 2))
         if u.get("total_r") is not None and "costs_r" in u else MISSING),
        ("Without its 3 best trades", _fmt_r(u["without_best_3_r"]) if "without_best_3_r" in u else MISSING),
        ("Beat just holding SPY?", f"{rep['vs_spy']['years_beat']} of {rep['vs_spy']['untested_years']} untested years "
         f"(bot {benchmark.usd(rep['vs_spy']['bot_usd'])} vs SPY {benchmark.usd(rep['vs_spy']['spy_usd'])})"
         if (rep.get("vs_spy") or {}).get("untested_years") else MISSING),
        *([("Beat just holding BTC?", f"{rep['vs_btc']['years_beat']} of {rep['vs_btc']['untested_years']} untested years "
             f"(bot {benchmark.usd(rep['vs_btc']['bot_usd'])} vs BTC {benchmark.usd(rep['vs_btc']['btc_usd'])})")]
          if (rep.get("vs_btc") or {}).get("untested_years") else []),
        ("Losing untested years", f"{len(rep['losing_untested_years'])} of {len(yrs)}" if yrs else MISSING),
        ("Crashes", "; ".join(f"{c['crash']}: {c['result']}" for c in crashes) if crashes else MISSING),
        ("Luck meter", f"{lk['level']} (beat {lk['random_twins']['beat']} of {lk['random_twins']['count']} random twins)"
         if lk.get("random_twins") else lk.get("level", MISSING)),
        ("Robustness checks", (f"{rb['passed']} pass" + (f"; failed: {', '.join(rb['failed'][:3])}"
                                                          + ("…" if len(rb['failed']) > 3 else "") if rb.get("failed") else ""))
         if rb.get("passed") else MISSING),
        ("Optimizer", (f"{_short_verdict(op['verdict'])} ({' × '.join(op['settings'])}, {op['cells_tried']} tried, "
                       f"{(op.get('saved_at') or '')[5:10]})") if op.get("verdict") else MISSING),
        ("Near misses", f"{rep['near_misses']['ghosts']} ghosts, {rep['near_misses']['total_r']:+.1f}R if taken"
         if (rep.get("near_misses") or {}).get("ghosts") else MISSING),
        ("Live paper trades", f"{conf['live']['trades']}" + (f", {conf['live']['avg_r']:+.2f}R each"
                                                              if conf["live"]["trades"] else "")),
        ("Confidence", conf["level"]),
    ]
    return {"bot": cls.name, "version": cls.version, "id": bid, "description": cls.description,
            "rows": [{"label": a, "value": b, "help": HELP.get(a, "")} for a, b in rows],
            "confidence": conf, "report_saved_at": rep.get("saved_at"), "luck_saved_at": lk.get("saved_at"),
            "data": rep.get("data") or "none yet (no honest report saved for this bot)",
            "bot_changed": _changed_note(cls, rep),
            "missing": [a for a, b in rows if b == MISSING],
            "how_to_fill": (f"Run honest_report {bid} (one backtest) to fill most of the missing rows; luck_meter "
                            f"and robustness_check (heavy) fill the rest." if not rep else
                            f"Run luck_meter {bid} and robustness_check {bid} (heavy) to fill the missing rows."),
            "note": "Past results, after trading costs. Not a promise and not financial advice."}


def _changed_note(cls, rep: dict) -> str | None:
    """Says so when the bot file changed after its report was saved: the label's numbers are for the older version."""
    if not report.changed_since(cls, rep):
        return None      # same file, or a report saved before fingerprints (can't tell, so stay quiet)
    return (f"The bot's code or the trading costs changed after this report was saved ({(rep.get('saved_at') or '')[:10]}), so these numbers "
            f"are for an older version. Run honest_report again to refresh them.")


def _short_verdict(v: str) -> str:
    """The optimizer's verdict in a few words for a label row."""
    if v.startswith("no cell makes money"):
        return "no setting pair makes money"
    if v.startswith("today's settings are already"):
        return "today's settings are the best cell"
    return v.split(":")[0]


def _per_trade_usd(u: dict, rep: dict) -> str:
    """' ($10.00/trade at $10k)': the costs in plain money, from the saved report."""
    if not u.get("trades") or u.get("costs_usd") is None or not rep.get("position_size_usd"):
        return ""
    size = rep["position_size_usd"]
    size = f"${size / 1000:g}k" if size >= 1000 else f"${size:,.0f}"
    return f" (${u['costs_usd'] / u['trades']:,.2f}/trade at {size})"


HELP = {   # one plain sentence per row, shown when you tap the row name on the label page
    "Status": "Where the bot stands: untested, on paper, passed or failed its tests.",
    "Timeframe / sides": "The candle size it trades on, and whether it buys (long), sells short, or both.",
    "Untested years": "Years the bot's settings were NOT picked on, so its results there are a fair test.",
    "Untested trades": "How many trades those untested years had; more trades = a result you can lean on more.",
    "Per trade, after costs": "The average result of one trade in R (1R = what the bot risks per trade), after fees and slippage.",
    "Total, after costs": "All untested trades added up, in R.",
    "Range (bad / middle / good)": "The trades reshuffled 1,000 times: 1 in 20 came out worse than 'bad', 1 in 20 better than 'good'.",
    "Worst drop": "The biggest fall from a high point to a low point, in R; you'd have to sit through this.",
    "Worst losing streak": "The most losing trades in a row.",
    "Costs took": "How much fees and slippage took out of the result, in R, and in dollars per trade at the tested size.",
    "If costs doubled": "The total if fills were twice as bad; a bot that only works with perfect fills shows it here.",
    "Without its 3 best trades": "The total with its 3 luckiest trades taken out; if this flips to a loss, a few trades carried it.",
    "Beat just holding SPY?": "Did the bot make more than simply buying the S&P 500 ETF with the same money?",
    "Beat just holding BTC?": "Crypto bots only: did the bot make more than simply buying bitcoin with the same money?",
    "Losing untested years": "How many of the fair-test years ended with a loss after costs.",
    "Crashes": "How it did through big market crashes inside its data; older ones say not tested.",
    "Optimizer": "The newest honest optimizer run on two of its settings: whether a different setting is a lead to test or just luck.",
    "Robustness checks": "The strategy factory's checklist (doubled costs, settings ±20%, later years, luck) run on this bot; each failure is a caution.",
    "Luck meter": "The bot vs 100 random bots trading at the same times; beating few of them looks like luck.",
    "Near misses": "Trades the bot almost took, played out on paper.",
    "Live paper trades": "Trades since the bot started running on paper, after the backtest.",
    "Confidence": "How far the evidence goes, from very low to very high: untested trades, luck and paper results.",
}


def markdown(lbl: dict) -> str:
    lines = [f"**{lbl['bot']} v{lbl['version']}: nutrition label**", ""]
    if lbl.get("bot_changed"):
        lines += [f"⚠ {lbl['bot_changed']}", ""]
    lines += ["| | |", "|---|---|"]
    lines += [f"| {r['label']} | {r['value']} |" for r in lbl["rows"]]
    if lbl["confidence"].get("next_level"):
        lines.append(f"| To move up | {lbl['confidence']['next_level']} |")
    lines += [""]
    if lbl["missing"]:
        lines.append(f"{len(lbl['missing'])} rows not measured yet. {lbl['how_to_fill']}")
    lines += [f"Data: {lbl['data']}.", "", f"_{lbl['note']}_"]
    return "\n".join(lines)
