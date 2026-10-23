"""Option spreads, defined risk only, paper only: turn a bot's stock signal into a vertical debit spread plan.

Long signal -> bull call spread (buy the call nearest the price, sell the next strike up). Short signal -> bear put
spread (buy the put nearest the price, sell the next strike down). The most you can lose is the debit you pay, and
the plan says so in dollars. Nothing is ever ordered. Honest limit: BotScope can't backtest spreads, because free
historical option prices only go back to 2024 and would need their own fill model, so a plan is a plan, not a
tested result.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from . import backtest, data, loader

OCC = re.compile(r"^([A-Z.]+)(\d{6})([CP])(\d{8})$")
MIN_DAYS, MAX_DAYS = 7, 45


def parse(occ: str) -> dict | None:
    m = OCC.match(occ)
    if not m:
        return None
    return {"symbol": occ, "root": m.group(1), "expiry": datetime.strptime(m.group(2), "%y%m%d").date(),
            "type": "call" if m.group(3) == "C" else "put", "strike": int(m.group(4)) / 1000}


def _quote(row: dict) -> tuple[float | None, float | None]:
    q = row.get("latest_quote") or {}
    bid, ask = q.get("bid_price"), q.get("ask_price")
    return (bid if bid and bid > 0 else None), (ask if ask and ask > 0 else None)


def plan(side: str, spot: float, chain: dict, today: date | None = None) -> dict:
    today = today or date.today()
    kind = "call" if side == "long" else "put"
    legs = [p | {"bid": _quote(r)[0], "ask": _quote(r)[1]} for k, r in chain.items()
            if (p := parse(k)) and p["type"] == kind and MIN_DAYS <= (p["expiry"] - today).days <= MAX_DAYS]
    if not legs:
        raise ValueError(f"no {kind}s expiring in {MIN_DAYS}-{MAX_DAYS} days in this chain")
    expiry = min(p["expiry"] for p in legs)
    legs = sorted((p for p in legs if p["expiry"] == expiry), key=lambda p: p["strike"])
    buy = min(legs, key=lambda p: abs(p["strike"] - spot))
    i = legs.index(buy)
    sell = legs[i + 1] if side == "long" and i + 1 < len(legs) else legs[i - 1] if side == "short" and i > 0 else None
    if sell is None or buy["ask"] is None or sell["bid"] is None:
        raise ValueError("no two-strike spread with live quotes near the price; try again in market hours")
    width = abs(sell["strike"] - buy["strike"])
    debit = round(buy["ask"] - sell["bid"], 2)                  # pay the ask, receive the bid: the cautious fill
    if debit <= 0 or debit >= width:
        raise ValueError("these quotes don't make a sensible debit spread (stale or crossed quotes)")
    be = buy["strike"] + debit if side == "long" else buy["strike"] - debit
    return {"spread": f"{'bull call' if side == 'long' else 'bear put'} spread", "expiry": str(expiry),
            "days": (expiry - today).days,
            "buy": {"contract": buy["symbol"], "strike": buy["strike"], "ask": buy["ask"]},
            "sell": {"contract": sell["symbol"], "strike": sell["strike"], "bid": sell["bid"]},
            "debit_per_share": debit, "max_loss_usd": round(debit * 100, 2),
            "max_gain_usd": round((width - debit) * 100, 2), "breakeven": round(be, 2),
            "risk": "defined: the most one spread can lose is its debit"}


def bot_signal(cls, symbol: str) -> tuple[str | None, str]:
    """The bot's decision on its newest finished candle for this stock."""
    day = date.today() - timedelta(days=1)
    bs, _ = data.view_bars(symbol, day, cls.timeframe, backtest.warmup_days(cls, data.DAILY_LOOKBACK))
    bs = data.clean(bs)[0]
    if not bs:
        return None, "no candles for that day"
    from .bot import View
    bot = cls()
    d = bot.entry(View(symbol, bs, bot.indicators(bs)))
    return (getattr(d, "side", None), getattr(d, "reason", ""))


def spread_plan(bot: str, symbol: str | None = None, side: str | None = None, chain=None, spot=None) -> dict:
    cls = loader.get(bot)
    sym = (symbol or cls.symbols[0]).upper()
    if data.is_crypto(sym):
        raise ValueError("option spreads are for stocks and ETFs, not crypto")
    why = "you chose the side"
    if side is None:
        side, why = bot_signal(cls, sym)
        if side is None:
            return {"bot": cls.name, "symbol": sym, "plan": None,
                    "why": f"the bot has no signal on its newest candle ({why}), so there's no spread to plan",
                    "note": NOTE}
    if side not in ("long", "short"):
        raise ValueError("side must be long or short")
    if chain is None or spot is None:
        from . import desk
        from alpaca.data.historical.option import OptionHistoricalDataClient
        from alpaca.data.requests import OptionChainRequest
        from .env import alpaca_keys
        c = OptionHistoricalDataClient(*alpaca_keys())
        raw = c.get_option_chain(OptionChainRequest(underlying_symbol=sym, expiration_date_gte=date.today() + timedelta(days=MIN_DAYS),
                                                    expiration_date_lte=date.today() + timedelta(days=MAX_DAYS)))
        chain = {k: v.model_dump() for k, v in raw.items()}
        spot = desk._snapshots([sym])[sym][0]
    return {"bot": cls.name, "symbol": sym, "side": side, "signal": why, "spot": spot,
            "plan": plan(side, spot, chain), "source": "Alpaca options (indicative feed: delayed, approximate quotes)",
            "note": NOTE}


NOTE = ("A paper plan only: nothing is ordered. Defined risk, but options can expire worthless, so the whole debit can "
        "go. Spreads aren't backtested (no long free option history). Not financial advice.")
