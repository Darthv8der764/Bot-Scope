"""The luck meter: could a bot with no idea have done just as well?

Two honest tests on the UNTESTED days:
1. Random twins: 100 bots that copy each real trade's symbol, day, side, stop distance and target size, but enter
   on a random candle. If the real bot doesn't beat most of them, its entries add nothing.
2. Shuffled days: the same candles in a random order (same moves and volatility, no real pattern). If the bot makes
   as much on shuffled days, its "edge" isn't coming from real market patterns.

Results are counts ("beat 87 of 100 random twins"), never a made-up probability. Not financial advice.
"""
from __future__ import annotations

import random
from datetime import timedelta

from . import backtest, data, journal, loader, report
from .bot import BarData, Bot, Entry

TWINS = 100
SHUFFLES = 10


def _day_groups(bot: Bot, symbols, windows, fetch, warmup: int):
    """[(symbol, day, bars, start)] for every session in the windows."""
    fetch = fetch or data.bars
    out = []
    for a, b in windows:
        for sym in symbols:
            try:
                raw = fetch(sym, a - timedelta(days=warmup), b, bot.timeframe, "sip")
            except RuntimeError:
                raise
            except Exception:
                continue
            for day, bs in data.sessions(data.clean(raw)[0], bot.timeframe, data.is_crypto(sym)).items():
                out.append((sym, day, bs, a))
    return out


def _twin(bot: Bot, sym, day, bs, t: backtest.Trade, rng: random.Random, cost, ind,
          span: tuple[int, int]) -> float | None:
    """One random-entry copy of a real trade: same side, stop distance and target size, random candle within the
    span of candles (counted from the session start) where the bot really enters, so twins trade at the same time
    of day."""
    lo = max(1, span[0])
    hi = min(len(bs) - 2, span[1])
    if hi < lo:
        return None
    i = rng.randint(lo, hi)
    c = bs[i].c
    d = 1 if t.side == "long" else -1
    risk = c * t.risk_pct / 100
    if risk <= 0:
        return None
    r_mult = abs(t.target - t.entry) / abs(t.entry - t.stop) if t.target and t.entry != t.stop else None
    e = Entry(t.side, c - d * risk, c + d * r_mult * risk if r_mult else None, "random twin")
    tr, _ = backtest.play_out(bot, sym, day, bs, i, e, cost, ind, close_at_end=bot.timeframe == "1Day")
    return tr.r if tr else None


def shuffle_bars(bs: list[BarData], rng: random.Random) -> list[BarData]:
    """Same candles (each one's move and shape), random order, same timestamps. Keeps volatility, kills patterns."""
    if len(bs) < 3:
        return list(bs)
    pieces = [(bs[i].c / bs[i - 1].c, bs[i].o / bs[i].c, bs[i].h / bs[i].c, bs[i].l / bs[i].c, bs[i].v)
              for i in range(1, len(bs))]
    rng.shuffle(pieces)
    out, c = [bs[0]], bs[0].c
    for b, (ret, o, h, l, v) in zip(bs[1:], pieces):   # noqa: E741
        c *= ret
        out.append(BarData(b.t, c * o, c * h, c * l, c, v))
    return out


def verdict(beat: int, of: int, real_r: float, shuffled_avg: float | None) -> dict:
    """Plain-English verdict from counts. Levels: looks like luck / unclear / beats luck."""
    why = [f"beat {beat} of {of} random twins (same trades, random entry candle)"]
    if real_r <= 0:
        level = "looks like luck"
        why.append("it doesn't make money on untested days, so there is no edge to explain")
    elif beat >= 95 * of / 100:
        level = "beats luck"
    elif beat >= 80 * of / 100:
        level = "unclear"
    else:
        level = "looks like luck"
    if shuffled_avg is not None:
        why.append(f"on shuffled days (no real patterns) it averaged {shuffled_avg:+.1f}R vs {real_r:+.1f}R on real days")
        if shuffled_avg >= real_r and level == "beats luck":
            level = "unclear"
            why.append("it does as well on shuffled days, so the edge may not come from real patterns")
    return {"level": level, "why": why}


def luck_meter(bot_cls, symbols: list[str] | None = None, years: bool = False, fetch=None, seed: int = 7,
               twins: int = TWINS, shuffles: int = SHUFFLES, save: bool = True, today=None) -> dict:
    """Run the luck meter on the untested days: the quick 2-month window, or every untested year (years=True)."""
    bot = bot_cls()
    symbols_asked = list(symbols or bot.symbols)
    symbols = [s.upper() for s in symbols_asked][:backtest.MAX_SYMBOLS]
    if years:
        ws = [(w["from"], w["to"]) for w in report.year_windows(bot_cls, today) if w["period"] == "untested"]
    else:
        ws = [(a, b) for label, a, b in backtest.windows(bot_cls) if label == "untested"]
    warm = backtest.warmup_days(bot, report.DAILY_WARMUP)
    groups = _day_groups(bot, symbols, ws, fetch, warm)
    cost = backtest.COSTS[bot.asset]
    rng = random.Random(seed)
    real, per_day = [], []
    for sym, day, bs, start in groups:
        tr, _ = backtest.run_day(bot, sym, day, bs, cost, close_at_end=bot.timeframe == "1Day")
        tr = [t for t in tr if t.t_in[:10] >= str(start)]
        real += tr
        if tr:
            per_day.append((sym, day, bs, tr, bot.indicators(bs)))
    real_r = round(sum(t.r for t in real), 2)
    idx = [[b.t.isoformat() for b in bs].index(t.t_in) for _, _, bs, tr, _ in per_day for t in tr]
    span = (min(idx), max(idx)) if idx else (1, 1)
    missing = sorted(set(symbols) - {g[0] for g in groups})
    base = {"bot": bot.name, "symbols": symbols, "windows": [[str(a), str(b)] for a, b in ws],
            "data": report.data_line(symbols), "untested_trades": len(real), "real_total_r": real_r}
    if (lo := backtest.left_out(symbols_asked)):
        base["left_out"] = lo
    if missing:
        base["no_data"] = f"no prices for {', '.join(missing)} in these windows, so they're left out"
    if len(real) < 10:
        return base | {"level": "not enough trades", "why": [f"only {len(real)} untested trades (need 10+)"],
                       "note": "Not financial advice."}
    totals = []
    for _ in range(twins):
        tot = 0.0
        for sym, day, bs, tr, ind in per_day:
            for t in tr:
                r = _twin(bot, sym, day, bs, t, rng, cost, ind, span)
                tot += r or 0.0
        totals.append(round(tot, 2))
    beat = sum(real_r > x for x in totals)
    sh = []
    for _ in range(shuffles):
        tot = 0.0
        for sym, day, bs, start in groups:
            fake = shuffle_bars(bs, rng)
            tr, _ = backtest.run_day(bot, sym, day, fake, cost, close_at_end=bot.timeframe == "1Day")
            tot += sum(t.r for t in tr if t.t_in[:10] >= str(start))
        sh.append(tot)
    sh_avg = round(sum(sh) / len(sh), 2) if sh else None
    totals.sort()
    out = base | verdict(beat, twins, real_r, sh_avg) | {
        "random_twins": {"count": twins, "beat": beat, "median_total_r": totals[len(totals) // 2],
                         "best_total_r": totals[-1], "worst_total_r": totals[0]},
        "shuffled_days": {"runs": shuffles, "avg_total_r": sh_avg},
        "note": "Counts, not a probability. Random twins copy each trade's side, stop distance and target size but "
                "enter on a random candle in the same part of the day the bot trades in. Not financial advice."}
    if save:
        journal.upsert("luck", {"bot": loader.bot_id(bot_cls)}, {k: v for k, v in out.items() if k != "bot"})
    return out
