"""My trades: import the trades you placed yourself (not a bot's), read-only, into your local journal.

Every source is turned into one shared fill format first, {symbol, side buy/sell, qty, price, time, tz}, and then
paired into whole round trips by imports.pair_fills (first-in-first-out, partial fills, options x100). So the hard
part is written once, and each broker only needs a small mapping.

Sources: your Alpaca PAPER account (filled order history, the only network call, read-only), a Webull CSV (the
column names are NOT confirmed from a real export yet: they live in WEBULL below, in one place), a CSV already in the
shared fill format, and made-up demo trades. Times are converted to US Eastern. Rows that can't be read are counted
and listed by line, never guessed. Saved in the journal as `my_trades` (this computer only). Nothing here can place,
change or cancel an order. Not financial advice.
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import imports, journal

ET = ZoneInfo("America/New_York")
MAX_ROWS = imports.MAX_ROWS
SHOW_BAD = 10
# Webull "Export Orders" (History tab). NOT confirmed from a real file: change it here if a real export differs.
WEBULL = {"symbol": "Symbol", "side": "Side", "status": "Status", "qty": "Filled", "price": "Avg Price",
          "time": "Filled Time"}
WEBULL_FILLED = ("filled", "partially filled")
FILL_COLUMNS = ("symbol", "side", "qty", "price", "time")
TIME_FORMATS = ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M")
SIDES = {"buy": "buy", "b": "buy", "buy to cover": "buy", "sell": "sell", "s": "sell", "short": "sell",
         "sell short": "sell", "sell_short": "sell"}
# Robinhood "Account activity report" and Fidelity "Accounts_History" CSVs. NOT confirmed from real files either: the
# column names come from other tools' import guides. Change them here if a real export differs. Both files have dates
# but no time of day, so their trades are DATE ONLY: they count in the setup and weekday tables and are left out of
# anything that needs the time (hour, morning/afternoon, holding time, the trade before it).
ROBINHOOD = {"date": "Activity Date", "symbol": "Instrument", "code": "Trans Code", "qty": "Quantity", "price": "Price"}
ROBINHOOD_SIDES = {"buy": "buy", "sell": "sell"}
ROBINHOOD_OPTIONS = ("bto", "stc", "sto", "btc", "oexp", "oasgn", "oexcs")
FIDELITY_DATE = ("Run Date", "Trade Date")                    # newer and older exports
FIDELITY = {"action": "Action", "symbol": "Symbol", "qty": "Quantity", "price": "Price ($)"}
DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y")
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.I)


def zone(tz: str | None) -> ZoneInfo:
    if not tz:
        raise ValueError("which time zone are the times in the file? e.g. America/New_York, America/Chicago, "
                         "America/Los_Angeles, Europe/London")
    try:
        return ZoneInfo(tz.strip())
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"unknown time zone '{tz}': use a name like America/New_York")


def to_eastern(stamp: str, tz: str | None) -> str:
    """A fill time (ISO, or Webull-style 10/15/2026 09:45:12, an EDT/EST-style letters suffix is ignored) in the
    given zone -> 'YYYY-MM-DDTHH:MM:SS' US Eastern. A time with its own offset keeps it."""
    s = re.sub(r"\s+[A-Z]{2,5}$", "", str(stamp or "").strip()).replace("Z", "+00:00")
    try:
        t = datetime.fromisoformat(s)
    except ValueError:
        t = None
        for fmt in TIME_FORMATS:
            try:
                t = datetime.strptime(s, fmt)
                break
            except ValueError:
                pass
        if t is None:
            raise ValueError(f"can't read the time '{str(stamp)[:30]}'")
    if t.tzinfo is None:
        t = t.replace(tzinfo=zone(tz))
    return t.astimezone(ET).strftime("%Y-%m-%dT%H:%M:%S")


def _num(v) -> float | None:
    return imports._num(str(v or "").strip().lstrip("@"))


def fill(symbol, side, qty, price, time, tz) -> dict:
    """One fill in the shared format, checked. ValueError says what's wrong (the row is then counted, not guessed)."""
    sym, sd, q, px = str(symbol or "").strip().upper(), SIDES.get(str(side or "").strip().lower()), _num(qty), _num(price)
    if not sym:
        raise ValueError("no symbol")
    if not sd:
        raise ValueError(f"side '{side}' is not buy or sell")
    if not q or q <= 0:
        raise ValueError(f"quantity '{qty}' is not a number above 0")
    if not px or px <= 0:
        raise ValueError(f"price '{price}' is not a number above 0")
    return {"symbol": sym, "side": sd, "qty": q, "price": px, "time": to_eastern(time, tz), "tz": "America/New_York"}


def to_date(stamp) -> str:
    """A date-only file's date -> 'YYYY-MM-DD'."""
    s = str(stamp or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ValueError(f"can't read the date '{s[:30]}'")


def has_time(t: dict) -> bool:
    """False for a date-only trade (from a Robinhood or Fidelity file): its time of day isn't known."""
    return len(t.get("opened") or "") > 10


def date_fill(symbol, side, qty, price, day) -> dict:
    """A fill from a file with dates only: checked like any fill, its time is just the date."""
    return fill(symbol, side, qty, price, "2000-01-02T12:00:00", "America/New_York") | {"time": to_date(day)}


def pair_dated(fills: list[dict]) -> tuple[list[dict], int, int]:
    """Date-only fills -> round trips, first-in-first-out per (account, symbol, long or short). Each fill says whether
    it opens or closes, and `seq` says its order within the day (from the file's row order, see _in_order). A closing
    fill with nothing open (shares bought before the file's first date) is counted and left out, never turned into a
    short. Returns (round trips, closing shares left out, shares still open)."""
    lots: dict[tuple, list[list]] = {}
    trips, unmatched = [], 0.0
    for f in sorted(fills, key=lambda f: (f["time"], f.get("seq", 0))):
        long = (f["side"] == "buy") == f["opens"]
        key = (f.get("account", ""), f["symbol"], long)
        if f["opens"]:
            lots.setdefault(key, []).append([f["qty"], f["price"], f["time"]])
            continue
        qty, open_lots = f["qty"], lots.get(key, [])
        while qty > 1e-9 and open_lots:
            lot = open_lots[0]
            take = min(qty, lot[0])
            entry, exit_ = lot[1], f["price"]
            trips.append({"bot": "dated", "symbol": f["symbol"], "side": "long" if long else "short", "entry": entry,
                          "exit": exit_, "qty": take, "r": None, "why": "", "opened": lot[2], "closed": f["time"],
                          "pnl": round((exit_ - entry) * take * (1 if long else -1), 2)})
            lot[0] -= take
            qty -= take
            if lot[0] < 1e-9:
                open_lots.pop(0)
        unmatched += qty
    return trips, round(unmatched, 6), round(sum(lot[0] for ls in lots.values() for lot in ls), 6)


def _in_order(fills: list[dict]) -> list[dict]:
    """Number the fills in the order they happened. These files list rows newest first (when the dates show the other
    way round, oldest first), so within a day the row order is the only clue to which fill came first."""
    days = [f["time"] for f in fills]
    newer_first = sum(a > b for a, b in zip(days, days[1:])) >= sum(a < b for a, b in zip(days, days[1:]))
    n = len(fills)
    return [f | {"seq": n - i if newer_first else i} for i, f in enumerate(fills)]


def _dated_counts(fills: list[dict], counts: dict) -> dict:
    trips, before, still = pair_dated(_in_order(fills))
    return counts | {"trips": trips, "sold_before_file": before, "open_at_end": still}


def _rows(text: str, header: tuple[str, ...] = ()) -> list[tuple[int, dict]]:
    """CSV rows with their line numbers. `header`: skip note lines above the line that starts with one of these."""
    lines = [ln for ln in text.lstrip("\ufeff").splitlines() if not ln.lstrip().startswith("#")]   # demo files carry a label line
    if header:
        start = next((i for i, ln in enumerate(lines) if ln.strip().strip('"').startswith(header)), 0)
        lines = lines[start:]
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    return [(n, {(k or "").strip(): (v or "").strip() for k, v in row.items()}) for n, row in enumerate(reader, 2)][:MAX_ROWS]


def _need(rows: list[tuple[int, dict]], columns, what: str) -> None:
    have = list(rows[0][1]) if rows else []
    missing = [c for c in columns if c not in have]
    if missing:
        raise ValueError(f"this doesn't look like a {what}: column(s) not found: {', '.join(missing)}. "
                         f"The file's columns: {', '.join(have[:20]) or '(none)'}")


def webull_fills(text: str, tz: str | None) -> tuple[list[dict], dict]:
    """A Webull orders CSV -> fills. Cancelled / not-filled orders are counted separately; unreadable rows by line."""
    zone(tz)
    rows = _rows(text)
    _need(rows, WEBULL.values(), "Webull orders export")
    out, bad, not_filled = [], [], 0
    for n, r in rows:
        if r[WEBULL["status"]].lower() not in WEBULL_FILLED:
            not_filled += 1
            continue
        try:
            out.append(fill(r[WEBULL["symbol"]], r[WEBULL["side"]], r[WEBULL["qty"]], r[WEBULL["price"]],
                            r[WEBULL["time"]], tz))
        except ValueError as e:
            bad.append(f"line {n}: {e}")
    return out, {"rows": len(rows), "not_filled": not_filled, "unreadable": len(bad), "unreadable_lines": bad[:SHOW_BAD]}


def plain_fills(text: str, tz: str | None = None) -> tuple[list[dict], dict]:
    """A CSV already in the shared fill format (symbol, side, qty, price, time; optional tz column per row)."""
    rows = _rows(text)
    _need(rows, FILL_COLUMNS, "fills file (symbol, side, qty, price, time, tz)")
    out, bad = [], []
    for n, r in rows:
        try:
            out.append(fill(r["symbol"], r["side"], r["qty"], r["price"], r["time"], r.get("tz") or tz))
        except ValueError as e:
            bad.append(f"line {n}: {e}")
    return out, {"rows": len(rows), "not_filled": 0, "unreadable": len(bad), "unreadable_lines": bad[:SHOW_BAD]}


def robinhood_fills(text: str) -> tuple[list[dict], dict]:
    """A Robinhood account activity report -> date-only fills. Stock buys and sells only: options, dividends,
    transfers and fees are counted, not imported."""
    rows = _rows(text)
    _need(rows, ROBINHOOD.values(), "Robinhood account activity report")
    out, bad, other, options = [], [], 0, 0
    for n, r in rows:
        code = r[ROBINHOOD["code"]].lower()
        if not code:                                   # blank lines and the notes at the bottom
            continue
        if code in ROBINHOOD_SIDES:
            try:
                qty = _num(r[ROBINHOOD["qty"]])                # some reports show sells as negative
                f = date_fill(r[ROBINHOOD["symbol"]], ROBINHOOD_SIDES[code],
                              abs(qty) if qty is not None else r[ROBINHOOD["qty"]], r[ROBINHOOD["price"]],
                              r[ROBINHOOD["date"]])
                out.append(f | {"opens": f["side"] == "buy"})       # Robinhood has no short selling
            except ValueError as e:
                bad.append(f"line {n}: {e}")
        elif code in ROBINHOOD_OPTIONS:
            options += 1
        else:
            other += 1
    return out, _dated_counts(out, {"rows": len(rows), "not_filled": 0, "not_trades": other,
                                    "options_skipped": options, "unreadable": len(bad),
                                    "unreadable_lines": bad[:SHOW_BAD], "times": "dates only"})


def fidelity_fills(text: str) -> tuple[list[dict], dict]:
    """A Fidelity account history CSV -> date-only fills. "YOU BOUGHT" / "YOU SOLD" rows only ("SOLD SHORT" opens a
    short, "BOUGHT TO COVER" closes it), paired within each account; options (symbols that start with "-") and
    everything else (dividends, transfers, interest) are counted, not imported."""
    rows = _rows(text, FIDELITY_DATE)
    date_col = next((c for c in FIDELITY_DATE if rows and c in rows[0][1]), FIDELITY_DATE[0])
    acct = next((c for c in ("Account Number", "Account") if rows and c in rows[0][1]), None)
    _need(rows, (date_col, *FIDELITY.values()), "Fidelity account history export")
    out, bad, other, options = [], [], 0, 0
    for n, r in rows:
        action = r[FIDELITY["action"]].upper()
        if not action:                                 # blank lines and the notes at the bottom
            continue
        side = "buy" if "YOU BOUGHT" in action else "sell" if "YOU SOLD" in action else None
        if not side:
            other += 1
        elif r[FIDELITY["symbol"]].startswith("-"):
            options += 1
        else:
            try:
                qty = _num(r[FIDELITY["qty"]])
                if qty is None:
                    raise ValueError(f"quantity '{r[FIDELITY['qty']][:20]}' is not a number (check the Quantity and "
                                     "Price columns aren't swapped in this file)")
                f = date_fill(r[FIDELITY["symbol"]], side, abs(qty), r[FIDELITY["price"]], r[date_col])
                opens = "SHORT" in action if side == "sell" else "COVER" not in action
                out.append(f | {"opens": opens, "account": r[acct] if acct else ""})
            except ValueError as e:
                bad.append(f"line {n}: {e}")
    return out, _dated_counts(out, {"rows": len(rows), "not_filled": 0, "not_trades": other,
                                    "options_skipped": options, "unreadable": len(bad),
                                    "unreadable_lines": bad[:SHOW_BAD], "times": "dates only"})


def trade_id(t: dict) -> str:
    """Same trade, same id, across re-imports, so your notes stay attached."""
    key = "|".join(str(t.get(k)) for k in ("source", "symbol", "side", "opened", "closed", "entry", "exit", "qty"))
    return hashlib.sha256(key.encode()).hexdigest()[:10]


def same_trade(t: dict) -> tuple:
    """What makes two imports the same trade: symbol, side, size, entry price and the minute it opened (brokers round
    seconds differently)."""
    return (t.get("symbol"), t.get("side"), float(t.get("qty") or 0), round(float(t.get("entry") or 0), 2),
            (t.get("opened") or "")[:16])


def save(source: str, fills: list[dict], counts: dict) -> dict:
    """Fills -> round trips -> journal. Replaces an earlier import from the same source (re-running is safe). A trade
    already saved from another source (e.g. Alpaca and a CSV of the same account) is left out, so it isn't counted
    twice. Matches are counted: two real trades that look alike, against one already saved, keep one of them."""
    from .demo_trades import LABEL
    demo_removed = 0
    if source != LABEL and any(r.get("source") == LABEL for r in journal.load("my_trades")):
        demo_removed = forget(LABEL)["removed"]          # made-up trades never mix with your own
    others: dict[tuple, list[str]] = {}
    for r in journal.load("my_trades"):
        if r.get("source") != source:
            others.setdefault(same_trade(r), []).append(r["source"])
    counts = dict(counts)
    trips = counts.pop("trips", None)
    rows, seen, dupes = [], {}, {}
    for t in (imports.pair_fills(fills) if trips is None else trips):
        t = {k: v for k, v in t.items() if k not in ("bot", "r", "why")} | {"source": source}
        if (left := others.get(same_trade(t))):
            other = left.pop()                          # each saved trade matches at most one new one
            dupes[other] = dupes.get(other, 0) + 1
            continue
        tid = trade_id(t)
        seen[tid] = seen.get(tid, 0) + 1
        rows.append({"trade_id": tid if seen[tid] == 1 else f"{tid}-{seen[tid]}", **t})   # two identical lots
    journal.replace_where("my_trades", {"source": source}, rows)
    closed = counts.pop("open_at_end") if "open_at_end" in counts else \
        sum(f["qty"] if f["side"] == "sell" else -f["qty"] for f in fills)
    return {"source": source, "fills_read": len(fills), "round_trips": len(rows), **counts,
            "still_open": "some fills have no closing fill yet, so they're not counted" if abs(closed) > 1e-9 else None,
            "demo_removed": (f"the {demo_removed} made-up demo trades were removed so they don't mix with yours"
                             if demo_removed else None),
            "sold_before": (f"{counts['sold_before_file']:g} shares were sold or covered with no opening fill in this "
                            "file (opened before its first date), so they're not counted")
                           if counts.get("sold_before_file") else None,
            "duplicates_skipped": sum(dupes.values()),
            "duplicates": (f"{sum(dupes.values())} trades were already imported from "
                           f"{', '.join(sorted(dupes))}, so they were left out to avoid counting them twice. Removing "
                           "that import and importing this one again brings them back.") if dupes else None,
            "times": counts.get("times") or "US Eastern", "read_only": True,
            "note": "Your own past trades, saved on this computer only. Nothing was traded. Not financial advice."}


def from_webull(path: str, tz: str | None) -> dict:
    p = _file(path)
    fills, counts = webull_fills(p.read_text(errors="replace"), tz)
    return save(f"Webull file {p.name}", fills, counts)


def from_robinhood(path: str) -> dict:
    p = _file(path)
    fills, counts = robinhood_fills(p.read_text(errors="replace"))
    return save(f"Robinhood file {p.name}", fills, counts)


def from_fidelity(path: str) -> dict:
    p = _file(path)
    fills, counts = fidelity_fills(p.read_text(errors="replace"))
    return save(f"Fidelity file {p.name}", fills, counts)


def from_fills_file(path: str, tz: str | None = None) -> dict:
    p = _file(path)
    fills, counts = plain_fills(p.read_text(errors="replace"), tz)
    return save(f"fills file {p.name}", fills, counts)


def from_text(broker: str, text: str, name: str, tz: str | None) -> dict:
    """The same imports from a file's text (Studio's file picker sends the text; nothing is uploaded anywhere)."""
    if broker == "webull":
        fills, counts = webull_fills(text, tz)
        return save(f"Webull file {name[:60]}", fills, counts)
    if broker == "fills":
        fills, counts = plain_fills(text, tz)
        return save(f"fills file {name[:60]}", fills, counts)
    if broker == "robinhood":
        fills, counts = robinhood_fills(text)
        return save(f"Robinhood file {name[:60]}", fills, counts)
    if broker == "fidelity":
        fills, counts = fidelity_fills(text)
        return save(f"Fidelity file {name[:60]}", fills, counts)
    raise ValueError(f"unknown file type '{broker}': webull, robinhood, fidelity or fills")


def is_bot_order(f: dict, rules: dict | None = None) -> bool:
    """A bot's order, not yours: it matches your alpaca_rules, or it has a custom client_order_id. Alpaca gives orders
    without one a random UUID, so an order from a bot that sets no id of its own can't be told apart from yours."""
    cid = f.get("client_order_id") or ""
    return imports._bot_of(f, rules or {}) != "alpaca" or bool(cid and not UUID.fullmatch(cid))


def from_alpaca(days: int = 90) -> dict:
    """Your own filled orders from your Alpaca PAPER account (read-only get_orders). Bots' orders are left out."""
    from .env import demo_mode
    if demo_mode():
        raise RuntimeError("demo mode has no Alpaca account to read: add your paper keys, or try the demo trades")
    days = max(1, min(int(days), 730))
    raw = imports._alpaca_fills(days)                  # read-only; it never trades
    rules = imports.local_config().get("alpaca_rules")
    mine = [f for f in raw if not is_bot_order(f, rules)]
    fills = [fill(f["symbol"], f["side"], f["qty"], f["price"], f["time"], "UTC") for f in mine]
    return save("Alpaca paper", fills, {"rows": len(raw), "not_filled": 0, "unreadable": 0, "unreadable_lines": [],
                                        "bot_orders_skipped": len(raw) - len(mine)})


def from_demo() -> dict:
    """The made-up demo trader's trades and notes (see demo_trades). Refused when your own trades are in this journal,
    so made-up trades never mix with real ones."""
    from . import demo_trades, trade_notes
    own = [s for s in {r.get("source") for r in journal.load("my_trades")} if s != demo_trades.LABEL]
    if own:
        raise ValueError(f"your own trades are imported here ({', '.join(sorted(own))}), and the made-up demo trades "
                         "would mix with them. Remove those imports first if you want to see the demo.")
    fills = [fill(**f) for f in demo_trades.fills()]
    out = save(demo_trades.LABEL, fills, {"rows": len(fills), "not_filled": 0, "unreadable": 0, "unreadable_lines": []})
    by = {(t["symbol"], t["opened"]): t["trade_id"] for t in trades(demo_trades.LABEL)}
    for n in demo_trades.notes():
        tid = by.get((n["symbol"], n["opened"]))
        if tid:
            trade_notes.note(tid, n["setup"], n["stop"], n["note"], n["checklist"])
    return out | {"demo": demo_trades.LABEL}


def _file(path: str) -> Path:
    p = Path(os.path.expanduser(path or ""))
    if not p.is_file():
        raise ValueError(f"no file at {p.name or path}")
    return p


def trades(source: str | None = None) -> list[dict]:
    """Saved round trips (oldest first), from one source or all."""
    rows = [r for r in journal.load("my_trades") if source is None or r.get("source") == source]
    return sorted(rows, key=lambda r: (r.get("opened") or "", r.get("closed") or ""))


def sources() -> list[dict]:
    by: dict[str, list] = {}
    for r in journal.load("my_trades"):
        by.setdefault(r["source"], []).append(r)
    return [{"source": s, "trades": len(ts), "from": min(t["opened"][:10] for t in ts),
             "to": max(t["closed"][:10] for t in ts)} for s, ts in sorted(by.items())]


def forget(source: str) -> dict:
    """Remove one import's trades from the journal (your notes stay, in case you import it again)."""
    rows = [r for r in journal.load("my_trades") if r.get("source") == source]
    journal.replace_where("my_trades", {"source": source}, [])
    return {"source": source, "removed": len(rows)}
