"""Parent view: one read-only summary for a parent (or anyone checking in): what each bot does, the safety limits,
paper vs real money, the live lock, STOP, recent paper trades and recent guard alerts. Nothing here changes a
setting: the page has no buttons, and its API only answers GET."""
from __future__ import annotations

from . import guard, journal, loader, settings


def summary(recent: int = 15) -> dict:
    from . import alerts, confidence, demo, preflight
    s = settings.load()
    bots, _ = loader.load_all()
    rows = []
    for bid, c in bots.items():
        rows.append({"id": bid, "name": c.name, "what_it_does": c.description, "rules": c.rules,
                     "symbols": c.symbols, "timeframe": c.timeframe, "status": c.status,
                     "on_today": preflight.is_on(bid) and not s["stopped"],
                     "money": "REAL money" if bid in s["live_bots"] else "paper (pretend money)",
                     "confidence": confidence.for_bot(bid)["level"]})
    trades = sorted(journal.load("paper_results"), key=lambda r: (r.get("day", ""), r.get("trade_id", "")))[-recent:]
    log = journal.load("orders_log")[-recent:]
    live_on = guard.live_switch_on()
    mode = "demo (made-up prices, no account)" if demo.active() else guard.account_mode()
    return {
        "read_only": True,
        "account": mode,
        "live_lock": ("UNLOCKED in the .env: real-money orders can be asked for, each one still needs a yes"
                      if live_on else "LOCKED: no real-money order can go through"),
        "live_lock_on": not live_on,
        "stopped": bool(s["stopped"]), "stopped_at": s["stopped_at"],
        "limits": {"max_order_usd": s["max_order_usd"], "max_orders_per_day": s["max_orders_per_day"],
                   "live_bots": s["live_bots"], "weekly_loss_budget_r": s.get("loss_budget_r")},
        "bots": rows,
        "recent_paper_trades": [{"day": r.get("day"), "bot": r.get("bot"), "symbol": r.get("symbol"),
                                 "side": r.get("side"), "r": r.get("r"), "why_out": r.get("why_out")}
                                for r in reversed(trades)],
        "recent_alerts": [{"when": r.get("saved_at"), "source": r.get("source"), "decision": r.get("decision"),
                           "reason": r.get("reason")} for r in reversed(log)],
        "alert_channels_on": [k for k, v in alerts.channels().items() if v],
        "note": ("Read only: nothing on this page can change a setting or place an order. Results are in R "
                 "(1R = the amount a trade risked). Paper trades use pretend money. Not financial advice."),
    }
