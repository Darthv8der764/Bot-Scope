"""Size by risk: "risk 1% per trade" turned into a share count (paper). Information only, never an order.

shares = (account x risk %) / (entry - stop distance), rounded down, and never more than the account can buy
without borrowing. If the stop is very close, the cap kicks in and the real risk is smaller than asked.
"""
from __future__ import annotations

import math


def shares_for(entry: float, stop: float, account_usd: float = 10_000, risk_pct: float = 1.0) -> dict:
    if entry <= 0 or account_usd <= 0 or not 0 < risk_pct <= 10:
        raise ValueError("entry and account must be above 0, and risk between 0 and 10% a trade")
    per_share = abs(entry - stop)
    if per_share == 0:
        raise ValueError("the stop is at the entry price, so there's no risk to size from")
    budget = account_usd * risk_pct / 100
    by_risk = math.floor(budget / per_share)
    by_cash = math.floor(account_usd / entry)
    shares = min(by_risk, by_cash)
    capped = by_cash < by_risk
    return {"shares": shares, "position_usd": round(shares * entry, 2), "risk_usd": round(shares * per_share, 2),
            "risk_budget_usd": round(budget, 2), "risk_per_share": round(per_share, 4), "capped_by_cash": capped,
            "explain": (f"Risking {risk_pct:g}% of ${account_usd:,.0f} = ${budget:,.2f}. The stop is ${per_share:.2f} "
                        f"away, so {by_risk} shares" + (f", but ${account_usd:,.0f} only buys {by_cash}: "
                                                        f"real risk ${shares * per_share:,.2f}" if capped else "") + "."),
            "note": "Paper sizing only. Gaps can jump past a stop, so the loss can be bigger. Not financial advice."}
