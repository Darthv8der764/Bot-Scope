"""Paper account summary (read only). Always the PAPER endpoint: there is no switch here to read a live account."""
from __future__ import annotations

from .env import alpaca_keys


def summary() -> dict:
    from alpaca.trading.client import TradingClient

    client = TradingClient(*alpaca_keys(), paper=True)        # hard-wired to paper-api.alpaca.markets
    a = client.get_account()
    pos = client.get_all_positions()
    f = lambda x: round(float(x), 2) if x is not None else None  # noqa: E731
    return {
        "source": "Alpaca paper account (read only)",
        "equity": f(a.equity), "cash": f(a.cash), "buying_power": f(a.buying_power),
        "day_change": f(float(a.equity) - float(a.last_equity)),
        "positions": sorted(({"symbol": p.symbol, "side": str(p.side.value), "qty": float(p.qty),
                              "value": f(p.market_value), "open_pl": f(p.unrealized_pl)} for p in pos),
                            key=lambda p: -abs(p["value"] or 0)),
        "note": "Paper money. Not financial advice.",
    }
