"""One-sentence start and the bot check.

new_bot writes a starter bot file from a plain-English idea (it loads and runs, but takes no trades until its entry
rule is written). check_bot loads a bot and checks it on made-up bars: it imports, it never peeks at future bars,
every decision has a reason, and the plain-English rules mention every setting (so words and code stay in sync).
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timedelta
from pathlib import Path

from . import backtest, checkpoints, loader
from .bot import BarData, Bot, Entry, NoTrade
from .data import ET

TIMEFRAMES = ("1Min", "5Min", "15Min", "1Hour", "1Day")

TEMPLATE = '''"""{name}: {description}

Started with BotScope's new_bot on {today}. New and untested: nothing here has been backtested yet.
"""
from botscope.bot import Bot, Entry, Exit, NoTrade


class {cls}(Bot):
    name = "{name}"
    version = "0.1"
    description = "{description}"
    rules = [
        # One plain-English line per rule. Mention every number in `params` so the words match the code.
        "TODO: when to buy or short.",
        "TODO: where the stop goes (every trade needs one).",
        "Target: {r_multiple}x the risk.",
    ]
    symbols = {symbols}
    timeframe = "{timeframe}"
    sides = "{sides}"
    asset = "{asset}"
    max_trades_per_day = 1
    flat_by_close = {flat}
    lookback_days = 0           # daily bots: earlier days needed first (200 for a 200-day average)
    params = {{"r_multiple": {r_multiple}}}
    tuned_on = None
    status = "untested"
    notes = "Idea: {description}"

    def indicators(self, bars):
        # Lines the chart draws: one value per bar, using only bars up to that one (no peeking).
        return {{}}

    def entry(self, view):
        # view.bars = finished bars only. Return Entry(side, stop, target, reason) or NoTrade("why not").
        return NoTrade("entry rule not written yet")

    def exit(self, view, pos):
        # Extra exits beyond the stop/target. None = keep holding.
        return None
'''


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def new_bot(name: str, description: str, timeframe: str = "5Min", symbols: list[str] | None = None,
            sides: str = "both", r_multiple: float = 2.0) -> dict:
    if not name.strip() or not description.strip():
        raise ValueError("give the bot a name and a 1-2 sentence description")
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {', '.join(TIMEFRAMES)}")
    if sides not in ("long", "short", "both"):
        raise ValueError("sides must be long, short or both")
    slug = _slug(name)
    path = loader.bots_dir() / f"{slug}.py"
    if path.exists():
        raise ValueError(f"{path.name} already exists; pick another name")
    if slug in loader.load_all()[0]:
        raise ValueError(f"a bot named {name!r} already exists")
    cp = checkpoints.save(f"before new_bot {name}")
    cls = "".join(w.capitalize() for w in slug.split("_")) or "MyBot"
    if cls[0].isdigit():
        cls = "Bot" + cls
    clean = lambda s: s.replace("\\", "").replace('"', "'").strip()   # noqa: E731
    syms = [s.upper() for s in (symbols or ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"])][:5]
    path.write_text(TEMPLATE.format(name=clean(name), description=clean(description), cls=cls, symbols=repr(syms),
                                    timeframe=timeframe, sides=sides, flat=timeframe != "1Day",
                                    asset="swing" if timeframe == "1Day" else "stock_intraday",
                                    r_multiple=float(r_multiple), today=datetime.now(ET).date()))
    return {"file": str(path), "bot_id": slug, "checkpoint_before": cp["id"], "next":
            "Write the entry rule in entry() and the rules in plain English, then run check_bot, then run_backtest."}


def make_shadow(bot: str, version: str | None = None) -> dict:
    """Copy a bot as a new version that runs beside it on paper (shadow mode). A checkpoint is saved first."""
    cls = loader.get(bot)
    bid = loader.bot_id(cls)
    try:
        major = int(str(cls.version).split(".")[0]) + 1
    except ValueError:
        major = 2
    version = version or f"{major}.0"
    name = f"{cls.name} v{version}"
    slug = _slug(name)
    path = Path(cls.source_file).parent / f"{slug}.py"          # beside the bot it copies: bots_private/ stays private
    if path.exists() or slug in loader.load_all()[0]:
        raise ValueError(f"{path.name} already exists; pass another version")
    src = Path(cls.source_file).read_text()
    head = re.search(rf"^class {cls.__name__}\((.*?)\):\n", src, re.M)
    if not head:
        raise ValueError(f"couldn't find class {cls.__name__} in its file; copy it by hand")
    new_cls = cls.__name__ + "V" + re.sub(r"\W", "_", version)
    body = src[head.end():]
    body, n_name = re.subn(r'^(\s+)name\s*=\s*["\'].*?["\']\s*$', lambda m: f'{m.group(1)}name = "{name}"', body,
                          count=1, flags=re.M)
    body, n_ver = re.subn(r'^(\s+)version\s*=\s*["\'].*?["\']\s*$',
                         lambda m: f'{m.group(1)}version = "{version}"\n{m.group(1)}shadows = "{bid}"   # shadow mode: '
                                   f'runs beside {bid} on paper', body, count=1, flags=re.M)
    if not (n_name and n_ver):
        raise ValueError("the bot class needs its own name = and version = lines to be copied as a shadow")
    cp = checkpoints.save(f"before make_shadow {bid}")
    path.write_text(src[:head.start()] + f"class {new_cls}({head.group(1)}):\n" + body)
    return {"file": str(path), "bot_id": slug, "shadows": bid, "checkpoint_before": cp["id"],
            "next": "Change what you want to test in the new file, run check_bot on it, then let both run on paper; "
                    "shadow_scoreboard compares them on the same days."}


def _fake_bars(timeframe: str, seed: int = 5) -> list[BarData]:
    rng = random.Random(seed)
    step = {"1Min": 1, "5Min": 5, "15Min": 15, "1Hour": 60}.get(timeframe)
    px, out = 100.0, []
    if step is None:                                          # daily: 120 weekdays
        d = datetime(2026, 1, 5, tzinfo=ET)
        while len(out) < 120:
            if d.weekday() < 5:
                o = px; px *= 1 + rng.gauss(0, 0.012)
                out.append(BarData(d, o, max(o, px) * 1.004, min(o, px) * 0.996, px, 1e6))
            d += timedelta(days=1)
        return out
    t0 = datetime(2026, 9, 1, 9, 30, tzinfo=ET)
    for i in range(390 // step):
        o = px; px *= 1 + rng.gauss(0, 0.0015 * step ** 0.5)
        out.append(BarData(t0 + timedelta(minutes=i * step), o, max(o, px) + 0.02, min(o, px) - 0.02, px, 1000))
    return out


def _variants(v) -> set[str]:
    """Ways a setting's value may be written in plain English."""
    if isinstance(v, bool):
        return {str(v).lower()}
    if isinstance(v, (int, float)):
        out = {f"{v:g}"}
        if isinstance(v, float) and 0 < abs(v) < 1:
            out |= {f"{v * 100:g}%", f"{v * 100:g} %", f"{v * 100:g} percent"}
        return out
    return {str(v).lower()}


def rules_check(cls) -> list[str]:
    """Settings whose value the plain-English rules never mention (words and code may have drifted apart)."""
    text = " ".join(cls.rules).lower()
    missing = []
    for k, v in cls.params.items():
        if not any(re.search(r"(?<![\d.])" + re.escape(x.lower()) + r"(?![\d])", text) for x in _variants(v)):
            missing.append(f"{k} = {v!r}")
    return missing


def check_bot(bot: str) -> dict:
    bots, errors = loader.load_all()
    err = next((e for e in errors if _slug(e["file"][:-3]) == _slug(bot) or bot in e["file"]), None)
    if err:
        return {"bot": bot, "ok": False, "checks": [{"check": "loads", "pass": False, "detail": err["error"]}]}
    return check_class(loader.get(bot))


def check_class(cls) -> dict:
    """check_bot on an already-loaded bot class (the strategy factory checks candidates outside the bots folder)."""
    checks = []
    try:
        b = cls()
        checks.append({"check": "loads", "pass": True, "detail": f"{cls.name} v{cls.version}"})
    except Exception as e:
        return {"bot": cls.name, "ok": False, "checks": [{"check": "loads", "pass": False, "detail": str(e)}]}
    bars = _fake_bars(cls.timeframe)
    try:
        peek = backtest.no_peek_check(b, bars)
        checks.append({"check": "no peeking", "pass": peek is None, "detail": peek or "indicators only use past bars"})
    except Exception as e:
        checks.append({"check": "no peeking", "pass": False, "detail": f"indicators() crashed: {type(e).__name__}: {e}"})
    trace = []
    try:
        trades, probs = backtest.run_day(b, "TEST", bars[-1].t.date(), bars, backtest.COSTS[cls.asset], trace=trace,
                                         close_at_end=cls.timeframe == "1Day")
        no_reason = [x for x in trace if x["kind"] == "no_trade" and not x["reason"].strip()]
        checks.append({"check": "runs on made-up bars", "pass": not probs,
                       "detail": "; ".join(probs[:3]) or f"{len(trades)} trade(s) on a random-walk day (expect few)"})
        checks.append({"check": "every decision has a reason", "pass": not no_reason,
                       "detail": f"{len(no_reason)} empty reasons" if no_reason else "yes"})
    except Exception as e:
        checks.append({"check": "runs on made-up bars", "pass": False, "detail": f"{type(e).__name__}: {e}"})
    missing = rules_check(cls)
    checks.append({"check": "rules mention every setting", "pass": not missing,
                   "detail": ("not found in the rules: " + ", ".join(missing)) if missing else "yes"})
    checks.append({"check": "has plain-English rules", "pass": bool(cls.rules) and not any("TODO" in r for r in cls.rules),
                   "detail": f"{len(cls.rules)} rules" + (" (some still say TODO)" if any("TODO" in r for r in cls.rules) else "")})
    long_days = {k: v for k, v in cls.params.items() if k.endswith("_days") and "hold" not in k
                 and isinstance(v, (int, float)) and v >= 20}
    if cls.timeframe == "1Day" and long_days and getattr(cls, "lookback_days", 0) < max(long_days.values()):
        k = max(long_days, key=long_days.get)
        checks.append({"check": "declares its lookback", "pass": False,
                       "detail": f"{k} = {long_days[k]} but lookback_days = {getattr(cls, 'lookback_days', 0)}: set "
                                 f"lookback_days = {long_days[k]} so every backtest fetches enough earlier days (otherwise "
                                 "the first months of each test window are skipped)"})
    if getattr(cls, "history_days", 0) and cls.timeframe == "1Day":
        checks.append({"check": "history_days only for intraday bots", "pass": False,
                       "detail": f"history_days = {cls.history_days} on a daily bot: daily bots already see earlier days "
                                 "in view.bars (set lookback_days instead); view.history stays empty for them"})
    return {"bot": cls.name, "ok": all(c["pass"] for c in checks), "checks": checks,
            "note": "Made-up bars only test that the bot works, not that it makes money. Next: run_backtest."}
