"""Broker and data adapters: one small interface so BotScope isn't tied to one company. Alpaca stays the default.

A data adapter answers `bars(symbol, start, end, timeframe)` with BarData, finished bars only. A broker adapter adds
`account()` (read-only). Orders never go through an adapter: they stay with Claude's Alpaca tools behind the
order guard, paper by default. Real adapters for other brokers wait until someone can test them with a real
account; the one extra adapter here is a keyless, read-only crypto data source (Coinbase's public candles) to
prove the interface. Each user downloads their own data; nothing is redistributed.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .bot import BarData

UTC = ZoneInfo("UTC")


class DataAdapter:
    name = "base"
    needs_keys = False
    assets = ("stocks",)
    read_only = True

    def bars(self, symbol: str, start: date, end: date, timeframe: str) -> list[BarData]:
        raise NotImplementedError

    def card(self) -> dict:
        return {"name": self.name, "needs_keys": self.needs_keys, "assets": list(self.assets), "read_only": self.read_only,
                "about": (self.__doc__ or "").strip().splitlines()[0]}


class AlpacaData(DataAdapter):
    """Alpaca market data with your own keys (stocks: SIP history, IEX today; crypto: keyless). The default."""
    name = "alpaca"
    needs_keys = True
    assets = ("stocks", "ETFs", "crypto")

    def bars(self, symbol, start, end, timeframe):
        from . import data
        return data.bars(symbol, start, end, timeframe, "sip")


class CoinbasePublic(DataAdapter):
    """Coinbase Exchange public candles: crypto only, no keys, read-only (300 candles per request)."""
    name = "coinbase"
    assets = ("crypto",)
    URL = "https://api.exchange.coinbase.com/products/{pair}/candles"
    GRAN = {"1Min": 60, "5Min": 300, "15Min": 900, "1Hour": 3600, "1Day": 86400}

    def __init__(self, get=None):
        self._get = get or self._http

    @staticmethod
    def _http(url: str):
        req = Request(url, headers={"User-Agent": "BotScope (personal use)"})
        from .market_data import _http as h                # certifi-backed TLS (python.org Python on macOS)
        with urlopen(req, timeout=20, context=h._ctx()) as r:
            return json.loads(r.read())

    def bars(self, symbol, start, end, timeframe):
        if timeframe not in self.GRAN:
            raise ValueError(f"coinbase has no {timeframe} candles")
        g, pair = self.GRAN[timeframe], symbol.upper().replace("/", "-")
        t, stop = datetime.combine(start, time(0), UTC), datetime.combine(end, time(23, 59), UTC)
        now = datetime.now(UTC)
        rows = {}
        while t < stop:
            t2 = min(t + timedelta(seconds=g * 300), stop)
            q = urlencode({"granularity": g, "start": t.isoformat(), "end": t2.isoformat()})
            for ts, lo, hi, o, c, v in self._get(self.URL.format(pair=pair) + "?" + q):
                bt = datetime.fromtimestamp(ts, UTC)
                if bt + timedelta(seconds=g) <= now:            # finished candles only
                    rows[ts] = BarData(bt, float(o), float(hi), float(lo), float(c), float(v))
            t = t2
        return [rows[k] for k in sorted(rows)]


ADAPTERS = {"alpaca": AlpacaData, "coinbase": CoinbasePublic}


def get(name: str) -> DataAdapter:
    if name not in ADAPTERS:
        raise ValueError(f"no data adapter {name!r}; have: {', '.join(ADAPTERS)}")
    return ADAPTERS[name]()


def crypto_source() -> str:
    from .env import key
    return key("BOTSCOPE_CRYPTO_DATA").lower() or "alpaca"


def sources() -> dict:
    return {"adapters": [a().card() for a in ADAPTERS.values()], "crypto_uses": crypto_source(),
            "stocks_use": "alpaca",
            "how": "Set BOTSCOPE_CRYPTO_DATA=coinbase in your .env to fetch crypto candles from Coinbase instead of Alpaca.",
            "note": "Data adapters only read. Orders never go through them. Each user downloads their own data."}
