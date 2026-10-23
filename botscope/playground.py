"""Rule playground: turn a bot's rules on and off and see a one-month projection for that mix, as a range from
untested history, within a second.

How it stays fast: one untested backtest per bot is run once and cached (its trades, plus every near miss with the
rule that blocked it). Turning a blocking rule OFF adds back the trades that rule blocked (played out on paper);
"longs only" / "shorts only" drop the other side. Each toggle is list math on the cache, no new backtest.

Honest limits, said on every answer: a rule's blocked trades are near misses the bot reported (NoTrade(almost=...)),
played one at a time; knock-on effects (a blocked trade using up the day's one try) aren't re-run. The month is a
range from reshuffling untested trades, with the sample size. Never one exact number, never a win %.
Not financial advice.
"""
from __future__ import annotations

import json
import random
import re
import threading
import time
from dataclasses import asdict
from pathlib import Path

from . import backtest, loader

TRADING_DAYS_MONTH = 21
SIMS = 2000
_cache: dict[str, dict] = {}
_lock = threading.Lock()


def rule_key(reason: str) -> str:
    """'range too narrow (0.15%)' -> 'range too narrow'; numbers and parentheses dropped so one rule = one key."""
    k = re.sub(r"\([^)]*\)", "", reason)
    k = re.sub(r"[-+]?\$\d[\d.,]*|[-+]?\d[\d.]*%|[-+]?\d+\.\d+R?", "#", k)   # amounts, %s and decimals; times stay
    return re.sub(r"\s+", " ", k).strip(" ,.;")


def _disk(bot_id: str):
    from . import journal
    return journal.folder() / "playground" / f"{bot_id}.json"


def _stamp(cls, a, b) -> str:
    """Changes when the bot file, the window or the cost model changes, so a stale disk cache is never used."""
    import hashlib
    src = Path(cls.source_file).read_bytes() if cls.source_file else repr(cls.params).encode()
    return hashlib.sha256(src + f"{a}{b}".encode() + json.dumps(backtest.COSTS, sort_keys=True).encode()).hexdigest()[:16]


def _load(bot_id: str, stamp: str) -> dict | None:
    try:
        d = json.loads(_disk(bot_id).read_text())
    except (OSError, ValueError):
        return None
    if d.get("stamp") != stamp:
        return None
    d["trades"] = [backtest.Trade(**t) for t in d["trades"]]
    d["ghosts"] = [backtest.Trade(**t) for t in d["ghosts"]]
    return d


def _save(c: dict) -> None:
    p = _disk(c["bot"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({**c, "trades": [asdict(t) for t in c["trades"]],
                             "ghosts": [asdict(t) for t in c["ghosts"]]}))


def precompute(bot_id: str, fetch=None) -> dict:
    """Run the untested window once (trades + ghosts with the rule that blocked each). Cached in this process and
    on disk (data/journal/playground/), so a restart stays instant until the bot file or the window changes."""
    with _lock:
        if bot_id in _cache and fetch is None:
            return _cache[bot_id]
        cls = loader.get(bot_id)
        bot = cls()
        days = 365 if bot.timeframe == "1Day" else 90
        (_, a, b), = [w for w in backtest.windows(cls, days) if w[0] == "untested"]
        stamp = _stamp(cls, a, b)
        if fetch is None and (hit := _load(loader.bot_id(cls), stamp)):
            _cache[bot_id] = hit
            return hit
        warm = backtest.warmup_days(bot, 30)
        t0 = time.time()
        trades, ghosts, problems = backtest.run_window(bot, bot.symbols[:backtest.MAX_SYMBOLS], a, b, fetch=fetch,
                                                       warmup_days=warm)
        c = {"bot": loader.bot_id(cls), "name": bot.name, "window": {"from": str(a), "to": str(b), "period": "untested"},
             "trading_days": max(1, round((b - a).days * 252 / 365)), "trades": trades, "ghosts": ghosts,
             "problems": problems[:5], "seconds": round(time.time() - t0, 1), "stamp": stamp}
        if fetch is None:
            _cache[bot_id] = c
            _save(c)
        return c


def rules(c: dict) -> list[dict]:
    by: dict[str, list] = {}
    for g in c["ghosts"]:
        by.setdefault(rule_key(g.blocked_by), []).append(g)
    return [{"rule": k, "blocked": len(gs), "blocked_total_r": round(sum(g.r for g in gs), 2),
             "newest_blocked": [{"day": g.t_in[:10], "symbol": g.symbol, "side": g.side, "r": round(g.r, 2)}
                                for g in sorted(gs, key=lambda g: g.t_in, reverse=True)[:6]]}
            for k, gs in sorted(by.items(), key=lambda kv: -len(kv[1]))]


def _usd(x: float) -> str:
    return f"{'-' if x < 0 else '+'}${abs(x):,.0f}"


def month_range(trs: list, trading_days: int, notional: float, seed: int = 7) -> dict:
    n = len(trs)
    if n < 10:
        return {"enough": False, "why": f"only {n} untested trades in this mix; need 10+ for a range"}
    per_month = n / trading_days * TRADING_DAYS_MONTH
    k = max(1, round(per_month))
    usd = [t.pct / 100 * notional for t in trs]
    rng = random.Random(seed)
    sims = sorted(sum(rng.choice(usd) for _ in range(k)) for _ in range(SIMS))
    lo, mid, hi = sims[SIMS // 20], sims[SIMS // 2], sims[SIMS * 19 // 20]
    return {"enough": True, "trades_a_month": round(per_month, 1), "bad_usd": round(lo), "middle_usd": round(mid),
            "good_usd": round(hi), "sample_trades": n,
            "text": f"a typical month: {_usd(lo)} to {_usd(hi)}, middle {_usd(mid)} (range from {n} untested "
                    f"trades, about {per_month:.0f} a month)"}


def play(bot_id: str, rules_off: list[str] | None = None, side: str = "both", position_size_usd: float = 10_000,
         fetch=None) -> dict:
    t0 = time.time()
    c = precompute(bot_id, fetch)
    off = {rule_key(r) for r in (rules_off or [])}
    known = {r["rule"] for r in rules(c)}
    unknown = off - known
    trs = list(c["trades"]) + [g for g in c["ghosts"] if rule_key(g.blocked_by) in off]
    if side in ("long", "short"):
        trs = [t for t in trs if t.side == side]
    base = month_range(c["trades"], c["trading_days"], position_size_usd)
    mix = month_range(trs, c["trading_days"], position_size_usd)
    rows = []
    for r in rules(c):
        mattered = r["blocked"] >= 3 and abs(r["blocked_total_r"]) >= 2
        r["matters"] = (("yes: it saves " if r["blocked_total_r"] < 0 else "yes: it costs ")
                        + f"{abs(r['blocked_total_r']):.1f}R over {r['blocked']} blocked trades") if mattered else \
            f"barely ({r['blocked']} blocked, {r['blocked_total_r']:+.1f}R)"
        if r["blocked"] >= 10 and r["blocked_total_r"] >= 5:      # a lead, not a verdict: test it the honest way
            r["worth_testing"] = (f"make_shadow {c['bot']}, take this rule out of the copy, then compare both on "
                                  f"paper (shadow_scoreboard) and on other days before trusting it")
        r["on"] = r["rule"] not in off
        rows.append(r)
    sides_lead = None
    both_r = sum(t.r for t in c["trades"])
    for sd in ("long", "short"):
        only = [t for t in c["trades"] if t.side == sd]
        if len(only) >= 10 and sum(t.r for t in only) - both_r >= 5:
            sides_lead = (f"{sd}s only made {sum(t.r for t in only) - both_r:+.1f}R more than both sides on these "
                          f"days ({len(only)} trades): a lead, not a fix. Test it with make_shadow (set sides = "
                          f"\"{sd}\" in the copy), on paper and on other days")
    from . import tries
    mix_id = {"playground_rules_off": sorted(off - unknown), "playground_side": side}
    tried = tries.note(c["bot"], c["window"]["from"], c["window"]["to"], None,
                       mix_id if (off - unknown or side != "both") else None)
    return {"bot": c["bot"], "name": c["name"], "window": c["window"], "side": side, "rules": rows, **tried,
            "sides_lead": sides_lead,
            "unknown_rules": sorted(unknown), "as_coded": base, "this_mix": mix,
            "total_r": round(sum(t.r for t in trs), 2), "trades": len(trs),
            "problems": c["problems"], "precompute_seconds": c["seconds"],
            "toggle_seconds": round(time.time() - t0, 3) if bot_id in _cache or fetch else None,
            "note": "Untested days only, after costs. Turning a rule off adds back the near misses it blocked, played "
                    "out on paper; knock-on effects aren't re-run. A range, not a promise. Not financial advice."}
