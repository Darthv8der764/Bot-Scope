"""Demo trades: a MADE-UP trader's fills, so "My trades" works with no broker and tests have known answers.

Nothing here is anyone's real trading: no broker, no account, no real person. The trades are generated from a fixed
seed (same every time), on made-up prices, with three patterns planted on purpose so the pattern table has something
to find:
1. a trade started soon after a loss (same day) usually loses too, and is bigger;
2. Friday afternoon trades usually lose;
3. losing trades are held much longer than winning ones.
Written in the shared fill format {symbol, side, qty, price, time, tz}. Not financial advice.
"""
from __future__ import annotations

import csv
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

LABEL = "MADE-UP DEMO TRADES (not real, results mean nothing)"
TZ = "America/New_York"
SEED = 11
START = date(2026, 8, 3)                  # a Monday; 8 weeks of weekdays
WEEKS = 8
HOLIDAYS = {date(2026, 9, 7)}           # NYSE closed inside the demo's 8 weeks: Labor Day (no calendar lookup)
_BASE = {"SPY": 640.0, "QQQ": 560.0, "AAPL": 230.0, "MSFT": 510.0, "NVDA": 180.0}
FIELDS = ("symbol", "side", "qty", "price", "time", "tz")


def _plan() -> list[dict]:
    """Round trips (with their planted kind) before they're split into fills. Same list every time."""
    rng = random.Random(SEED)
    out, d = [], START
    while d < START + timedelta(weeks=WEEKS):
        if d.weekday() < 5:
            t = datetime.combine(d, time(9, 40)) + timedelta(minutes=rng.randint(0, 20))
            kinds = ["normal"] * rng.choice((1, 2))
            day = []
            for kind in kinds:
                day.append(_trip(rng, d, t, kind))
                t = day[-1]["closed"] + timedelta(minutes=rng.randint(5, 25))
                if not day[-1]["win"]:                   # planted 1: right after a loss, another (bigger) trade
                    day.append(_trip(rng, d, day[-1]["closed"] + timedelta(minutes=rng.randint(3, 12)), "after_loss"))
                    t = day[-1]["closed"] + timedelta(minutes=rng.randint(5, 25))
            if d.weekday() == 4:                         # planted 2: Friday afternoons
                t = max(t, datetime.combine(d, time(13, 0)) + timedelta(minutes=rng.randint(0, 20)))
                for _ in range(2):
                    if t.time() > time(14, 45):
                        break
                    day.append(_trip(rng, d, t, "friday_pm"))
                    t = day[-1]["closed"] + timedelta(minutes=rng.randint(5, 15))
            if d not in HOLIDAYS:                        # drawn anyway, so the other days' trades stay the same
                out += [x for x in day if x["opened"].time() <= time(15, 15)]      # time left to close it
        d += timedelta(days=1)
    return out


def _trip(rng: random.Random, d: date, opened: datetime, kind: str) -> dict:
    win = rng.random() < {"normal": 0.62, "after_loss": 0.2, "friday_pm": 0.15}[kind]
    hold = rng.randint(8, 40) if win else rng.randint(70, 200)          # planted 3: losers held longer
    sym = rng.choice(list(_BASE))
    entry = round(_BASE[sym] * (1 + (d - START).days * 0.0004) * (1 + rng.uniform(-0.01, 0.01)), 2)
    move = rng.uniform(0.006, 0.014) if win else -rng.uniform(0.005, 0.010)
    side = "short" if rng.random() < 0.25 else "long"
    exit_ = round(entry * (1 + move * (1 if side == "long" else -1)), 2)
    qty = rng.randint(10, 40) * (2 if kind == "after_loss" else 1)
    stop_dist = round(entry * 0.008, 2)
    has_stop = rng.random() < 0.8
    return {"symbol": sym, "side": side, "qty": qty, "entry": entry, "exit": exit_, "win": win, "kind": kind,
            "opened": opened, "closed": min(opened + timedelta(minutes=hold), datetime.combine(d, time(15, 55))),
            "setup": "no setup" if kind == "after_loss" else rng.choice(("pullback", "breakout")),
            "stop": (round(entry - stop_dist if side == "long" else entry + stop_dist, 2)) if has_stop else None,
            "feeling": "frustrated" if kind == "after_loss" else rng.choice(("calm", "calm", "rushed", "bored"))}


def fills() -> list[dict]:
    """The demo trades as fills in the shared format: one opening and one closing fill per round trip."""
    out = []
    for x in _plan():
        o, c = ("buy", "sell") if x["side"] == "long" else ("sell", "buy")
        out.append({"symbol": x["symbol"], "side": o, "qty": x["qty"], "price": x["entry"],
                    "time": x["opened"].isoformat(timespec="seconds"), "tz": TZ})
        out.append({"symbol": x["symbol"], "side": c, "qty": x["qty"], "price": x["exit"],
                    "time": x["closed"].isoformat(timespec="seconds"), "tz": TZ})
    return out


def notes() -> list[dict]:
    """The made-up trader's notes: setup tag, stop (most trades), and two checklist answers. Matched to trades by
    symbol and open time."""
    return [{"symbol": x["symbol"], "opened": x["opened"].isoformat(timespec="seconds"), "setup": x["setup"],
             "stop": x["stop"], "note": "made-up demo note",
             "checklist": {"setup": x["setup"], "feeling": x["feeling"]}} for x in _plan()]


def planted() -> list[dict]:
    """What was planted, per round trip (for tests): kind, win, symbol, open and close time."""
    return [{"kind": x["kind"], "win": x["win"], "symbol": x["symbol"], "opened": x["opened"].isoformat(timespec="seconds"),
             "closed": x["closed"].isoformat(timespec="seconds")} for x in _plan()]


def write_csv(path: str | Path | None = None) -> Path:
    """Save the demo fills as a CSV (data/demo/my_trades_demo.csv by default), to look at or import like a file."""
    from .env import ROOT
    from .userdata import place
    p = Path(path) if path else place(ROOT / "data" / "demo" / "my_trades_demo.csv", "demo/my_trades_demo.csv")
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="") as f:
        f.write(f"# {LABEL}\n")
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(fills())
    return p
