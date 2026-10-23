"""The order guard: every order BotScope (or Claude, through the plugin's hook) might send goes through check_order
first. Paper is the default. LIVE money is blocked unless ALL of these are true:

  1. the live switch is on in your own .env (BOTSCOPE_LIVE_TRADING=1),
  2. for a bot's order: that bot passed the graduation test and you switched it to live,
  3. the order size is known and under the cap (max_order_usd, default $1,000),
and even then the answer is "ask": real money always needs your yes. STOP everything blocks every order, paper too,
and a runaway brake blocks more than max_orders_per_day orders a day.

As a Claude Code hook (PreToolUse on the Alpaca MCP's order tools) it reads the tool call on stdin:
    .venv/bin/python -m botscope.guard
Paper or live is read from BOTSCOPE_ACCOUNT (paper|live) if set, else from the key: Alpaca paper key IDs start with
"PK", live ones with "AK". Anything else counts as live (the safe guess).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from . import journal, settings
from .env import key

ORDER_TOOLS = ("place_stock_order", "place_crypto_order", "place_option_order", "replace_order_by_id",
               "exercise_options_position")


def account_mode() -> str:
    forced = key("BOTSCOPE_ACCOUNT").lower()
    if forced in ("paper", "live"):
        return forced
    k = key("ALPACA_API_KEY")
    return "paper" if k.startswith("PK") else "live"


def live_switch_on() -> bool:
    return key("BOTSCOPE_LIVE_TRADING") == "1"


def _today_orders() -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    return sum(1 for r in journal.load("orders_log")
               if r.get("saved_at", "").startswith(today) and r.get("decision") != "deny")


def _f(x):
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def order_size(order: dict) -> float | None:
    """Dollar size if it can be known from the order itself: notional, or qty x limit/stop price (x100 for options)."""
    if (n := _f(order.get("notional"))) is not None:
        return n
    qty, px = _f(order.get("qty") or order.get("quantity")), _f(order.get("limit_price") or order.get("stop_price"))
    if qty is None or px is None:
        return None
    mult = 100 if order.get("kind") == "option" else 1
    return abs(qty * px * mult)


def check_order(order: dict, bot: str | None = None, mode: str | None = None) -> dict:
    """{decision: allow|ask|deny, reason, mode}. Never sends anything."""
    s = settings.load()
    mode = mode or account_mode()
    if s["stopped"]:
        return {"decision": "deny", "mode": mode, "reason": "STOP is on: every order is blocked until you resume"}
    if _today_orders() >= s["max_orders_per_day"]:
        return {"decision": "deny", "mode": mode,
                "reason": f"runaway brake: already {s['max_orders_per_day']} orders today (max_orders_per_day)"}
    if mode == "paper":
        return {"decision": "allow", "mode": mode, "reason": "paper account"}
    if not live_switch_on():
        return {"decision": "deny", "mode": mode,
                "reason": "LIVE money is locked: the live switch is off (BOTSCOPE_LIVE_TRADING=1 in your own .env)"}
    if bot and bot not in s["live_bots"]:
        return {"decision": "deny", "mode": mode,
                "reason": f"bot '{bot}' is not switched to live (it must pass the graduation test first)"}
    size = order_size(order)
    if size is None:
        return {"decision": "deny", "mode": mode,
                "reason": "can't tell the order's dollar size; use a limit price or a dollar amount (notional)"}
    if size > s["max_order_usd"]:
        return {"decision": "deny", "mode": mode,
                "reason": f"order is ${size:,.0f}, over the ${s['max_order_usd']:,.0f} live size cap"}
    return {"decision": "ask", "mode": mode,
            "reason": f"REAL MONEY: {order.get('side', '')} {order.get('symbol', '')} about ${size:,.0f}. Confirm?"}


def stop_everything(reason: str = "") -> dict:
    settings.change(stopped=True, stopped_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    journal.add("orders_log", {"source": "STOP", "decision": "deny", "mode": "-", "reason": reason})
    from . import alerts
    alerts.send("BotScope: STOP pressed", "Every order is blocked and every bot is off until you resume.", "octagonal_sign",
                demo_ok=True)
    return {"stopped": True, "note": "Every order is now blocked (paper and live) and every bot is treated as OFF "
                                     "until you resume. Open positions are NOT closed; ask if you want that."}


def resume(confirm: bool = False) -> dict:
    if not confirm:
        return {"question": "Resume? Bots go back to today's on/off list and orders are allowed again.",
                "needs": "confirm=true", "still_stopped": True}
    settings.change(stopped=False, stopped_at=None)
    return {"stopped": False}


def record(order: dict, decision: dict, source: str) -> None:
    journal.add("orders_log", {"source": source, "decision": decision["decision"], "mode": decision["mode"],
                               "symbol": order.get("symbol"), "side": order.get("side"),
                               "size_usd": order_size(order)})


def hook(event: dict) -> dict | None:
    """Claude Code PreToolUse hook: deny or ask for order tools; None = not an order tool (let it through)."""
    tool = event.get("tool_name", "")
    if not any(tool.endswith(t) for t in ORDER_TOOLS):
        return None
    order = dict(event.get("tool_input") or {})
    if "option" in tool:
        order["kind"] = "option"
    d = check_order(order)
    record(order, d, "claude hook")
    if d["decision"] == "allow":
        return None
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": d["decision"],
                                   "permissionDecisionReason": "BotScope guard: " + d["reason"]}}


def main():
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        event = {}
    try:
        out = hook(event)
    except Exception as e:        # a broken guard must fail closed for order tools
        if any(str(event.get("tool_name", "")).endswith(t) for t in ORDER_TOOLS):
            out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                          "permissionDecisionReason": f"BotScope guard error, blocked to be safe: {e}"}}
        else:
            out = None
    if out:
        print(json.dumps(out))


if __name__ == "__main__":
    main()
