"""Strategy DNA: a fingerprint of each bot (trend vs dip, holding time, time of day, long/short lean, symbols) and
a near-twin flag for bots that are really the same bet. Style comes from the bot's own rules text; holding time,
time of day and lean come from a short UNTESTED-days backtest (last 120 days for daily bots, 30 for intraday), one
bot at a time. Counts only."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from statistics import median

from . import backtest, loader

DIP = r"\bdip|pullback|oversold|rsi|reversion|revert|fade|below the (lower )?band|bounce|sharp(ly)? down"
TREND = r"breakout|breaks? (above|out)|crosses above|uptrend|trend|new (\d+-day )?high|momentum|range high|channel"
TWIN_AT = 0.75


def style(cls) -> str:
    text = " ".join([cls.description, *cls.rules]).lower()
    d, t = len(re.findall(DIP, text)), len(re.findall(TREND, text))
    return "dip buying" if d > t else "trend following" if t > d else "mixed"


def _hours(a: str, b: str) -> float:
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 3600


def fingerprint(cls, trades) -> dict:
    n = len(trades)
    longs = sum(t.side == "long" for t in trades)
    held = [_hours(t.t_in, t.t_out) for t in trades if t.t_in and t.t_out]
    mh = median(held) if held else None
    hold = ("no trades" if mh is None else f"{mh * 60:.0f} min" if mh < 1 else f"{mh:.1f} h" if mh < 24
            else f"{mh / 24:.1f} days")
    if cls.timeframe == "1Day":
        tod = "at the daily close"
    elif trades:
        hrs = [datetime.fromisoformat(t.t_in).hour + datetime.fromisoformat(t.t_in).minute / 60 for t in trades]
        m = median(hrs)
        tod = f"{'morning' if m < 11.5 else 'midday' if m < 14 else 'afternoon'} (median entry {int(m):02d}:{int(m % 1 * 60):02d} NY)"
    else:
        tod = "unknown (no trades)"
    lean = ("no trades" if not n else "long only" if longs == n else "short only" if not longs else
            f"{longs} of {n} long")
    return {"style": style(cls), "timeframe": cls.timeframe, "holding_time": hold, "hold_hours": mh,
            "time_of_day": tod, "lean": lean, "long_share": round(longs / n, 2) if n else None, "trades": n,
            "symbols": list(cls.symbols), "entries": sorted({(t.symbol, t.t_in[:10]) for t in trades})}


def similarity(a: dict, b: dict) -> tuple[float, list[str]]:
    why, score = [], 0.0
    sa, sb = set(a["symbols"]), set(b["symbols"])
    j = len(sa & sb) / len(sa | sb) if sa | sb else 0
    score += 0.25 * j; why += [f"{len(sa & sb)} shared symbols"] if sa & sb else []
    if a["style"] == b["style"]:
        score += 0.2; why.append(f"both {a['style']}")
    if a["timeframe"] == b["timeframe"]:
        score += 0.1; why.append(f"both {a['timeframe']}")
    if a["hold_hours"] and b["hold_hours"]:
        ratio = min(a["hold_hours"], b["hold_hours"]) / max(a["hold_hours"], b["hold_hours"])
        score += 0.15 * ratio; why += ["similar holding time"] if ratio > 0.6 else []
    if a["long_share"] is not None and b["long_share"] is not None:
        same = 1 - abs(a["long_share"] - b["long_share"])
        score += 0.1 * same; why += ["same long/short lean"] if same > 0.8 else []
    ea, eb = set(map(tuple, a["entries"])), set(map(tuple, b["entries"]))
    if ea and eb:
        share = len(ea & eb) / min(len(ea), len(eb))
        score += 0.2 * share; why += [f"{len(ea & eb)} entries on the same symbol and day"] if ea & eb else []
    return round(score, 2), why


def dna(bots: list[str] | None = None, fetch=None, today: date | None = None) -> dict:
    found, _ = loader.load_all()
    ids = [loader.bot_id(loader.get(b)) for b in bots] if bots else list(found)
    end = (today or date.today()) - timedelta(days=1)
    rows, problems = {}, []
    for bid in ids:
        cls = found.get(bid) or loader.get(bid)
        bot = cls()
        start = end - timedelta(days=120 if cls.timeframe == "1Day" else 30)
        trades, _, probs = backtest.run_window(bot, list(cls.symbols)[:backtest.MAX_SYMBOLS], start, end,
                                               fetch=fetch, warmup_days=backtest.warmup_days(bot, 30))
        problems += probs[:3]
        rows[bid] = {"bot": bid, "name": cls.name} | fingerprint(cls, trades)
    twins = []
    keys = list(rows)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            s, why = similarity(rows[a], rows[b])
            if s >= TWIN_AT:
                twins.append({"bots": [a, b], "score": s, "why": why})
    for r in rows.values():
        r.pop("entries"); r.pop("hold_hours")
    return {"window": {"from": "last 120 days (daily) / 30 days (intraday)", "to": str(end), "period": "untested"},
            "bots": list(rows.values()), "near_twins": twins,
            "summary": (f"{len(twins)} near-twin pair{'s' if len(twins) != 1 else ''}: "
                        + "; ".join(" + ".join(t["bots"]) for t in twins) + ". Two twins are one bet twice: "
                        "together they double the risk, not the edge." if twins else
                        f"no near-twins among {len(rows)} bots"),
            "problems": problems[:10],
            "note": "Style is read from each bot's rules; holding time, time of day and lean are from a short "
                    "backtest on recent untested days. A fingerprint, not a verdict. Not financial advice."}
