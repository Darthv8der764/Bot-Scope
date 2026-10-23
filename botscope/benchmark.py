"""Beat just holding?: the bot vs simply buying SPY with the same money over the same days.

The fair question for any bot: would putting the same $10,000 into SPY on the first day and selling on the last have
done better? Holding pays one round trip of costs; the bot's numbers already have its costs taken out. Uses SPY
daily bars (Alpaca SIP, your own keys). If SPY can't be downloaded, the row says so instead of guessing.
"""
from __future__ import annotations

from datetime import date

from . import data

SYMBOL = "SPY"
HOLD_COST_BPS = 2.0          # one buy + one sell of SPY: about a penny spread each way
SAME_PCT = 0.25              # within a quarter of a percent of the money: call it a tie


def _fetch(*a):
    return data.bars(*a)


def hold(symbol: str, start: date, end: date, notional: float = 10_000, fetch=None,
         cost_bps: float = HOLD_COST_BPS) -> dict:
    """Buy `symbol` at the first day's open, sell at the last day's close, minus one round trip of costs."""
    fetch = fetch or _fetch
    try:
        bs = fetch(symbol, start, end, "1Day", "sip")
    except RuntimeError:
        raise
    except Exception as e:
        return {"error": f"{symbol} not available ({type(e).__name__})"}
    bs = [b for b in bs if start <= b.t.date() <= end]
    if not bs:
        return {"error": f"no {symbol} days in this window"}
    pct = (bs[-1].c / bs[0].o - 1) * 100 - cost_bps / 100
    return {"from": str(bs[0].t.date()), "to": str(bs[-1].t.date()), "days": len(bs),
            "buy": round(bs[0].o, 2), "sell": round(bs[-1].c, 2),
            "pct": round(pct, 2), "usd": round(pct / 100 * notional, 2)}


def spy_hold(start: date, end: date, notional: float = 10_000, fetch=None) -> dict:
    """Buy SPY at the first day's open, sell at the last day's close. {} if there are no bars."""
    return hold(SYMBOL, start, end, notional, fetch)


def usd(x: float) -> str:
    """Signed dollars the way people write them: +$8,324 / -$579 (not $+8,324)."""
    return f"{'-' if x < 0 else '+'}${abs(x):,.0f}"


def verdict(bot_usd: float | None, hold: dict, notional: float = 10_000) -> str:
    if not hold or "usd" not in hold:
        return "can't compare: " + (hold or {}).get("error", "no SPY data")
    bot_usd = bot_usd or 0.0
    gap = bot_usd - hold["usd"]
    if abs(gap) <= SAME_PCT / 100 * notional:
        return f"about the same as just holding SPY (bot {usd(bot_usd)}, SPY {usd(hold['usd'])})"
    word = "beat" if gap > 0 else "trailed"
    return f"{word} just holding SPY by ${abs(gap):,.0f} (bot {usd(bot_usd)}, SPY {usd(hold['usd'])})"


def compare(bot_usd: float | None, start: date, end: date, notional: float = 10_000, fetch=None) -> dict:
    """One row for a report: what SPY did, and whether the bot beat it."""
    hold = spy_hold(start, end, notional, fetch)
    gap = None if "usd" not in hold else (bot_usd or 0.0) - hold["usd"]
    result = None if gap is None else "tie" if abs(gap) <= SAME_PCT / 100 * notional else "beat" if gap > 0 else "trailed"
    return {"bot_usd": round(bot_usd or 0.0, 2), "spy_hold": hold, "beat_holding": verdict(bot_usd, hold, notional),
            "beat": None if result is None else result == "beat", "result": result}


CRYPTO_SYMBOL = "BTC/USD"   # crypto bots get a second line: the fair "why not just hold?" for them is bitcoin

CRYPTO_NOTE = ("vs BTC: the same money put into bitcoin on the first day and sold on the last, paying one round trip "
               "of crypto costs. Shown next to SPY (not instead of it) for bots that trade only crypto.")

NOTE = ("vs SPY: the same money put into SPY on the first day and sold on the last, one round trip of costs. "
        "The bot isn't always fully invested, so this is the 'why not just hold?' question, not a perfect match.")
