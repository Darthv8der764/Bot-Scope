"""The BotScope bot file format. Every bot is one Python class that subclasses `Bot`.

The chart, the backtester and the safety checker only ever talk to a bot through this class, so any bot that
follows it can be charted, backtested and checked without special code.

    class MyBot(Bot):
        name = "My bot"                      # metadata: plain class attributes (see Bot below)
        ...
        def indicators(self, bars):  ->  {"line name": [value per bar]}         what the chart draws
        def entry(self, view):       ->  Entry(...)  or  NoTrade("why not", almost=Entry(...) | None)
                                                                                 called once per finished bar, when flat
        def exit(self, view, pos):   ->  Exit("why") or  None (keep holding)    called once per finished bar, when in

Rules every bot follows (the backtester and safety checker rely on them):
  1. No peeking: `view.bars` only holds bars that have already finished. A bot never sees the future.
  2. Every entry has a stop. Target is optional (None = hold until exit() or the close).
  3. Every decision has a reason in plain English (the "why not here?" click shows NoTrade reasons).
  4. Bots never place orders. They only say what they would do; BotScope decides paper vs live (paper by default).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar


@dataclass(frozen=True)
class BarData:
    t: datetime          # bar START time, timezone-aware (New York time for stocks)
    o: float
    h: float
    l: float             # noqa: E741
    c: float
    v: float


@dataclass(frozen=True)
class Entry:
    side: str                    # "long" | "short"
    stop: float                  # required: price where the trade is wrong
    target: float | None = None  # optional take-profit price
    reason: str = ""


@dataclass(frozen=True)
class NoTrade:
    reason: str                  # why the bot did NOT trade on this bar
    almost: Entry | None = None  # optional near miss: the trade it WOULD have taken if this one filter had passed.
                                 # BotScope plays it out on paper as a faded "ghost trade" (never a real trade), so
                                 # you can see whether the filter is saving you money or costing you.


@dataclass(frozen=True)
class Exit:
    reason: str                  # exit at this bar's close


@dataclass
class Position:
    side: str
    entry_price: float
    entry_time: datetime
    stop: float
    target: float | None
    reason: str = ""


@dataclass
class View:
    """What the bot can see when it decides: finished bars only."""
    symbol: str
    bars: list[BarData]          # today's finished bars, oldest first (bars[-1] = the bar that just closed)
    ind: dict[str, list]         # indicators(bars) for those same bars, same length
    trades_today: int = 0        # entries this bot already took today on this symbol
    history: list[BarData] = field(default_factory=list)  # intraday bots with history_days: the earlier sessions' bars, oldest first

    @property
    def now(self) -> datetime:
        return self.bars[-1].t

    @property
    def last(self) -> BarData:
        return self.bars[-1]


class Bot:
    # ---- metadata (override in every bot) ----
    name: ClassVar[str] = "Unnamed bot"
    version: ClassVar[str] = "0.1"
    description: ClassVar[str] = ""          # 1-2 sentences, plain English
    rules: ClassVar[list[str]] = []          # the rules in plain English, one per line (must match the code)
    symbols: ClassVar[list[str]] = []        # default tickers
    timeframe: ClassVar[str] = "1Min"        # bar size: "1Min" | "5Min" | "15Min" | "1Hour" | "1Day"
    sides: ClassVar[str] = "both"            # "long" | "short" | "both"
    asset: ClassVar[str] = "stock_intraday"  # cost profile in costs.json
    max_trades_per_day: ClassVar[int] = 1    # per symbol
    flat_by_close: ClassVar[bool] = True     # intraday bots: close everything at the last bar of the day
    lookback_days: ClassVar[int] = 0         # daily bots: earlier days needed before the first decision (e.g. 200 for a 200-day average)
    history_days: ClassVar[int] = 0          # intraday bots: earlier sessions to put in view.history (e.g. 1 = yesterday, for gap bots)
    params: ClassVar[dict] = {}              # every tunable number lives here, so tools can show and vary them
    tuned_on: ClassVar[tuple[str, str] | None] = None  # (start, end) dates the params were picked on; None = never tuned
    source_file: ClassVar[str] = ""          # set by the loader: the .py file this bot was loaded from
    shadows: ClassVar[str | None] = None     # shadow mode: id of the bot this is a new version of (runs beside it on paper)
    status: ClassVar[str] = "untested"       # "untested" | "paper" | "failed" | "passed" (honest label)
    notes: ClassVar[str] = ""                # where it came from, past results

    def __init__(self, **overrides):
        unknown = set(overrides) - set(self.params)
        if unknown:
            raise ValueError(f"{self.name}: unknown params {sorted(unknown)}")
        self.p = {**self.params, **overrides}

    # ---- the three methods ----
    def indicators(self, bars: list[BarData]) -> dict[str, list]:
        """Lines/levels the chart draws, one value per bar (None where not defined yet). Must not look ahead:
        value i may only use bars[0..i]."""
        return {}

    def entry(self, view: View) -> Entry | NoTrade:
        raise NotImplementedError

    def exit(self, view: View, pos: Position) -> Exit | None:
        """Extra exit rules beyond the stop/target (which BotScope handles). Default: none."""
        return None

    # ---- helpers for tools ----
    @classmethod
    def card(cls) -> dict:
        """Metadata as a plain dict (list_bots, the nutrition label, the chart header)."""
        return {"name": cls.name, "version": cls.version, "description": cls.description, "rules": cls.rules,
                "symbols": cls.symbols, "timeframe": cls.timeframe, "sides": cls.sides, "asset": cls.asset,
                "max_trades_per_day": cls.max_trades_per_day, "flat_by_close": cls.flat_by_close,
                "params": cls.params, "tuned_on": cls.tuned_on, "shadows": cls.shadows, "status": cls.status, "notes": cls.notes}
