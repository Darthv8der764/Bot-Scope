"""Import my bots (read-only): bring the results of bots you already run into BotScope.

Two ways in, both read-only, both paper only:
(a) Alpaca order history: filled orders from YOUR paper account, grouped into bots by client_order_id prefix
    (e.g. "swing-" -> swing) or by symbol, then paired first-in-first-out into round trips with dollars made.
(b) A trade-log file (CSV or JSON) with a column mapping: which of your columns is the symbol, side, entry, exit...

Saved in the journal as `imported_trades` (this computer only). Linking an imported bot to a BotScope bot makes its
trades that have an R count as live evidence on the confidence meter and in shadow comparisons. Nothing here can
place, change or cancel an order: the only Alpaca call is get_orders (filled history, and `orders()` for an
imported bot's open and past orders).

Your own file paths live in botscope.local.json (git-ignored, never committed), e.g.
  {"imports": [{"name": "my stock bot", "path": "~/somewhere/roundtrips.csv", "mapping": {...}}]}
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import journal
from .env import ROOT
from .errtext import say
from .userdata import place

LOCAL_CONFIG = place(ROOT / "botscope.local.json", "botscope.local.json")
FIELDS = ("symbol", "side", "entry", "exit", "qty", "pnl", "r", "opened", "closed", "bot", "why")
NEEDED = ("symbol", "entry", "exit")
MAX_ROWS = 50_000


def local_config() -> dict:
    p = Path(os.environ.get("BOTSCOPE_LOCAL_CONFIG") or LOCAL_CONFIG)
    try:
        return json.loads(p.read_text())
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        raise ValueError(f"botscope.local.json is not valid JSON: {e}")


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except ValueError:
        return None


def _side(v) -> str:
    s = str(v or "long").strip().lower()
    return "short" if s in ("short", "sell", "sell_short", "s", "-1") else "long"


def normalize(row: dict, mapping: dict, default_bot: str) -> dict | None:
    """One of your rows -> one round trip. `mapping` = {botscope field: your column name}; unmapped fields use their
    own name. A row with no symbol, entry or exit price is skipped (counted, never guessed)."""
    g = lambda f: row.get(mapping.get(f, f))   # noqa: E731
    sym, entry, exit_ = str(g("symbol") or "").strip().upper(), _num(g("entry")), _num(g("exit"))
    if not sym or entry is None or exit_ is None:
        return None
    side, qty = _side(g("side")), _num(g("qty")) or 1.0
    pnl = _num(g("pnl"))
    if pnl is None:
        pnl = (exit_ - entry) * qty * (1 if side == "long" else -1)
    return {"bot": str(g("bot") or default_bot).strip() or default_bot, "symbol": sym, "side": side,
            "entry": entry, "exit": exit_, "qty": qty, "pnl": round(pnl, 2), "r": _num(g("r")),
            "opened": str(g("opened") or "")[:19], "closed": str(g("closed") or "")[:19], "why": str(g("why") or "")[:80]}


def read_rows(text: str, fmt: str) -> list[dict]:
    if fmt == "json":
        got = json.loads(text)
        rows = got.get("trades", got) if isinstance(got, dict) else got
        if not isinstance(rows, list):
            raise ValueError("JSON must be a list of trades (or {\"trades\": [...]})")
        return [r for r in rows if isinstance(r, dict)][:MAX_ROWS]
    return list(csv.DictReader(io.StringIO(text)))[:MAX_ROWS]


def from_file(path: str, name: str, mapping: dict | None = None, link_to: str | dict | None = None,
              names: dict | None = None) -> dict:
    """Import a trade-log file. Replaces an earlier import with the same name (re-running is safe)."""
    p = Path(os.path.expanduser(path))
    if not p.is_file():
        raise ValueError(f"no file at {p.name}")
    fmt = "json" if p.suffix.lower() == ".json" else "csv"
    rows = read_rows(p.read_text(errors="replace"), fmt)
    return save(name, rows, mapping or {}, link_to, source=f"{fmt.upper()} file {p.name}", names=names)


def save(name: str, rows: list[dict], mapping: dict, link_to: str | dict | None, source: str,
         names: dict | None = None) -> dict:
    name = (name or "").strip()[:40]
    if not name:
        raise ValueError("give the import a name (e.g. 'my stock bot')")
    bad = [k for k in mapping if k not in FIELDS]
    if bad:
        raise ValueError(f"unknown field(s) in the mapping: {', '.join(bad)} (known: {', '.join(FIELDS)})")
    trades = [t for t in (normalize(r, mapping, name) for r in rows) if t]
    for t in trades:                       # optional full names for short strategy codes: "ABC" -> "ABC: Example strategy"
        # link_to: one BotScope bot for the whole import, or {strategy code: bot id} so each strategy feeds its own bot
        t["link_to"] = (link_to.get(t["bot"]) if isinstance(link_to, dict) else link_to) or None
        if names and isinstance(names.get(t["bot"]), str):
            t["bot"] = f"{t['bot']}: {names[t['bot']][:60]}"
    if rows and not trades:
        missing = [f for f in NEEDED if mapping.get(f, f) not in rows[0]]
        raise ValueError(f"no usable trades: column(s) not found: {', '.join(mapping.get(f, f) for f in missing)}. "
                         f"Your columns: {', '.join(list(rows[0])[:15])}")
    for r in [r for r in journal.load("imported_trades") if r.get("import") == name]:
        journal.remove("imported_trades", r["id"])
    for t in trades:
        journal.add("imported_trades", {"import": name, **t})
    out = summary(name)
    out.update(source=source, skipped=len(rows) - len(trades), read_only=True,
               note="Imported results of your own bot: read-only, nothing was traded. Past trades, not a backtest.")
    return out


# ---------- (a) Alpaca order history ----------
def _bot_of(f: dict, rules: dict) -> str:
    cid = f.get("client_order_id") or ""
    for pre, b in (rules.get("prefix") or {}).items():
        if cid.startswith(pre):
            return b
    return (rules.get("symbols") or {}).get(f["symbol"], "alpaca")


def _multiplier(symbol: str) -> int:
    """An option contract (OCC symbol like SPY261016C00500000) is 100 shares; prices are per share."""
    return 100 if re.fullmatch(r"[A-Z]{1,6}\d{6}[CP]\d{8}", symbol) else 1


def pair_fills(fills: list[dict], rules: dict | None = None) -> list[dict]:
    """Filled orders -> round trips, first-in-first-out per (bot, symbol). `fills` = [{symbol, side buy/sell, qty,
    price, time, client_order_id}]. rules = {"prefix": {"swing-": "swing"}, "symbols": {"BTC/USD": "crypto"}}."""
    rules = rules or {}

    def bot_of(f):
        return _bot_of(f, rules)

    open_lots: dict[tuple, list[list]] = {}
    out = []
    for f in sorted(fills, key=lambda x: x["time"]):
        key, sign = (bot_of(f), f["symbol"]), (1 if f["side"] == "buy" else -1)
        lots, qty = open_lots.setdefault(key, []), float(f["qty"])
        while qty > 1e-9 and lots and lots[0][0] * sign < 0:      # this fill closes (part of) the oldest open lot
            lot = lots[0]
            take = min(qty, abs(lot[0]))
            side = "long" if lot[0] > 0 else "short"
            pnl = (f["price"] - lot[1]) * take * (1 if side == "long" else -1) * _multiplier(key[1])
            out.append({"bot": key[0], "symbol": key[1], "side": side, "entry": lot[1], "exit": f["price"], "qty": take,
                        "pnl": round(pnl, 2), "r": None, "opened": lot[2][:19], "closed": f["time"][:19], "why": ""})
            lot[0] -= take * (1 if lot[0] > 0 else -1)
            qty -= take
            if abs(lot[0]) < 1e-9:
                lots.pop(0)
        if qty > 1e-9:
            lots.append([qty * sign, f["price"], f["time"]])
    return out


def _alpaca_fills(days: int) -> list[dict]:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest
    from .env import alpaca_keys
    client = TradingClient(*alpaca_keys(), paper=True)            # paper only; get_orders reads, it never trades
    after, fills = datetime.now(timezone.utc) - timedelta(days=days), []
    while True:
        got = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.CLOSED, after=after, limit=500, direction="asc"))
        for o in got:
            if o.filled_at and float(o.filled_qty or 0) > 0 and o.filled_avg_price:
                fills.append({"symbol": o.symbol, "side": str(o.side.value), "qty": float(o.filled_qty),
                              "price": float(o.filled_avg_price), "time": o.filled_at.isoformat(),
                              "client_order_id": o.client_order_id or ""})
        if len(got) < 500 or len(fills) >= MAX_ROWS:
            return fills
        after = max(o.submitted_at for o in got)


def from_alpaca(name: str = "alpaca", days: int = 90, rules: dict | None = None, link_to: str | None = None) -> dict:
    """Import filled orders from your Alpaca PAPER account (last `days` days) as round trips."""
    from .env import demo_mode
    if demo_mode():
        raise RuntimeError("demo mode has no Alpaca account to read: add your paper keys to import your order history")
    days = max(1, min(int(days), 730))
    trades = pair_fills(_alpaca_fills(days), rules or local_config().get("alpaca_rules"))
    rows = [{**t} for t in trades]
    out = save(name, rows, {}, link_to, source=f"Alpaca paper order history (last {days} days)")
    out["open_positions_not_counted"] = "orders that are still open (no closing fill yet) are not counted"
    return out


def _order_row(o) -> dict:
    num = lambda v: float(v) if v not in (None, "") else None
    when = lambda t: t.isoformat()[:19] if t else None
    val = lambda v: str(getattr(v, "value", v)) if v is not None else None
    return {"symbol": o.symbol, "side": val(o.side), "qty": num(o.qty), "filled_qty": num(o.filled_qty),
            "type": val(o.order_type or getattr(o, "type", None)), "limit": num(o.limit_price), "stop": num(o.stop_price),
            "filled_price": num(o.filled_avg_price), "status": val(o.status), "submitted": when(o.submitted_at),
            "filled": when(o.filled_at), "client_order_id": o.client_order_id or ""}


def _alpaca_orders(days: int) -> tuple[list[dict], list[dict]]:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest
    from .env import alpaca_keys
    client = TradingClient(*alpaca_keys(), paper=True)            # paper only; get_orders reads, it never trades
    after = datetime.now(timezone.utc) - timedelta(days=days)
    live = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500))
    past = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.CLOSED, after=after, limit=500))
    return [_order_row(o) for o in live], [_order_row(o) for o in past]


def orders(bot: str | None = None, days: int = 30, rules: dict | None = None, limit: int = 50) -> dict:
    """An imported bot's live (open) orders and past orders from your Alpaca PAPER account, read-only. Grouped into
    bots with the same rules as the import (client_order_id prefix or symbol). Nothing is placed, changed or cancelled."""
    from .env import demo_mode
    if demo_mode():
        raise RuntimeError("demo mode has no Alpaca account to read: add your paper keys to see your orders")
    rules = rules or local_config().get("alpaca_rules") or {}
    days, limit = max(1, min(int(days), 730)), max(1, min(int(limit), 500))
    live, past = _alpaca_orders(days)
    out: dict[str, dict] = {}
    for kind, rows in (("open", live), ("past", past)):
        for r in rows:
            b = _bot_of(r, rules)
            if bot is None or b == bot:
                out.setdefault(b, {"bot": b, "open": [], "past": []})[kind].append(r)
    for g in out.values():
        g["open"].sort(key=lambda r: r["submitted"] or "", reverse=True)
        g["past"].sort(key=lambda r: r["submitted"] or "", reverse=True)
        g["past_shown"], g["past_total"] = min(limit, len(g["past"])), len(g["past"])
        g["past"] = g["past"][:limit]
    return {"bots": sorted(out.values(), key=lambda g: g["bot"]), "days": days, "read_only": True,
            "source": f"Alpaca paper account orders (open now + the last {days} days)",
            "note": "Read-only: BotScope only reads these orders. It never places, changes or cancels one."}


def from_local(name: str | None = None) -> dict:
    """Run the imports listed in botscope.local.json (your own paths, never committed)."""
    items = local_config().get("imports") or []
    if not items:
        return {"error": "no imports in botscope.local.json yet",
                "how": 'add {"imports": [{"name": "my bot", "path": "~/path/trades.csv", "mapping": {"entry": "entry_px"}}]}'}
    done = []
    for it in items:
        if name and it.get("name") != name:
            continue
        try:
            done.append(from_file(it["path"], it["name"], it.get("mapping"), it.get("link_to"), it.get("names")))
        except (KeyError, ValueError) as e:
            done.append({"import": it.get("name"), "error": say(e)})
    return {"imports": done}


# ---------- reading it back ----------
def summary(name: str | None = None) -> dict:
    rows = [r for r in journal.load("imported_trades") if name is None or r.get("import") == name]
    by: dict[tuple, list] = {}
    for r in rows:
        by.setdefault((r["import"], r["bot"]), []).append(r)
    bots = []
    for (imp, b), ts in sorted(by.items()):
        wins = [t for t in ts if t["pnl"] > 0]
        rs = [t["r"] for t in ts if t.get("r") is not None]
        days = sorted(t["closed"][:10] for t in ts if t.get("closed"))
        bots.append({"import": imp, "bot": b, "trades": len(ts), "won": len(wins),
                     "total_usd": round(sum(t["pnl"] for t in ts), 2),
                     "avg_win_usd": round(sum(t["pnl"] for t in wins) / len(wins), 2) if wins else None,
                     "avg_r": round(sum(rs) / len(rs), 3) if rs else None, "trades_with_r": len(rs),
                     "from": days[0] if days else None, "to": days[-1] if days else None,
                     "linked_to": ts[0].get("link_to")})
    return {"bots": bots, "trades": len(rows)}


def live_rs(bid: str) -> list[float]:
    """R of imported trades linked to a BotScope bot: extra live evidence for the confidence meter."""
    return [r["r"] for r in journal.find("imported_trades", link_to=bid) if r.get("r") is not None]


def trades(name: str, bot: str | None = None, symbol: str | None = None) -> list[dict]:
    return [r for r in journal.find("imported_trades", **{"import": name}) if (bot is None or r["bot"] == bot)
            and (symbol is None or r["symbol"] == symbol.upper())]
