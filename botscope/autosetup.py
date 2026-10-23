"""Auto setup for other people's bots: a guided import of a newcomer's existing bot into the BotScope format.

Step 1, `scan(path)`: reads (never runs) the newcomer's bot code and trade logs and lists what it found: language,
symbols, timeframe, indicators, stop/target hints, order calls, and for each trade log a guessed column mapping for
`import_my_bots(how="file")`. Claude then writes the bot file in the standard format (the botscope-auto-setup
skill), using these hints and the code itself.
Step 2, `finish(bot, ...)`: runs check_bot and writes the mapping report: what was translated, what was not, what
BotScope added, and what the newcomer must check. Then the honest report is its own (heavier) step.
Read-only and local: nothing here imports or executes the newcomer's code, and nothing places an order.
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime
from pathlib import Path

from . import journal

MAX_FILES, MAX_BYTES = 200, 400_000
CODE = {".py": "python", ".pine": "pine", ".js": "javascript", ".ts": "typescript", ".mq4": "mql4", ".mq5": "mql5"}
LOGS = {".csv", ".json"}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".env", "data", "cache"}

_TF = [("1Day", r"\b(?:1d|1D|1Day|daily|TimeFrame\.Day|Day\b)"), ("1Hour", r"\b(?:1h|1H|1Hour|60m|hourly|TimeFrame\.Hour)"),
       ("15Min", r"\b(?:15m|15Min|15min|15 ?minutes?)\b"), ("5Min", r"\b(?:5m|5Min|5min|5 ?minutes?)\b"),
       ("1Min", r"\b(?:1m|1Min|1min|TimeFrame\.Minute)\b")]
_IND = {"sma": r"\bsma\b|rolling\(.*\)\.mean|moving.average", "ema": r"\bema\b|ewm\(", "rsi": r"\brsi\b",
        "vwap": r"\bvwap\b", "atr": r"\batr\b", "macd": r"\bmacd\b", "bollinger": r"bollinger|\bbbands?\b",
        "breakout (highest/lowest)": r"highest|lowest|rolling\(.*\)\.max|rolling\(.*\)\.min|\bdonchian\b",
        "volume": r"\bvolume\b"}
_STOP = re.compile(r"(?i)\b(stop[_ ]?loss|stop[_ ]?pct|stop[_ ]?price|sl_?pct|trail(?:ing)?[_ ]?stop)\b\s*[=:]\s*([0-9.]+)")
_TARGET = re.compile(r"(?i)\b(take[_ ]?profit|target[_ ]?pct|tp_?pct|profit[_ ]?target|r_?multiple)\b\s*[=:]\s*([0-9.]+)")
_ORDERS = re.compile(r"\b(submit_order|place_order|create_order|order_send|OrderSend|strategy\.entry|"
                     r"market_order|limit_order|place_stock_order)\b")
_SYMBOL = re.compile(r"""['"]([A-Z]{1,5}(?:/USD[TC]?)?)['"]""")
_NOT_TICKERS = {"USD", "GET", "POST", "PUT", "BUY", "SELL", "LONG", "SHORT", "API", "KEY", "ID", "OK", "NA", "ET",
                "UTC", "EST", "PDT", "JSON", "CSV", "TRUE", "FALSE", "NONE", "DAY", "GTC", "IOC", "FOK", "OPG", "CLS",
                "LIMIT", "STOP", "A", "I", "X", "Y", "Z", "N", "R"}
_SYNONYMS = {"symbol": ("symbol", "ticker", "sym", "instrument", "asset"),
             "side": ("side", "direction", "dir", "position", "type"),
             "entry": ("entry", "entry_price", "entry_px", "buy_price", "open_price", "price_in", "avg_entry"),
             "exit": ("exit", "exit_price", "exit_px", "sell_price", "close_price", "price_out", "avg_exit"),
             "qty": ("qty", "quantity", "shares", "size", "contracts", "units"),
             "pnl": ("pnl", "p&l", "profit", "net", "realized", "pl", "gain"),
             "r": ("r", "r_multiple", "rmult", "realized_r"),
             "opened": ("opened", "entry_time", "open_time", "entry_date", "date_in", "time_in", "opened_at"),
             "closed": ("closed", "exit_time", "close_time", "exit_date", "date_out", "time_out", "closed_at", "date"),
             "bot": ("bot", "strategy", "setup", "system"),
             "why": ("why", "reason", "note", "notes", "signal")}


def _files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    out = []
    for p in sorted(root.rglob("*")):
        if len(out) >= MAX_FILES:
            break
        if p.is_file() and not (set(p.relative_to(root).parts[:-1]) & SKIP_DIRS) and p.name != ".env" \
                and (p.suffix.lower() in CODE or p.suffix.lower() in LOGS):
            out.append(p)
    return out


def guess_mapping(headers: list[str]) -> dict:
    """BotScope field -> the newcomer's column, by common names (case and spaces ignored)."""
    norm = {h: re.sub(r"[\s-]+", "_", h.strip().lower()) for h in headers}
    out = {}
    for field, names in _SYNONYMS.items():
        for h, n in norm.items():
            if n in names and h not in out.values():
                out[field] = h
                break
    return out


def _log_headers(p: Path, text: str) -> list[str]:
    if p.suffix.lower() == ".csv":
        return next(csv.reader(io.StringIO(text)), [])
    try:
        d = json.loads(text)
    except ValueError:
        return []
    rows = d if isinstance(d, list) else next((v for v in d.values() if isinstance(v, list)), []) if isinstance(d, dict) else []
    return list(rows[0]) if rows and isinstance(rows[0], dict) else []


def scan(path: str) -> dict:
    """Read a newcomer's bot (a file or a folder): hints for writing the BotScope bot file, and log mappings."""
    root = Path(path).expanduser()
    if not root.exists():
        raise ValueError(f"{path} doesn't exist")
    code, logs, skipped = [], [], []
    syms, tfs, inds, stops, targets, orders = {}, {}, set(), [], [], set()
    for p in _files(root):
        if p.stat().st_size > MAX_BYTES:
            skipped.append(f"{p.name} (over {MAX_BYTES // 1000} KB)")
            continue
        text = p.read_text(errors="replace")
        rel = str(p.relative_to(root)) if root.is_dir() else p.name
        if p.suffix.lower() in LOGS:
            hs = _log_headers(p, text)
            m = guess_mapping(hs)
            if {"symbol", "entry", "exit"} <= set(m):
                logs.append({"file": rel, "columns": hs[:30], "mapping": m,
                             "missing": [f for f in ("side", "qty", "pnl", "r", "closed") if f not in m]})
            continue
        code.append({"file": rel, "language": CODE[p.suffix.lower()], "lines": text.count("\n") + 1})
        for s in _SYMBOL.findall(text):
            if s not in _NOT_TICKERS:
                syms[s] = syms.get(s, 0) + 1
        for tf, rx in _TF:
            n = len(re.findall(rx, text))
            if n:
                tfs[tf] = tfs.get(tf, 0) + n
        inds |= {k for k, rx in _IND.items() if re.search(rx, text, re.I)}
        stops += [f"{rel}: {m.group(1)} = {m.group(2)}" for m in _STOP.finditer(text)][:5]
        targets += [f"{rel}: {m.group(1)} = {m.group(2)}" for m in _TARGET.finditer(text)][:5]
        orders |= set(_ORDERS.findall(text))
    timeframe = max(tfs, key=tfs.get) if tfs else None
    check = ["the rules in plain English match what the code really does",
             "the stop: BotScope needs one on every entry" + ("" if stops else " (none found in the code: pick one)"),
             f"the timeframe ({timeframe or 'not found'}) and symbols"]
    if orders:
        check.append(f"the code places orders ({', '.join(sorted(orders))}); the BotScope version never will (paper only)")
    pine = [c for c in code if c["language"] == "pine"]
    return {"path": str(root.name), "code_files": code[:50], "trade_logs": logs, "skipped": skipped,
            "suggested": {"symbols": [s for s, _ in sorted(syms.items(), key=lambda x: -x[1])][:8],
                          "timeframe": timeframe, "indicators": sorted(inds), "stop_hints": stops[:8],
                          "target_hints": targets[:8]},
            "needs_your_check": check, "read_only": True,
            "next": ("Pine Script found: use import_pine with its text first. " if pine else "") +
                    "Write the bot with new_bot + the code (botscope-auto-setup skill), then auto_setup(how=\"finish\"). "
                    "Trade logs: import_my_bots(how=\"file\", path=..., mapping=...) with the mapping above."}


def finish(bot: str, source: str = "", translated: list[str] | None = None, not_translated: list[str] | None = None,
           added: list[str] | None = None) -> dict:
    """check_bot on the new bot + the mapping report (saved in the journal as `auto_setup`)."""
    from . import scaffold
    chk = scaffold.check_bot(bot)                  # a bot that doesn't load still gets its report (and the error)
    translated, not_translated, added = translated or [], not_translated or [], added or []
    to_check = ["every line under 'Not translated' (the bot is only as faithful as the translation)",
                "each rule in plain English against the original bot's behavior"] + \
               [f"added by BotScope: {a}" for a in added]
    md = [f"# Auto setup: {chk.get('bot', bot)}", "", f"From: {source or 'not given'}  ", f"BotScope bot: `{bot}`", "",
          "## Translated", *([f"- {t}" for t in translated] or ["- (none listed)"]), "",
          "## Not translated (needs your check)", *([f"- {t}" for t in not_translated] or ["- nothing listed"]), "",
          "## Added by BotScope", *([f"- {a}" for a in added] or ["- nothing"]), "",
          "## Check", f"- check_bot: {'all passed' if chk.get('ok') else 'see the failing checks'}", "",
          "Next: the honest report (tuned vs untested years). Paper only. Not financial advice."]
    row = {"bot": bot, "source": source, "translated": translated, "not_translated": not_translated, "added": added,
           "check_ok": bool(chk.get("ok")), "at": datetime.now().isoformat(timespec="seconds")}
    journal.add("auto_setup", row)
    return {"bot": bot, "check": chk, "mapping_report": "\n".join(md), "needs_your_check": to_check,
            "next": f'honest_report("{bot}")'}
