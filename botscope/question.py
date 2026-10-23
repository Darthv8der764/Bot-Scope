"""Ask a market question: a plain-English one-off question ("how did buying SPY on red Mondays do?") becomes a
small daily bot in memory, run through the same honest report as any bot: every year since the data starts, real
costs, trade count, vs just holding SPY and a confidence level (counts and R only). No bot file is written.

The idea came from a person, and people notice patterns in what just happened. So by default the last 12 months
count as TUNED (where you probably saw it) and only older years are the real test. Say `idea_from="elsewhere"` when
the idea didn't come from looking at recent prices.

Understood (daily candles, all conditions must hold on the day that just closed; buy or short at that close):
  weekdays ("on Mondays"), red / green days (close below / above the open), N down / up days in a row,
  gap down / gap up (open vs the day before's close), down / up X% (close vs the day before's close),
  new N-day high / low (close), above / below the N-day average.
  Hold: "hold 5 days", "for a week", "next day" (default 1 trading day). Stop: "stop 2%" (default 3%).
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from . import journal, report
from .bot import Bot, Entry, Exit, NoTrade

DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")   # weekends: crypto only
KNOWN = {"spy", "qqq", "iwm", "dia", "aapl", "msft", "nvda", "tsla", "amzn", "meta", "googl", "amd", "xlf", "xle",
         "tlt", "gld", "smh", "btc/usd", "eth/usd"}
CRYPTO_NAMES = {"bitcoin": "BTC/USD", "btc": "BTC/USD", "BTC": "BTC/USD", "ether": "ETH/USD", "ethereum": "ETH/USD",
                "eth": "ETH/USD", "ETH": "ETH/USD"}
UNIT_DAYS = {"day": 1, "week": 5, "month": 21, "year": 252}          # trading days: a 52-week high = a 260-day high
NOT_TICKERS = {"I", "A", "R", "ET", "US", "USD", "ETF", "RSI", "AM", "PM", "OK", "IF", "SO", "THE", "AND", "OR"}
DEFAULT_STOP_PCT, DEFAULT_HOLD, NOTICED_DAYS = 3.0, 1, 365
EXAMPLES = ["how did buying SPY on red Mondays do?", "buy QQQ after 3 down days in a row, hold 5 days",
            "short IWM when it gaps up 1%", "buy SPY at a new 20-day high, hold a month, stop 5%"]
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _num(s: str) -> float:
    return float(WORDS.get(s, s))


def parse(text: str) -> dict:
    """{symbols, side, conds[], hold_days, stop_pct, rules[], not_understood?} from the question's words."""
    raw = text.strip()
    t = " " + re.sub(r"\s+", " ", raw.lower().replace("’", "'")) + " "
    num = r"(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten)"
    syms = [w for w in re.findall(r"\b[A-Z]{1,5}(?:/USD)?\b", raw) if w not in NOT_TICKERS]
    syms += [w.upper() for w in re.findall(r"[a-z]+(?:/usd)?", t) if w in KNOWN]
    syms = [CRYPTO_NAMES.get(w.lower(), w) for w in syms]
    syms += [CRYPTO_NAMES[w] for w in re.findall(r"[a-z]+", t) if w in CRYPTO_NAMES and CRYPTO_NAMES[w] not in syms]
    symbols = list(dict.fromkeys(syms))[:5] or ["SPY"]
    side = "short" if re.search(r"\bshort(ing|ed)?\b|\bbet(ting)? against\b", t) or any(
        re.search(rf"\bsell(?:ing)? {re.escape(x.lower())}\b", t) for x in symbols) else "long"   # "sell SPY when ..." 
    conds, rules = [], []
    wd = [i for i, d in enumerate(DAYS) if re.search(rf"\b{d}s?\b", t)]
    weekend_note = None
    if any(i >= 5 for i in wd) and not all("/" in x for x in symbols):   # stocks never trade on weekends
        wd = [i for i in wd if i < 5]
        weekend_note = ("stocks don't trade on Saturdays or Sundays (only crypto does), so "
                        + ("those days were left out" if wd else "there's nothing to test: try a weekday or BTC/ETH"))
    if wd:
        conds.append(("weekday", wd)); rules.append("the day is a " + " or ".join(DAYS[i].title() for i in wd))
    if m := re.search(rf"\b{num} (down|red|losing|up|green) days?( in a row)?", t):
        n, kind = int(_num(m.group(1))), m.group(2)
        down = kind in ("down", "red", "losing")
        conds.append(("streak", n, down)); rules.append(f"{n} {'down' if down else 'up'} closes in a row")
    elif re.search(r"\b(red|down) (day|close|monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b|\bred\b|\bcloses? red\b", t):
        conds.append(("candle", "red")); rules.append("the day closed red (below its open)")
    elif re.search(r"\b(green|up) (day|close|monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b|\bgreen\b|\bcloses? green\b", t):
        conds.append(("candle", "green")); rules.append("the day closed green (above its open)")
    if m := re.search(rf"\bgaps? (down|up)(?: (?:by |over |more than )?{num}%)?", t):
        pct = float(m.group(2) or 0)
        conds.append(("gap", m.group(1), pct))
        rules.append(f"it opened {'below' if m.group(1) == 'down' else 'above'} the day before's close"
                     + (f" by {pct:g}%+" if pct else ""))
    elif m := re.search(rf"\b(falls?|drops?|down|loses?|sinks?|rises?|jumps?|up|gains?) (?:by |over |more than )?{num}%", t):
        down = m.group(1).rstrip("s") in ("fall", "drop", "down", "lose", "sink")
        pct = float(_num(m.group(2)))
        conds.append(("move", down, pct)); rules.append(f"it closed {pct:g}%+ {'below' if down else 'above'} the day before's close")
    elif m := re.search(rf"\b{num}% (drop|fall|decline|loss|down day|gain|rise|jump|pop|up day)", t):
        down = m.group(2) in ("drop", "fall", "decline", "loss", "down day")
        pct = float(_num(m.group(1)))
        conds.append(("move", down, pct)); rules.append(f"it closed {pct:g}%+ {'below' if down else 'above'} the day before's close")
    if m := re.search(rf"\bnew {num}[- ](day|week|month|year) (high|low)", t):
        n, hl = int(_num(m.group(1))) * UNIT_DAYS[m.group(2)], m.group(3)
        conds.append(("extreme", n, hl)); rules.append(f"the close is a new {n}-day {hl}"
                                                       + (f" ({m.group(1)}-{m.group(2)})" if m.group(2) != "day" else ""))
    if m := re.search(rf"\b(above|below|under|over) (?:the |its )?{num}[- ](day|week|month) (?:moving )?average", t):
        n, above = int(_num(m.group(2))) * UNIT_DAYS[m.group(3)], m.group(1) in ("above", "over")
        conds.append(("avg", n, above)); rules.append(f"the close is {'above' if above else 'below'} the {n}-day average")
    hold = DEFAULT_HOLD
    if m := re.search(rf"\b(?:hold(?:ing)?|for|sell after|exit after) (?:it )?(?:for )?{num} (?:trading )?days?", t):
        hold = int(_num(m.group(1)))
    elif re.search(r"\b(a|one) week\b", t):
        hold = 5
    elif re.search(r"\b(a|one) month\b", t):
        hold = 21
    stop = DEFAULT_STOP_PCT
    if m := re.search(rf"\bstop (?:at |of )?{num}%|\b{num}% stop", t):
        stop = float(_num(m.group(1) or m.group(2)))
    hold, stop = max(1, min(hold, 60)), max(0.25, min(stop, 25.0))
    out = {"symbols": symbols, "side": side, "conds": conds, "hold_days": hold, "stop_pct": stop,
           "rules": [f"{'Short' if side == 'short' else 'Buy'} {', '.join(symbols)} at the close when: "
                     + (" and ".join(rules) if rules else "(no condition understood)") + ".",
                     f"{'Cover' if side == 'short' else 'Sell'} at the close {hold} trading day{'s' if hold > 1 else ''} later, or at a {stop:g}% stop."]}
    if re.search(r"\b(minute|minutes|hour|open(ing)? range|first \d+|vwap|premarket|after hours)\b", t):
        out["not_understood"] = "intraday questions (minutes, the opening range, VWAP) aren't supported yet: daily candles only"
    if weekend_note and not wd:
        out["conds"] = []                              # never quietly widen "red Sundays" to every red day
    if weekend_note:
        out["not_understood"] = "; ".join(x for x in (out.get("not_understood"), weekend_note) if x)
    return out


def make_bot(q: dict, today: date | None = None, idea_from: str = "recent") -> type[Bot]:
    """A one-off daily Bot class for the parsed question (kept in memory, never saved as a file)."""
    conds, side, hold, stop_pct = q["conds"], q["side"], q["hold_days"], q["stop_pct"]
    look = max([c[1] for c in conds if c[0] in ("streak", "extreme", "avg")] + [1]) + 5
    end = today or date.today()

    def ok(bars) -> str | None:
        b, prev = bars[-1], bars[-2]
        closes = [x.c for x in bars]
        for c in conds:
            if c[0] == "weekday" and b.t.weekday() not in c[1]:
                return f"not a {' / '.join(DAYS[i].title() for i in c[1])}"
            if c[0] == "candle" and not (b.c < b.o if c[1] == "red" else b.c > b.o):
                return f"the day wasn't {c[1]}"
            if c[0] == "streak":
                n, down = c[1], c[2]
                if len(closes) <= n or not all((closes[-k] < closes[-k - 1]) if down else (closes[-k] > closes[-k - 1])
                                               for k in range(1, n + 1)):
                    return f"not {n} {'down' if down else 'up'} days in a row"
            if c[0] == "gap":
                g = (b.o / prev.c - 1) * 100
                hit = (g < 0 and -g >= c[2]) if c[1] == "down" else (g > 0 and g >= c[2])
                if not hit:
                    return f"no gap {c[1]} ({g:+.2f}%)"
            if c[0] == "move":
                mv = (b.c / prev.c - 1) * 100
                if (c[1] and mv > -c[2]) or (not c[1] and mv < c[2]):
                    return f"moved {mv:+.2f}%"
            if c[0] == "extreme":
                n, hi = c[1], c[2] == "high"
                if len(closes) < n or closes[-1] != (max if hi else min)(closes[-n:]):
                    return f"not a new {n}-day {c[2]}"
            if c[0] == "avg":
                n, above = c[1], c[2]
                if len(closes) < n:
                    return "not enough days yet"
                a = sum(closes[-n:]) / n
                if (closes[-1] > a) != above:
                    return f"{'below' if above else 'above'} the {n}-day average"
        return None

    class Question(Bot):
        name = "Market question"
        description = "A one-off question turned into rules (not a saved bot)."
        rules = q["rules"]
        symbols = q["symbols"]
        timeframe = "1Day"
        sides = side
        asset = "crypto" if all("/" in s for s in q["symbols"]) else "swing"
        flat_by_close = False
        lookback_days = look
        params = {"hold_days": hold, "stop_pct": stop_pct}
        tuned_on = (str(end - timedelta(days=NOTICED_DAYS)), str(end)) if idea_from == "recent" else None
        status = "untested"

        def entry(self, view):
            if len(view.bars) < 2:
                return NoTrade("not enough days yet")
            why = ok(view.bars)
            if why:
                return NoTrade(why)
            c = view.last.c
            s = c * (1 - stop_pct / 100) if side == "long" else c * (1 + stop_pct / 100)
            return Entry(side, s, None, "the question's conditions all held")

        def exit(self, view, pos):
            held = sum(1 for b in view.bars if b.t > pos.entry_time)
            return Exit(f"held {held} trading day{'s' if held > 1 else ''}") if held >= hold else None
    return Question


def ask(text: str, idea_from: str = "recent", notional: float = 10_000, fetch=None, today: date | None = None) -> dict:
    """Parse the question, run the honest report on it (nothing saved as a bot) and answer in counts and R."""
    q = parse(text)
    if not q["conds"]:
        return {"error": "I couldn't turn that into a rule I can test.", "understood": q["rules"],
                "try_one_like": EXAMPLES, "not_understood": q.get("not_understood")}
    cls = make_bot(q, today, idea_from)
    rep = report.full_report(cls, q["symbols"], notional, fetch=fetch, crashes=False, save=False, today=today)
    u, tuned = rep["untested"], rep["tuned"]
    key = " | ".join(q["rules"])
    journal.upsert("questions", {"rules": key}, {"question": text[:200], "symbols": q["symbols"]})
    asked = len(journal.load("questions"))
    years = rep["years"]
    keep = ("trades", "avg_r", "total_r", "net_usd", "costs_usd", "costs_r", "if_costs_doubled_r",
            "without_best_3_r", "total_r_range_5_50_95", "worst_losing_streak", "max_drawdown_r")
    out = {"question": text, "understood_as": q["rules"], "symbols": q["symbols"], "data": rep["data"],
           "tuned_years": years["tuned"], "untested_years": years["untested"],
           "tuned_note": (f"TUNED: the last {NOTICED_DAYS} days ({', '.join(map(str, years['tuned']))}), where you "
                          "probably noticed the idea, so they're expected to look good. Pass idea_from='elsewhere' "
                          "if the idea didn't come from recent prices." if idea_from == "recent" else
                          "No tuned years: you said the idea didn't come from looking at these prices."),
           "untested": {k: u[k] for k in keep if k in u}, "tuned": {k: tuned[k] for k in keep if k in tuned},
           "by_year": [{k: r.get(k) for k in ("year", "period", "trades", "avg_r", "total_r", "net_usd", "spy_hold_usd")}
                       for r in rep["by_year"]],
           "vs_spy": rep["vs_spy"], "confidence": rep["confidence"], "headline": rep["headline"],
           "questions_asked": asked, "position_size_usd": notional, "problems": rep["problems"][:5]}
    if rep.get("vs_btc"):
        out["vs_btc"] = rep["vs_btc"]
    if q.get("not_understood"):
        out["not_understood"] = q["not_understood"]
    if asked > 1:
        out["questions_note"] = (f"You've asked {asked} different questions here. Asking many and keeping the best "
                                 "one is like trying many settings: the best looks better than it is.")
    out["note"] = ("A one-off question, not a saved bot: to keep it, ask for it as a bot (new_bot). Every number is after "
                   f"trading costs with ${notional:,.0f} a trade. Not financial advice.")
    return out
