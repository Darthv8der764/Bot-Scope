"""Tickers the user's bots trade or watch: every bot's `symbols` (botscope.loader), plus an optional watch.txt next
to this file (one ticker per line, # for comments). Replaces the prototype's account-specific local_tickers.py."""
from pathlib import Path


def from_bots():
    from botscope import loader
    bots, _ = loader.load_all()
    return {s.upper() for c in bots.values() for s in c.symbols}


def watched():
    f = Path(__file__).with_name("watch.txt")
    if not f.exists():
        return set()
    lines = (l.split("#")[0].strip().upper() for l in f.read_text().splitlines())   # "  # note" and "SPY  # note"
    return {t for t in lines if t}


def bot_tickers():
    return sorted(from_bots() | watched())
