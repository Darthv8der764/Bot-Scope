"""The full honest report: one bot across many years, split into TUNED years (where its settings were picked, so it
is expected to look good) and UNTESTED years (the real test), with real trading costs, a range of outcomes, the
worst losing streak, near misses (ghost trades) and the crash time machine.

Data: Alpaca, downloaded with the user's own keys. Alpaca's US stock history starts in 2016, so anything earlier
(like 2008) cannot be tested and the report says so instead of guessing. To stay light, intraday bots test one
sample month per year (the month rotates Jan/Apr/Jul/Oct so every season shows up); daily bots test whole years.
Not financial advice: past results do not predict the future.
"""
from __future__ import annotations

import calendar
import json
from datetime import date, timedelta

from . import backtest, benchmark, confidence, data, journal, loader

DATA_START = date(2016, 1, 1)          # Alpaca's US stock history starts here
ALPACA_CRYPTO_START = date(2021, 1, 1)  # Alpaca's crypto history starts here (Coinbase's goes back further)
SAMPLE_MONTHS = (1, 4, 7, 10)          # intraday: one month per year, rotating by year
DAILY_WARMUP = 30                      # calendar days of history fetched before a daily bot's window

CRASHES = [
    {"name": "2008 financial crisis", "from": "2008-09-01", "to": "2008-11-28",
     "what_happened": "Lehman Brothers failed; the S&P 500 fell about 30% in three months"},
    {"name": "Q4 2018 sell-off", "from": "2018-10-01", "to": "2018-12-24",
     "what_happened": "rate-hike and trade-war fears; the S&P 500 fell almost 20%"},
    {"name": "2020 covid crash", "from": "2020-02-19", "to": "2020-04-30",
     "what_happened": "the fastest 30%+ drop on record (Feb 19 to Mar 23), then a sharp rebound"},
    {"name": "2022 bear market", "from": "2022-04-01", "to": "2022-06-30",
     "what_happened": "inflation and fast rate hikes; the S&P 500's worst quarter of 2022 (about -16%)"},
]
NO_DATA = ("not tested: Alpaca's stock data starts in 2016, and BotScope only uses data you download with your own "
           "keys. The earliest crash it can show is Q4 2018.")
CRYPTO_NO_DATA = ("not tested: Alpaca's crypto history starts in 2021. Set BOTSCOPE_CRYPTO_DATA=coinbase in your .env "
                  "for older crypto candles.")


def _yesterday(today: date | None = None) -> date:
    return (today or date.today()) - timedelta(days=1)


def _tuned(bot_cls, a: date, b: date) -> bool:
    if not bot_cls.tuned_on:
        return False
    t0, t1 = (date.fromisoformat(x) for x in bot_cls.tuned_on)
    return a <= t1 and b >= t0


def data_start(bot_cls) -> date:
    """First day with candles for this bot: crypto from Alpaca starts in 2021, so earlier years aren't 'untested
    years with no trades' (that would flatter or sink the bot against holding SPY); they're left out."""
    from . import brokers, demo
    if getattr(bot_cls, "asset", "") == "crypto" and not demo.active() and brokers.crypto_source() == "alpaca":
        return ALPACA_CRYPTO_START
    return DATA_START


def warming_up_years(bot, by_year: list[dict], warm: int) -> list[int]:
    """Years whose warmup reaches back before the data starts, for a bot with a declared lookback."""
    if bot.timeframe != "1Day" or not getattr(bot, "lookback_days", 0):
        return []
    return [r["year"] for r in by_year
            if date.fromisoformat(str(r["from"])) - timedelta(days=warm) < data_start(type(bot))]


def year_windows(bot_cls, today: date | None = None) -> list[dict]:
    """[{year, from, to, period: tuned|untested}] from 2016 to yesterday."""
    end_all = _yesterday(today)
    out = []
    for y in range(data_start(bot_cls).year, end_all.year + 1):
        if bot_cls.timeframe == "1Day":
            a, b = date(y, 1, 1), date(y, 12, 31)
        else:
            m = SAMPLE_MONTHS[y % 4]
            a, b = date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
            if a > end_all:                       # this year's sample month hasn't happened yet: use the last full month
                m = (end_all.replace(day=1) - timedelta(days=1)).month
                a, b = date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
        b = min(b, end_all)
        if a > b:
            continue
        out.append({"year": y, "from": a, "to": b, "period": "tuned" if _tuned(bot_cls, a, b) else "untested"})
    return out


def _row(label: str, w: dict, trades, ghosts, notional, fetch=None) -> dict:
    s = backtest.summarize(trades, notional)
    vs = benchmark.compare(s.get("net_usd"), w["from"], w["to"], notional, fetch)
    return {label: w[label], "period": w["period"], "from": str(w["from"]), "to": str(w["to"]),
            "trades": s.get("trades", 0), "net_usd": s.get("net_usd", 0.0),
            "spy_hold_usd": vs["spy_hold"].get("usd"), "beat_holding": vs["beat_holding"], "beat": vs["beat"],
            "avg_r": s.get("avg_r"), "total_r": s.get("total_r"),
            "worst_losing_streak": s.get("worst_losing_streak"), "max_drawdown_r": s.get("max_drawdown_r"),
            "near_misses": len(ghosts)}


def _verdict(s: dict) -> str:
    n = s.get("trades", 0)
    if not n:
        return "no trades"
    if s["total_r"] > 0:
        return f"made {s['total_r']:+.1f}R" + (" (few trades)" if n < 10 else "")
    return f"lost {s['total_r']:+.1f}R" + (" (few trades)" if n < 10 else "")


def crash_test(bot_cls, symbols: list[str] | None = None, notional: float = 10_000, fetch=None,
               params: dict | None = None) -> dict:
    """The crash time machine: run the bot through the big drops. Crashes before the data starts are listed as
    not tested, never guessed."""
    bot = bot_cls(**(params or {}))
    symbols = [s.upper() for s in (symbols or bot.symbols)][:backtest.MAX_SYMBOLS]
    warm = backtest.warmup_days(bot, DAILY_WARMUP)
    rows, problems = [], []
    for c in CRASHES:
        a, b = date.fromisoformat(c["from"]), date.fromisoformat(c["to"])
        base = {"crash": c["name"], "from": c["from"], "to": c["to"], "what_happened": c["what_happened"]}
        if a < data_start(bot_cls):
            rows.append(base | {"tested": False, "result": NO_DATA if data_start(bot_cls) == DATA_START else
                                CRYPTO_NO_DATA}); continue
        trades, ghosts, probs = backtest.run_window(bot, symbols, a, b, fetch=fetch, warmup_days=warm)
        problems += probs
        s = backtest.summarize(trades, notional)
        rows.append(base | {"tested": True, "period": "tuned" if _tuned(bot_cls, a, b) else "untested",
                            "trades": s.get("trades", 0), "avg_r": s.get("avg_r"), "total_r": s.get("total_r"),
                            "worst_losing_streak": s.get("worst_losing_streak"),
                            "max_drawdown_r": s.get("max_drawdown_r"), "result": _verdict(s)})
    tested = [r for r in rows if r["tested"]]
    lost = [r for r in tested if (r.get("total_r") or 0) < 0]
    return {"bot": bot.name, "symbols": symbols, "data": data_line(symbols),
            "crashes": rows, "problems": problems[:20],
            "summary": (f"tested {len(tested)} of {len(rows)} crashes; lost money in {len(lost)}" if tested else
                        "no crash could be tested"),
            "note": "A crash test shows how bad it got, not how it will go next time. Not financial advice."}


def full_report(bot_cls, symbols: list[str] | None = None, notional: float = 10_000, fetch=None,
                crashes: bool = True, today: date | None = None, save: bool = True) -> dict:
    """Every year since the data starts, tuned vs untested, with costs, range, streaks, near misses and crashes."""
    bot = bot_cls()
    bid = loader.bot_id(bot_cls)
    asked = list(symbols or bot.symbols)
    symbols = [s.upper() for s in asked][:backtest.MAX_SYMBOLS]
    warm = backtest.warmup_days(bot, DAILY_WARMUP)
    by_year, pools, ghost_pool, problems, peek = [], {"tuned": [], "untested": []}, [], [], {}
    if (lo := backtest.left_out(asked)):
        problems.append(lo)
    for w in year_windows(bot_cls, today):
        trades, ghosts, probs = backtest.run_window(bot, symbols, w["from"], w["to"], fetch=fetch, peek=peek,
                                                    warmup_days=warm)
        problems += probs
        pools[w["period"]] += trades
        ghost_pool += ghosts
        by_year.append(_row("year", w, trades, ghosts, notional, fetch))
    if peek.get("problem"):
        problems.insert(0, peek["problem"])
    tuned, untested = (backtest.summarize(pools[k], notional) for k in ("tuned", "untested"))
    years = {"tuned": [r["year"] for r in by_year if r["period"] == "tuned"],
             "untested": [r["year"] for r in by_year if r["period"] == "untested"]}
    losing_years = [r["year"] for r in by_year if r["period"] == "untested" and (r["total_r"] or 0) < 0]
    out = {
        "bot": bot.name, "version": bot.version, "status": bot.status, "symbols": symbols, "timeframe": bot.timeframe,
        "data": data_line(symbols),
        "sample": ("whole years" if bot.timeframe == "1Day" else
                   "one month per year (Jan/Apr/Jul/Oct, rotating) to keep it light"),
        "tuned_on": bot_cls.tuned_on, "years": years, "position_size_usd": notional,
        "costs_bps": backtest.COSTS[bot.asset], "tuned": tuned, "untested": untested,
        "by_year": by_year, "losing_untested_years": losing_years,
        "near_misses": backtest.ghost_summary(ghost_pool),
        "problems": problems[:20],
    }
    short = warming_up_years(bot, by_year, warm)
    if short:
        out["warming_up_years"] = short
        out["warming_up_note"] = (f"{', '.join(map(str, short))}: the bot needs {bot.lookback_days} earlier trading days, "
                                  f"but the data starts in {data_start(type(bot)).year}, so it can only trade once they have built "
                                  "up (fewer trades that year)")
    if untested.get("trades") and save:
        journal.upsert("backtests", {"bot": bid},
                       {"untested": untested, "untested_rs": [t.r for t in pools["untested"]], "symbols": symbols,
                        "version": bot.version, "source": "full report"})
    out["vs_spy"] = vs_spy(by_year)
    if symbols and all(data.is_crypto(x) for x in symbols):
        out["vs_btc"] = vs_btc(by_year, notional, backtest.COSTS["crypto"], fetch)
    out["confidence"] = confidence.for_bot(bid) if save else confidence.meter(untested)
    if crashes:
        ct = crash_test(bot_cls, symbols, notional, fetch)
        out["crashes"] = ct["crashes"]; out["problems"] += ct["problems"]
    out["headline"] = headline(out)
    out["note"] = ("TUNED years: the settings were picked there, so expect them to look good. UNTESTED years: the "
                   "real test. Costs are already taken out. Not financial advice.")
    if not save:                                  # strategy-factory candidates: nothing saved to the journal
        out["untested_entries"] = sorted({(t.symbol, t.t_in[:10]) for t in pools["untested"]})
        return out
    journal.upsert("reports", {"bot": bid}, {k: v for k, v in out.items() if k not in ("problems", "bot")}
                   | {"bot_name": bot.name, "untested_rs": [t.r for t in pools["untested"]],
                      "bot_file_hash": fingerprint(bot)})
    return out


def vs_spy(by_year: list[dict]) -> dict:
    """Untested years only: did the bot beat simply holding SPY with the same money?"""
    rows = [r for r in by_year if r["period"] == "untested" and r.get("spy_hold_usd") is not None]
    if not rows:
        return {"summary": "can't compare with SPY (no SPY data for the untested years)", "note": benchmark.NOTE}
    bot, spy = sum(r["net_usd"] for r in rows), sum(r["spy_hold_usd"] for r in rows)
    beat = sum(bool(r["beat"]) for r in rows)
    return {"untested_years": len(rows), "years_beat": beat, "bot_usd": round(bot, 2), "spy_usd": round(spy, 2),
            "summary": f"beat just holding SPY in {beat} of {len(rows)} untested years "
                       f"(bot {benchmark.usd(bot)} vs SPY {benchmark.usd(spy)} over the same days)",
            "note": benchmark.NOTE}


def data_line(symbols: list[str]) -> str:
    """Names where the candles came from: stocks from Alpaca SIP, crypto from the crypto data source in use."""
    from . import brokers, demo
    if demo.active():                    # every candle is made up in demo mode, crypto included
        return demo.SOURCE
    stocks = "Alpaca SIP (all US exchanges), downloaded with your own keys"
    crypto = {"alpaca": "Alpaca crypto history (no keys needed)",
              "coinbase": "Coinbase public candles (no keys needed)"}.get(brokers.crypto_source(), brokers.crypto_source())
    kinds = {data.is_crypto(x) for x in symbols}
    return crypto if kinds == {True} else stocks if kinds != {True, False} else f"{stocks}; crypto: {crypto}"


def vs_btc(by_year: list[dict], notional: float = 10_000, costs: dict | None = None, fetch=None) -> dict:
    """Crypto-only bots, untested years only: did the bot beat simply holding bitcoin with the same money?"""
    rt = (costs or {}).get("entry_bps", 0) + (costs or {}).get("exit_bps", 0)
    rows = []
    for r in by_year:
        if r["period"] != "untested":
            continue
        h = benchmark.hold(benchmark.CRYPTO_SYMBOL, date.fromisoformat(r["from"]), date.fromisoformat(r["to"]),
                           notional, fetch, cost_bps=rt)
        if "usd" in h:
            rows.append((r["net_usd"], h["usd"]))
    if not rows:
        return {"summary": "can't compare with BTC (no BTC data for the untested years)", "note": benchmark.CRYPTO_NOTE}
    bot, btc = sum(a for a, _ in rows), sum(b for _, b in rows)
    beat = sum(a - b > benchmark.SAME_PCT / 100 * notional for a, b in rows)
    return {"untested_years": len(rows), "years_beat": beat, "bot_usd": round(bot, 2), "btc_usd": round(btc, 2),
            "summary": f"beat just holding BTC in {beat} of {len(rows)} untested years "
                       f"(bot {benchmark.usd(bot)} vs BTC {benchmark.usd(btc)} over the same days)",
            "note": benchmark.CRYPTO_NOTE}


tight_stops = backtest.tight_stops     # (kept here too: the factory and headline call report.tight_stops)


def headline(r: dict) -> str:
    u = r["untested"]
    if not u.get("trades"):
        return "No trades on untested years, so there is nothing honest to say yet."
    parts = [f"{u['trades']} untested trades over {len(r['years']['untested'])} years: "
             f"{u['avg_r']:+.2f}R per trade after costs ({u['total_r']:+.1f}R total)"]
    if "total_r_range_5_50_95" in u:
        lo, mid, hi = u["total_r_range_5_50_95"]
        parts.append(f"range {lo:+.0f}R to {hi:+.0f}R")
    parts.append(f"worst losing streak {u['worst_losing_streak']}")
    if tight_stops(u):
        parts.append(f"⚠ {tight_stops(u)}: judge this bot by dollars ({benchmark.usd(u['net_usd'])}) and widen its stop")
    if r["losing_untested_years"]:
        parts.append(f"lost money in {len(r['losing_untested_years'])} of {len(r['years']['untested'])} untested years")
    if r.get("vs_spy", {}).get("years_beat") is not None:
        parts.append(r["vs_spy"]["summary"])
    if r.get("vs_btc", {}).get("years_beat") is not None:
        parts.append(r["vs_btc"]["summary"])
    return "; ".join(parts) + "."


def _code_only(src: bytes) -> bytes:
    """The bot file without its docstrings and comments, so writing results or notes into it isn't a change."""
    import ast
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body
                and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.dump(tree).encode()


def fingerprint(bot, code_only: bool = True) -> str | None:
    """A short fingerprint of the bot's code and the trading-cost model, saved with the report so the label can tell
    when either changed since (both move every number on it). Docstrings and comments don't count."""
    import hashlib
    from pathlib import Path
    f = Path(getattr(bot, "source_file", "") or "")
    if not f.is_file():
        return None
    src = _code_only(f.read_bytes()) if code_only else f.read_bytes()
    return hashlib.sha256(src + json.dumps(backtest.COSTS, sort_keys=True).encode()).hexdigest()[:16]


def changed_since(bot_cls, rep: dict | None = None) -> bool:
    """True when the bot code changed after its saved report (False for no report or one saved before fingerprints).
    Reports saved before docstrings were ignored carry a whole-file fingerprint, so that one still matches too."""
    rep = saved(bot_cls) if rep is None else rep
    old, now = (rep or {}).get("bot_file_hash"), fingerprint(bot_cls)
    return bool(old and now and old not in (now, fingerprint(bot_cls, code_only=False)))


def saved(bot_cls) -> dict | None:
    """The last full report saved on this computer (for the nutrition label), or None."""
    rows = journal.find("reports", bot=loader.bot_id(bot_cls))
    return rows[-1] if rows else None
