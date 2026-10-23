"""Market weather: is the market trending, choppy, or in a panic, and which bots do well in that weather?

The weather comes from the S&P 500 ETF (SPY) daily closes, using only days that had already closed (what you'd know
at the open), so it never peeks:
- panic:    20-day swings of 30%+ a year, 10%+ below the 60-day high, or a 3%+ one-day drop in the last 5 days
- trending: the last 20 days moved mostly one way (efficiency 0.30+: net move / total distance travelled)
- choppy:   everything else (lots of back and forth, little net progress)
"quiet" / "jumpy" is added from the same 20-day swing number.

Bot fit: the bot's UNTESTED trades grouped by the weather on the day they were entered. Counts and averages only.
Not financial advice.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta

from . import backtest, data, journal, loader

INDEX = "SPY"
LOOKBACK = 20
PANIC_VOL, PANIC_DD, PANIC_DAY = 30.0, -0.10, -0.03
TREND_ER = 0.30
QUIET_VOL, JUMPY_VOL = 12.0, 22.0
MIN_TRADES = 10
HISTORY_DAYS = 130            # calendar days of SPY fetched before a window (60 trading days + the lookback)


def classify(closes: list[float]) -> dict:
    """Weather from daily closes, oldest first; the last one is the most recent finished day."""
    if len(closes) < LOOKBACK + 1:
        return {"weather": "unknown", "why": [f"need {LOOKBACK + 1}+ daily closes, got {len(closes)}"]}
    c = closes[-(LOOKBACK + 1):]
    rets = [c[i] / c[i - 1] - 1 for i in range(1, len(c))]
    mean = sum(rets) / len(rets)
    vol = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) * math.sqrt(252) * 100
    path = sum(abs(c[i] - c[i - 1]) for i in range(1, len(c)))
    er = abs(c[-1] - c[0]) / path if path else 0.0
    dd = closes[-1] / max(closes[-60:]) - 1
    worst = min(rets[-5:])
    nums = {"swing_pct_a_year": round(vol, 1), "trend_efficiency": round(er, 2), "below_60d_high_pct": round(dd * 100, 1),
            "worst_day_last_5_pct": round(worst * 100, 1), "move_20d_pct": round((c[-1] / c[0] - 1) * 100, 1)}
    why = []
    if vol >= PANIC_VOL or dd <= PANIC_DD or worst <= PANIC_DAY:
        w = "panic"
        if vol >= PANIC_VOL:
            why.append(f"prices are swinging {vol:.0f}% a year (panic level is {PANIC_VOL:.0f}%+)")
        if dd <= PANIC_DD:
            why.append(f"{-dd * 100:.1f}% below the 60-day high")
        if worst <= PANIC_DAY:
            why.append(f"a {worst * 100:.1f}% day in the last week")
    elif er >= TREND_ER:
        w = "trending up" if c[-1] > c[0] else "trending down"
        why.append(f"the last {LOOKBACK} days moved mostly one way ({nums['move_20d_pct']:+.1f}%, efficiency {er:.2f})")
    else:
        w = "choppy"
        why.append(f"lots of back and forth, little net progress ({nums['move_20d_pct']:+.1f}% in {LOOKBACK} days, "
                   f"efficiency {er:.2f})")
    mood = "quiet" if vol < QUIET_VOL else "jumpy" if vol >= JUMPY_VOL else "normal"
    if w != "panic":
        why.append(f"{mood}: swings of {vol:.0f}% a year")
    return {"weather": w, "mood": mood, "why": why, "numbers": nums}


def label_days(index_bars) -> dict[str, str]:
    """{day: weather known at that day's open}: each day uses the closes before it, never its own."""
    closes = [b.c for b in index_bars]
    out = {}
    for i, b in enumerate(index_bars):
        if i >= LOOKBACK + 1:
            out[str(b.t.date())] = classify(closes[:i])["weather"]
    return out


def _index_bars(start: date, end: date, fetch=None):
    return data.clean((fetch or data.bars)(INDEX, start - timedelta(days=HISTORY_DAYS), end, "1Day", "sip"))[0]


def today(fetch=None, now: date | None = None) -> dict:
    now = now or date.today()
    y = now - timedelta(days=1)    # finished days only (free SIP data also can't be asked about today)
    bs = [b for b in _index_bars(y, y, fetch) if b.t.date() <= y]
    out = classify([b.c for b in bs])
    return {"as_of_close": str(bs[-1].t.date()) if bs else None, **out,
            "source": f"{INDEX} daily closes from Alpaca SIP (your own keys)"}


def fit_rows(trades, labels: dict[str, str]) -> list[dict]:
    g: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        g[labels.get(t.t_in[:10], "unknown")].append(t.r)
    return [{"weather": w, "trades": len(rs), "avg_r": round(sum(rs) / len(rs), 3), "total_r": round(sum(rs), 2)}
            for w, rs in sorted(g.items(), key=lambda kv: -len(kv[1]))]


def fit_verdict(rows: list[dict], weather: str) -> str:
    row = next((r for r in rows if r["weather"] == weather), None)
    if not row or row["trades"] < MIN_TRADES:
        return f"not enough untested trades in {weather} weather to say ({row['trades'] if row else 0}, need {MIN_TRADES}+)"
    return (f"does well in {weather} weather ({row['avg_r']:+.2f}R a trade over {row['trades']} untested trades)"
            if row["avg_r"] > 0 else
            f"struggles in {weather} weather ({row['avg_r']:+.2f}R a trade over {row['trades']} untested trades)")


def bot_fit(bot_cls, symbols: list[str] | None = None, days: int = 90, fetch=None, now_weather: str | None = None) -> dict:
    """The bot's untested trades grouped by the weather on their entry day; saved for the desk panel."""
    bot = bot_cls()
    symbols = [s.upper() for s in (symbols or bot.symbols)][:backtest.MAX_SYMBOLS]
    (_, a, b), = [w for w in backtest.windows(bot_cls, days) if w[0] == "untested"]
    warm = backtest.warmup_days(bot, 30)
    trades, _, problems = backtest.run_window(bot, symbols, a, b, fetch=fetch, warmup_days=warm)
    labels = label_days(_index_bars(a, b, fetch))
    rows = fit_rows(trades, labels)
    out = {"bot": bot.name, "window": {"from": str(a), "to": str(b), "period": "untested"}, "symbols": symbols,
           "by_weather": rows, "problems": problems[:5]}
    if now_weather:
        out["today"] = fit_verdict(rows, now_weather)
    journal.upsert("weather_fit", {"bot": loader.bot_id(bot_cls)},
                   {"bot_name": bot.name, "window": out["window"], "symbols": symbols, "by_weather": rows})
    return out


def market_weather(bot_cls=None, fetch=None) -> dict:
    """Today's weather, plus each bot's saved fit (and a fresh fit for `bot_cls`)."""
    now = today(fetch)
    fresh = bot_fit(bot_cls, fetch=fetch, now_weather=now["weather"]) if bot_cls else None
    bots = []
    for r in journal.load("weather_fit"):
        bots.append({"bot": r["bot"], "name": r.get("bot_name") or r["bot"], "window": r["window"],
                     "by_weather": r["by_weather"], "today": fit_verdict(r["by_weather"], now["weather"])})
    return {"weather": now, "bots": bots, "fresh_fit": fresh,
            "note": "Weather uses only finished days (what you'd know at the open). Bot fit = UNTESTED trades only. "
                    "Bots never measured say so; run market_weather with that bot. Not financial advice."}


def calendar_days(months: int = 6, fetch=None, now: date | None = None) -> dict:
    """Weather calendar: every finished trading day of the last `months` months with the weather known at its
    open (the closes before it, never its own) plus that day's SPY move, for the /weather page."""
    now = now or date.today()
    end = now - timedelta(days=1)
    start = end - timedelta(days=31 * max(1, min(months, 24)))
    bs = [b for b in _index_bars(start, end, fetch) if b.t.date() <= end]
    labels = label_days(bs)
    days = []
    for i, b in enumerate(bs):
        d = str(b.t.date())
        if d >= str(start) and d in labels and i:
            days.append({"day": d, "weather": labels[d], "spy_pct": round((b.c / bs[i - 1].c - 1) * 100, 2)})
    counts = defaultdict(int)
    for x in days:
        counts[x["weather"]] += 1
    return {"from": str(start), "to": str(end), "days": days, "counts": dict(counts),
            "source": f"{INDEX} daily closes from Alpaca SIP (your own keys)",
            "note": "Each day's color is the weather known at that day's open. Click a day to replay it in the bot "
                    "view. Not financial advice."}
