"""Days like today: past days whose market looked like today's at the open, and what the bot did on each.

"Looked like" uses only what you'd know before the open: SPY's last 20 finished days (swings, how one-way the move
was, the 20-day move), how far SPY sits below its 60-day high, and its worst day in the last week. Each number is
put on the same scale (z-score over all days since 2016), and the closest days win. Then the bot is replayed on
those days only (one symbol, light). Every day says whether it's TUNED or UNTESTED. Wins are a count, never a %.
Not financial advice.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from . import backtest, data, loader, report, weather

FEATURES = ["swing_pct_a_year", "trend_efficiency", "move_20d_pct", "below_60d_high_pct", "worst_day_last_5_pct"]
SKIP_RECENT = 10          # the last 2 weeks overlap today's own 20-day window: never count them as "like today"
MIN_GAP = 5               # picked days at least a week apart, so one stretch of market can't fill the list


def day_features(index_bars) -> dict[str, dict]:
    """{day: numbers known at that day's open}, each from the closes before it (never its own)."""
    closes = [b.c for b in index_bars]
    out = {}
    for i, b in enumerate(index_bars):
        if i >= 61:
            n = weather.classify(closes[:i])
            out[str(b.t.date())] = n["numbers"] | {"weather": n["weather"]}
    return out


def nearest(feats: dict[str, dict], today: dict, k: int = 10, skip_after: str | None = None) -> list[dict]:
    """The k days closest to `today` (z-scored distance), at least MIN_GAP trading days apart."""
    days = [d for d in sorted(feats) if not skip_after or d < skip_after]
    if not days:
        return []
    scale = {}
    for f in FEATURES:
        xs = [feats[d][f] for d in days]
        m = sum(xs) / len(xs)
        scale[f] = (m, math.sqrt(sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1)) or 1.0)
    dist = {d: math.sqrt(sum(((feats[d][f] - today[f]) / scale[f][1]) ** 2 for f in FEATURES)) for d in days}
    idx = {d: i for i, d in enumerate(days)}
    picked: list[str] = []
    for d in sorted(days, key=dist.get):
        if all(abs(idx[d] - idx[p]) >= MIN_GAP for p in picked):
            picked.append(d)
        if len(picked) == k:
            break
    return [{"day": d, "distance": round(dist[d], 2), "weather": feats[d]["weather"],
             **{f: feats[d][f] for f in FEATURES}} for d in picked]


def similarity(distance: float) -> str:
    return "very close" if distance < 0.75 else "close" if distance < 1.5 else "loose"


def days_like_today(bot_cls, symbol: str | None = None, k: int = 10, today: date | None = None, fetch=None) -> dict:
    bot = bot_cls()
    symbol = (symbol or bot.symbols[0]).upper()
    today = today or date.today()
    fetch = fetch or data.bars
    spy, _ = data.clean(fetch(weather.INDEX, report.DATA_START, today - timedelta(days=1), "1Day", "sip"))
    spy = [b for b in spy if b.t.date() < today]
    if len(spy) < 62 + SKIP_RECENT:
        return {"error": "not enough SPY history to compare days"}
    feats = day_features(spy)
    now = weather.classify([b.c for b in spy])
    cut = str(spy[-SKIP_RECENT].t.date())
    picks = nearest(feats, now["numbers"], k, skip_after=cut)
    cost = backtest.COSTS[bot.asset]
    rows, all_trades, unt, problems = [], [], [], []
    warm = backtest.warmup_days(bot, 120)
    for p in picks:
        d = date.fromisoformat(p["day"])
        try:
            raw = fetch(symbol, d - timedelta(days=warm), d, bot.timeframe, "sip")
        except RuntimeError:
            raise
        except Exception as e:
            problems.append(f"{symbol} {d}: no data ({type(e).__name__})")
            continue
        raw, _ = data.clean(raw)
        sess = data.sessions(raw, bot.timeframe, data.is_crypto(symbol))
        trades = []
        for day, bs in sess.items():
            t, _ = backtest.run_day(bot_cls(), symbol, day, bs, cost, close_at_end=bot.timeframe == "1Day")
            trades += [x for x in t if x.t_in[:10] == p["day"]]
        all_trades += trades
        period = "tuned" if report._tuned(bot_cls, d, d) else "untested"
        if period == "untested":
            unt += trades
        rows.append({"day": p["day"], "how_alike": similarity(p["distance"]), "weather_then": p["weather"],
                     "period": period,
                     "trades": len(trades), "total_r": round(sum(t.r for t in trades), 2),
                     "result": ("no trade" if not trades else
                                ", ".join(f"{t.side} {t.r:+.2f}R ({t.why_out})" for t in trades)),
                     "open": f"/?bot={loader.bot_id(bot_cls)}&symbol={symbol}&day={p['day']}"})
    wins = sum(t.r > 0 for t in unt)
    summary = (f"on {len(rows)} days like today the bot traded {len(all_trades)} times"
               + (f"; untested ones: {wins} wins of {len(unt)}, {sum(t.r for t in unt):+.2f}R total" if unt else
                  "; none on untested days"))
    return {"bot": bot.name, "symbol": symbol, "today": {"as_of_close": str(spy[-1].t.date()), **now},
            "days": rows, "summary": summary,
            "how": "Matched on SPY's last 20 days (swings, one-way-ness, move), distance from its 60-day high and its "
                   "worst recent day, known before the open. The last 2 weeks are skipped (they overlap today).",
            "sample_note": (f"{len(rows)} days is a small sample: treat this as a story, not a forecast."),
            "data": f"days matched on SPY (Alpaca SIP); {symbol} bars: {report.data_line([symbol])}", "problems": problems[:5],
            "note": "Past days that looked alike can still go differently. Not financial advice."}
