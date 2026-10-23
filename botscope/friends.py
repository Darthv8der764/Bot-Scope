"""Friends: swap friend codes and compare bots, read-only. No server, no account, nothing uploaded.

A friend code is one block of text: "BOTSCOPE-FRIEND-1:" + the bot's card (JSON, zlib, base64url) + "." + a short
checksum (catches a bad copy-paste; it is not a signature). You send it any way you like (chat, Discord, email); your
friend pastes it into their Friends tab. The card holds honest numbers only (untested years, after costs, the same
fields as the friends league plus a short profile): never code, keys, account, dollars or file paths. The bot's rules
and tickers are left out unless you tick "include rules". A friend's card is read as data, checked field by field,
and never run: nothing can be copied, run or changed in either direction.

compare() runs on each person's own computer, so each side gets its own "what your bot can learn" summary when they
paste the other's code. Nothing changes automatically. Not financial advice.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import zlib
from datetime import datetime, timezone

from . import journal, league, loader, report

PREFIX = "BOTSCOPE-FRIEND-1:"
VERSION = 1
MAX_CODE = 12_000            # characters of pasted text
MAX_JSON = 32_000            # bytes after unzipping (a tiny code can't unpack into something huge)
MIN_TRADES = league.MIN_TRADES

# field: (type, low, high) for numbers, (str, max length) for text. Anything else in a card is dropped.
NUM = {"untested_trades": (int, 0, 1_000_000), "untested_years": (int, 0, 100), "losing_years": (int, 0, 100),
       "years_beat_spy": (int, 0, 100), "worst_losing_streak": (int, 0, 100_000),
       "avg_r": (float, -100, 100), "total_r": (float, -1e6, 1e6), "range_low_r": (float, -1e6, 1e6),
       "costs_r": (float, 0, 1e6), "wins": (int, 0, 1_000_000), "avg_win_r": (float, 0, 1000),
       "avg_loss_r": (float, -1000, 0), "max_drawdown_r": (float, -1e6, 0), "if_costs_doubled_r": (float, -1e6, 1e6),
       "without_best_3_r": (float, -1e6, 1e6)}
TEXT = {"name": 30, "bot": 60, "timeframe": 10, "asset": 10, "sides": 10, "data": 60, "report_day": 10, "luck": 30,
        "confidence": 20}
REQUIRED = ("bot", "untested_trades", "avg_r", "total_r", "range_low_r", "luck", "data")
_CTRL = re.compile(r"[\x00-\x1f\x7f<>]")


# ---------- your card and code ----------
def card(bot: str, name: str = "me", include_rules: bool = False) -> dict:
    """The card for one of your bots: honest numbers from its saved report (UNTESTED years, after costs)."""
    cls = loader.get(bot)
    base = league.card(bot, name)                  # needs a saved honest report; same numbers as the league
    rep = report.saved(cls) or {}
    u = rep.get("untested") or {}
    rs = [r for r in (rep.get("untested_rs") or []) if isinstance(r, (int, float))]
    wins, losses = [r for r in rs if r > 0], [r for r in rs if r <= 0]
    c = {"friend_card": VERSION, "name": base["owner"] if base["owner"] != "me" else "your friend", "bot": base["bot"], "timeframe": cls.timeframe,
         "asset": cls.asset, "sides": cls.sides, "data": base["data"], "report_day": base["report_day"],
         "luck": base["luck"], "confidence": base["confidence"],
         **{k: base[k] for k in ("untested_trades", "avg_r", "total_r", "range_low_r", "costs_r", "losing_years",
                                 "untested_years")},
         "wins": len(wins) if rs else None,
         "avg_win_r": round(sum(wins) / len(wins), 3) if wins else None,
         "avg_loss_r": round(sum(losses) / len(losses), 3) if losses else None,
         "worst_losing_streak": u.get("worst_losing_streak"), "max_drawdown_r": u.get("max_drawdown_r"),
         "if_costs_doubled_r": u.get("if_costs_doubled_r"), "without_best_3_r": u.get("without_best_3_r"),
         "years_beat_spy": (rep.get("vs_spy") or {}).get("years_beat"),
         "by_year": [{"year": y["year"], "trades": y["trades"], "avg_r": y.get("avg_r")}
                     for y in rep.get("by_year") or [] if y.get("period") == "untested" and y.get("trades")]}
    if include_rules:                              # only when you tick it: how the bot works, and what it trades
        c["rules"] = [str(r) for r in (cls.rules or [])][:20]
        c["symbols"] = [str(s) for s in (cls.symbols or [])][:20]
    return clean(c)


def encode(c: dict) -> str:
    raw = zlib.compress(json.dumps(c, separators=(",", ":")).encode(), 9)
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return f"{PREFIX}{body}.{hashlib.sha256(body.encode()).hexdigest()[:6]}"


def my_code(bot: str, name: str = "me", include_rules: bool = False) -> dict:
    c = card(bot, name, include_rules)
    code = encode(c)
    return {"code": code, "card": c, "characters": len(code), "includes_rules": include_rules,
            "note": "Send this code to a friend any way you like; they paste it into their Friends tab. It holds the "
                    "numbers shown here only: no code, keys, account, dollars or file paths"
                    + ("" if include_rules else ", and no rules or tickers") + ". Nothing is uploaded."}


# ---------- reading a friend's code ----------
def decode(code: str) -> dict:
    """A friend's card from their code, checked field by field. Raises ValueError with a plain reason."""
    code = re.sub(r"\s+", "", code or "")
    if len(code) > MAX_CODE:
        raise ValueError(f"that code is too long ({len(code):,} characters; a friend code is under {MAX_CODE:,})")
    if not code.startswith(PREFIX):
        raise ValueError("that isn't a BotScope friend code (it should start with BOTSCOPE-FRIEND-1:)")
    body, _, check = code[len(PREFIX):].rpartition(".")
    if not body or check != hashlib.sha256(body.encode()).hexdigest()[:6]:
        raise ValueError("that code is cut off or changed: ask your friend to copy it again, all of it")
    try:
        z = zlib.decompressobj()
        raw = z.decompress(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)), MAX_JSON)
        if z.unconsumed_tail or not z.eof:
            raise ValueError("too big")
        data = json.loads(raw)
    except (ValueError, zlib.error) as e:
        raise ValueError("that code can't be read (damaged, or too big inside)") from e
    if not isinstance(data, dict) or data.get("friend_card") != VERSION:
        raise ValueError("that friend code is from a different BotScope version: ask your friend to update")
    c = clean(data)
    missing = [k for k in REQUIRED if c.get(k) is None]
    if missing:
        raise ValueError(f"that card is missing {', '.join(missing)}")
    return c


def _text(v, n: int) -> str | None:
    return _CTRL.sub("", v).strip()[:n] or None if isinstance(v, str) else None


def clean(d: dict) -> dict:
    """Keep known fields only, with the right types and sane ranges; text loses control characters and < >."""
    out: dict = {"friend_card": VERSION}
    for k, n in TEXT.items():
        out[k] = _text(d.get(k), n)
    for k, (t, lo, hi) in NUM.items():
        v = d.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
            out[k] = None
            continue
        v = int(v) if t is int else round(float(v), 4)
        out[k] = v if lo <= v <= hi else None
    years = []
    for y in d.get("by_year") or [] if isinstance(d.get("by_year"), list) else []:
        if (isinstance(y, dict) and isinstance(y.get("year"), int) and 1900 <= y["year"] <= 2100
                and isinstance(y.get("trades"), int) and isinstance(y.get("avg_r"), (int, float))
                and not isinstance(y.get("avg_r"), bool) and abs(y["avg_r"]) <= 100):
            years.append({"year": y["year"], "trades": max(0, min(y["trades"], 100_000)), "avg_r": round(float(y["avg_r"]), 4)})
    out["by_year"] = years[:40]
    for k, n, size in (("rules", 20, 200), ("symbols", 20, 15)):
        if isinstance(d.get(k), list):
            out[k] = [x for x in (_text(s, size) for s in d[k][:n]) if x]
    out["name"] = out["name"] or "your friend"
    return out


# ---------- friends list (journal 'friends', this computer only) ----------
def add(code: str) -> dict:
    c = decode(code)
    for r in journal.load("friends"):          # same friend + bot again = the newer card replaces the old one
        if r.get("card", {}).get("name") == c["name"] and r.get("card", {}).get("bot") == c["bot"]:
            journal.remove("friends", r["id"])
    row = journal.add("friends", {"card": c, "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return {"added": row["id"], "card": c, "note": "Saved on this computer only. Read as numbers; nothing is run."}


def remove(fid: str) -> dict:
    return {"removed": journal.remove("friends", str(fid))}


def listing() -> dict:
    rows = journal.load("friends")
    return {"friends": [{"id": r["id"], "added_at": r.get("added_at"), "card": clean(r.get("card") or {})} for r in rows],
            "note": "Friends' cards are numbers from their own computers (UNTESTED years, after costs), read as data."}


# ---------- compare + what each bot can learn ----------
def _per_trade(c: dict, k: str) -> float | None:
    return c[k] / c["untested_trades"] if c.get(k) is not None and c.get("untested_trades") else None


def _f(x, unit="R", plus=True) -> str:
    return "–" if x is None else f"{x:+.2f}{unit}" if plus else f"{x:.2f}{unit}"


def rows(mine: dict, theirs: dict) -> list[dict]:
    won = lambda c: "–" if c.get("wins") is None else f"{c['wins']} of {c['untested_trades']}"     # noqa: E731
    def r(label, a, b, why=""):
        return {"row": label, "yours": a, "theirs": b, "why": why}
    s1, s2 = (league.score(c)[0] if c["data"] and c["data"].startswith("real") else None for c in (mine, theirs))
    return [
        r("Bot", f"{mine['bot']} ({mine.get('timeframe') or '?'})", f"{theirs['bot']} ({theirs.get('timeframe') or '?'})"),
        r("Data", mine["data"], theirs["data"]),
        r("Untested trades", mine["untested_trades"], theirs["untested_trades"], f"under {MIN_TRADES} = too few to judge"),
        r("Honest score (per trade)", _f(s1), _f(s2), "bad end of the untested range per trade, after costs"),
        r("Average per trade", _f(mine["avg_r"]), _f(theirs["avg_r"]), "untested years, after costs"),
        r("Trades won", won(mine), won(theirs), "counts, untested years"),
        r("Average win / loss", f"{_f(mine.get('avg_win_r'))} / {_f(mine.get('avg_loss_r'))}",
          f"{_f(theirs.get('avg_win_r'))} / {_f(theirs.get('avg_loss_r'))}"),
        r("Costs per trade", _f(_per_trade(mine, "costs_r"), plus=False), _f(_per_trade(theirs, "costs_r"), plus=False)),
        r("If costs doubled (total)", _f(mine.get("if_costs_doubled_r")), _f(theirs.get("if_costs_doubled_r"))),
        r("Without its best 3 trades", _f(mine.get("without_best_3_r")), _f(theirs.get("without_best_3_r"))),
        r("Worst losing streak", mine.get("worst_losing_streak") or "–", theirs.get("worst_losing_streak") or "–"),
        r("Losing years", f"{mine.get('losing_years')} of {mine.get('untested_years')}",
          f"{theirs.get('losing_years')} of {theirs.get('untested_years')}"),
        r("Luck meter", mine["luck"], theirs["luck"]),
    ]


TEST_FIRST = "Test it on your own bot with run_backtest (tuned vs untested years) before changing anything."


def lessons(me: dict, them: dict) -> list[dict]:
    """What `me` (the person reading) can take from `them`. Plain rules on the two cards' numbers only."""
    out = []
    def tip(title, what, use):
        out.append({"title": title, "what": what, "use": use + " " + TEST_FIRST})
    who = them["name"]
    if not (me["data"] or "").startswith("real") or not (them["data"] or "").startswith("real"):
        return [{"title": "Made on demo prices", "what": "At least one card was made on made-up DEMO prices, so its "
                 "numbers say nothing about real markets.", "use": "Make both codes again with real data, then compare."}]
    small = [c["name"] + "'s" if c is them else "your" for c in (me, them) if c["untested_trades"] < MIN_TRADES]
    if small:
        out.append({"title": "Too few trades to learn much", "what": f"{' and '.join(small)} bot has fewer than "
                    f"{MIN_TRADES} untested trades, so differences below could easily be luck.",
                    "use": "Treat everything here as a hint, not a lesson."})
    c1, c2 = _per_trade(me, "costs_r"), _per_trade(them, "costs_r")
    if c1 is not None and c2 is not None and c1 > 0.03 and c1 > 1.5 * c2:
        tip("Costs eat more of yours", f"Costs take {c1:.2f}R a trade from yours and {c2:.2f}R from {who}'s.",
            "Fewer, bigger trades (a farther target, or skipping the smallest setups) usually cut costs.")
    w1, w2 = (c["wins"] / c["untested_trades"] if c.get("wins") is not None and c["untested_trades"] else None
              for c in (me, them))
    g1, g2 = me.get("avg_win_r"), them.get("avg_win_r")
    if None not in (w1, w2, g1, g2) and them["avg_r"] > me["avg_r"]:
        if w2 < w1 - 0.05 and g2 > g1 * 1.2:
            tip("Theirs wins less often but bigger", f"{who}'s won {them['wins']} of {them['untested_trades']} trades with {g2:.2f}R average wins; "
                f"yours won {me['wins']} of {me['untested_trades']} with {g1:.2f}R.", "A farther target or a trailing exit could let your winners run.")
        elif w2 > w1 + 0.05:
            tip("Theirs wins more often", f"{who}'s won {them['wins']} of {them['untested_trades']} trades, yours {me['wins']} of {me['untested_trades']}.",
                "A closer target or a stricter entry filter might win more of your trades; check it doesn't shrink the average.")
    s1, s2 = me.get("worst_losing_streak"), them.get("worst_losing_streak")
    if s1 and s2 and s1 >= s2 + 4:
        tip("Long losing streaks", f"Your worst losing streak is {s1} trades; {who}'s is {s2}.",
            "A smaller size or a weekly loss budget (set_loss_budget) makes long streaks easier to sit through.")
    b1, b2 = me.get("without_best_3_r"), them.get("without_best_3_r")
    if b1 is not None and b2 is not None and me["total_r"] > 0 and b1 <= 0 < b2:
        tip("Yours leans on a few big wins", f"Without its best 3 trades yours is at {b1:+.1f}R; {who}'s still makes {b2:+.1f}R.",
            "Results that need a few lucky trades are fragile: paper trade longer before trusting it.")
    d1, d2 = me.get("if_costs_doubled_r"), them.get("if_costs_doubled_r")
    if d1 is not None and d2 is not None and d1 < 0 <= d2:
        tip("Thin edge against costs", f"With costs doubled yours goes to {d1:+.1f}R; {who}'s stays at {d2:+.1f}R.",
            "Real fills can cost more than the backtest: a bigger edge per trade or fewer trades gives room.")
    if them["luck"] == "beats luck" and me["luck"] == "looks like luck":
        tip("Theirs beats the luck meter", f"{who}'s results beat random entries; yours look like luck so far.",
            "Run luck_meter on yours after changes: an idea only counts if it beats random entries too.")
    y1 = {y["year"]: y["avg_r"] for y in me.get("by_year") or []}
    y2 = {y["year"]: y["avg_r"] for y in them.get("by_year") or []}
    both = sorted(set(y1) & set(y2))
    saved = [y for y in both if y1[y] < 0 < y2[y]]
    if saved:
        tip("They did well when yours struggled", f"In {', '.join(map(str, saved))} yours lost money and {who}'s made money.",
            "Bots that lose in different years can smooth each other out; team_report shows how two bots work together.")
    elif (len(both) >= 3 and all((y1[y] < 0) == (y2[y] < 0) for y in both)
          and any(y1[y] < 0 for y in both)):
        out.append({"title": "Good and bad years line up", "what": f"Your bot and {who}'s were up and down in the same "
                    "years.", "use": "Running both wouldn't spread the risk much."})
    if them.get("rules"):
        tip("Their rules are shared", f"{who} included their bot's rules in plain English.",
            "Read them for ideas you could try on your own bot. Nothing is copied: you'd write any change yourself.")
    if not [x for x in out if x["title"] not in ("Too few trades to learn much",)]:
        out.append({"title": "No clear lesson from the numbers", "what": f"Your bot and {who}'s don't differ enough "
                    "on these numbers to point at a change.", "use": "That's a real answer. Compare again after more trades."})
    return out


def compare(bot: str, fid: str, name: str = "me") -> dict:
    friend = next((r for r in journal.load("friends") if r["id"] == fid), None)
    if not friend:
        raise ValueError("no friend card with that id (add their friend code first)")
    mine, theirs = card(bot, name), clean(friend["card"])
    return {"rows": rows(mine, theirs), "for_you": lessons(mine, theirs), "for_friend": lessons(theirs, mine),
            "theirs": theirs, "mine": mine,
            "note": "All numbers are UNTESTED years after costs, from each person's own computer. Each of you gets "
                    "your own summary: when your friend pastes your code, their computer makes theirs. Read-only: "
                    "nothing is copied, run or changed. Not financial advice."}
