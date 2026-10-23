"""Pine Script import: turn a pasted TradingView strategy into a BotScope bot file.

Only a common subset translates (number and on/off inputs, plain variables, the usual ta.* functions, strategy.entry / close /
exit / close_all with `when=` or under a one-line `if`). Everything else is listed back as "not translated" with the line, never
guessed. Pine fills orders on the next bar's open by default; BotScope enters at the close of the signal bar, and
every BotScope trade needs a stop, so a script without one gets `stop_pct` (said so in `added`).
"""
from __future__ import annotations

import ast
import re
from datetime import datetime

from . import checkpoints, loader, pine_runtime, scaffold

DISPLAY = ("plot", "plotshape", "plotchar", "plotarrow", "bgcolor", "barcolor", "fill", "hline", "alertcondition",
           "label.", "line.", "table.", "alert(", "indicator(", "study(")
PRICES = {"open", "high", "low", "close", "volume", "hl2", "hlc3"}


def _clean_expr(e: str) -> str:
    e = re.sub(r"\b(ta|math)\.", "", e.strip())
    e = re.sub(r"\btrue\b", "True", e)
    e = re.sub(r"\bfalse\b", "False", e)
    return e if ":=" in e else _ternary(e)


def _split_top(e: str, sep: str) -> list[int]:
    """Indexes of `sep` outside any brackets."""
    depth, at = 0, []
    for i, ch in enumerate(e):
        depth += ch in "([" and 1 or ch in ")]" and -1 or 0
        if ch == sep and depth == 0:
            at.append(i)
    return at


def _ternary(e: str) -> str:
    """Pine's `cond ? a : b` as Python's `(a if cond else b)`, inside brackets and nested ones too.
    Anything unbalanced is left as it was (then listed as not translated)."""
    out, i = "", 0
    while i < len(e):
        if e[i] in "([":
            depth, j = 0, i
            while j < len(e):
                depth += e[j] in "([" and 1 or e[j] in ")]" and -1 or 0
                if depth == 0:
                    break
                j += 1
            if j >= len(e):
                return e
            inner, cuts = e[i + 1:j], _split_top(e[i + 1:j], ",")
            parts = [inner[a + 1:b] for a, b in zip([-1] + cuts, cuts + [len(inner)])]
            out += e[i] + ",".join(_ternary(x) for x in parts) + e[j]
            i = j + 1
        else:
            out += e[i]
            i += 1
    qs = _split_top(out, "?")
    if not qs:
        return out
    q, nest = qs[0], 0
    for k in sorted(_split_top(out, "?")[1:] + _split_top(out, ":")):
        if k < q:
            continue
        if out[k] == "?":
            nest += 1
        elif nest:
            nest -= 1
        else:
            cond, a, b = out[:q], out[q + 1:k], out[k + 1:]
            return f"({_ternary(a).strip()} if {cond.strip()} else {_ternary(b).strip()})"
    return e


def _check_expr(e: str, known: set[str]) -> str | None:
    """None if the expression only uses what the runtime can run, else why not."""
    if "?" in e or ":=" in e or re.search(r"\bna\b", e):
        return "uses := or na (not translated yet)" if "?" not in e else "uses ?: that doesn't read cleanly"
    try:
        tree = ast.parse(e, mode="eval")
    except SyntaxError:
        return "doesn't read as a simple expression"
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in pine_runtime.FUNCS or node.keywords:
                return f"uses {ast.unparse(node.func)}(), which isn't translated yet"
        elif isinstance(node, ast.Name) and node.id not in known and node.id not in pine_runtime.FUNCS \
                and node.id not in ("True", "False"):
            return f"uses {node.id}, which isn't defined above it"
        elif isinstance(node, ast.Attribute):
            return f"uses {ast.unparse(node)}"
    return None


def _args(call: str) -> tuple[list[str], dict[str, str]]:
    """Positional and keyword arguments of 'f(a, b, k=v)' (splits on top-level commas only)."""
    inner = call[call.index("(") + 1:call.rindex(")")]
    parts, depth, cur = [], 0, ""
    for ch in inner:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur); cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    pos, kw = [], {}
    for p in parts:
        m = re.match(r"\s*(\w+)\s*=(?!=)\s*(.*)$", p, re.S)
        if m:
            kw[m.group(1)] = m.group(2).strip()
        else:
            pos.append(p.strip())
    return pos, kw


def translate(script: str) -> dict:
    """{title, params, series, long, short, exit_long, exit_short, stop_long, target_long, stop_short,
    target_short, plots, translated, skipped, not_translated}"""
    out = {"title": None, "params": {}, "series": [], "long": [], "short": [], "exit_long": [], "exit_short": [],
           "stop_long": None, "target_long": None, "stop_short": None, "target_short": None, "plots": [],
           "translated": [], "skipped": [], "not_translated": []}
    known = set(PRICES)
    ids = {}                                            # entry id -> "long" / "short"
    for cond, line, raw in _blocks(script, out):
        if cond is not None and re.match(r"(?:var\s+|float\s+|int\s+|bool\s+)*\w+\s*:?=(?!=)", line):
            out["not_translated"].append({"line": raw, "why": "a value set inside an if (only set-always values are translated)"})
            continue
        if line.startswith("strategy("):
            pos, kw = _args(line)
            t = kw.get("title") or (pos[0] if pos else None)
            out["title"] = t.strip("'\"") if t else None
            out["skipped"].append({"line": line, "why": "strategy settings (BotScope uses its own costs and size)"})
            continue
        if line.startswith(DISPLAY):
            if line.startswith("plot("):
                p, _ = _args(line)
                if p and re.fullmatch(r"\w+", p[0]) and p[0] in known and p[0] not in PRICES:
                    out["plots"].append(p[0])
            out["skipped"].append({"line": line, "why": "display only"})
            continue
        m = re.match(r"(?:var\s+|float\s+|int\s+|bool\s+)*(\w+)\s*=(?!=)\s*(.+)$", line)
        if m and not line.startswith("strategy."):
            name, rhs = m.group(1), m.group(2).strip()
            if re.match(r"input(\.int|\.float|\.bool)?\s*\(", rhs):
                pos, kw = _args(rhs)
                v = kw.get("defval") or (pos[0] if pos else None)
                if v in ("true", "false"):             # an on/off switch: a fixed value (edit SERIES to flip it)
                    out["series"].append((name, "True" if v == "true" else "False"))
                    known.add(name); out["translated"].append(line)
                    continue
                try:
                    num = float(v)
                    out["params"][name] = int(num) if num.is_integer() and "." not in v else num
                    known.add(name); out["translated"].append(line)
                except (TypeError, ValueError):
                    out["not_translated"].append({"line": line, "why": "only number inputs are translated"})
                continue
            e = _clean_expr(rhs)
            why = _check_expr(e, known)
            if why:
                out["not_translated"].append({"line": line, "why": why})
                continue
            out["series"].append((name, e)); known.add(name); out["translated"].append(line)
            continue
        if line.startswith("strategy.close_all"):         # closes whatever is open, long or short
            _, kw = _args(line)
            when = kw.get("when") or cond
            why = "a close_all without a condition" if when is None else _check_expr(_clean_expr(when), known)
            if why:
                out["not_translated"].append({"line": raw, "why": why})
                continue
            out["exit_long"].append(_clean_expr(when)); out["exit_short"].append(_clean_expr(when))
            out["translated"].append(raw)
            continue
        if line.startswith(("strategy.entry", "strategy.close", "strategy.exit")):
            pos, kw = _args(line)
            when = kw.get("when") or cond
            if when is not None:
                when = _clean_expr(when)
                why = _check_expr(when, known)
                if why:
                    out["not_translated"].append({"line": raw, "why": why})
                    continue
            if line.startswith("strategy.entry"):
                side = "long" if "strategy.long" in line else "short" if "strategy.short" in line else None
                if not side or when is None:
                    out["not_translated"].append({"line": raw, "why": "an entry without a side or a condition"})
                    continue
                ids[pos[0].strip("'\"") if pos else side] = side
                out[side].append(when)
            elif line.startswith("strategy.close"):
                side = ids.get(pos[0].strip("'\"") if pos else "", None)
                if not side or when is None:
                    out["not_translated"].append({"line": raw, "why": "a close for an unknown entry id or without a condition"})
                    continue
                out["exit_" + side].append(when)
            else:
                side = ids.get((kw.get("from_entry") or (pos[1] if len(pos) > 1 else "")).strip("'\""))
                if not side or not ({"stop", "limit"} & set(kw)):
                    out["not_translated"].append({"line": raw, "why": "exit without stop=/limit= prices (loss=/profit= in ticks aren't translated)"})
                    continue
                for k, slot in (("stop", "stop_"), ("limit", "target_")):
                    if k in kw:
                        e = _clean_expr(kw[k])
                        why = _check_expr(e, known)
                        if why:
                            out["not_translated"].append({"line": raw, "why": why}); break
                        out[slot + side] = e
                else:
                    out["translated"].append(raw)
                continue
            out["translated"].append(raw)
            continue
        out["not_translated"].append({"line": line, "why": "not part of the translated subset"})
    return out


def _blocks(script: str, out: dict):
    """(condition or None, line, line as shown) for each statement. A one-level `if` block gives every line in it the
    if's condition; an indented line under anything else (else, for, while, a nested if, a function) is listed as not
    translated, so nothing that only runs sometimes is ever translated as if it always ran."""
    lines = [ln.split("//")[0].rstrip() for ln in script.splitlines()]
    ind = lambda ln: len(ln) - len(ln.lstrip())
    i = 0
    while i < len(lines):
        raw = lines[i]; line = raw.strip(); i += 1
        if not line:
            continue
        if ind(raw):
            out["not_translated"].append({"line": line, "why": "inside a block that isn't translated (else, for, while, "
                                                               "a nested if or a function)"})
            continue
        if line.startswith("if ") and i < len(lines) and ind(lines[i]):
            cond, depth = line[3:].strip(), ind(lines[i])
            while i < len(lines) and (not lines[i].strip() or ind(lines[i])):
                body = lines[i]; i += 1
                if not body.strip():
                    continue
                if ind(body) > depth:
                    out["not_translated"].append({"line": f"if {cond} → {body.strip()}",
                                                  "why": "inside a nested block (not translated)"})
                elif body.strip().startswith(("if ", "else", "for ", "while ")):
                    out["not_translated"].append({"line": f"if {cond} → {body.strip()}",
                                                  "why": "a nested if or loop (not translated)"})
                else:
                    yield cond, body.strip(), f"if {cond} → {body.strip()}"
            continue
        yield None, line, raw


def _inline_lengths(t: dict) -> list[int]:
    """Lengths written straight into a call, like sma(close, 200): they need warmup days too."""
    exprs = [e for _, e in t["series"]] + t["long"] + t["short"] + t["exit_long"] + t["exit_short"] + \
        [t[k] for k in ("stop_long", "target_long", "stop_short", "target_short") if t[k]]
    out = []
    for e in exprs:
        try:
            tree = ast.parse(e, mode="eval")
        except SyntaxError:
            continue
        out += [a.value for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in pine_runtime.FUNCS for a in node.args
                if isinstance(a, ast.Constant) and type(a.value) is int and 2 <= a.value <= 300]
    return out


def _or(conds: list[str]) -> str | None:
    return None if not conds else conds[0] if len(conds) == 1 else " or ".join(f"({c})" for c in conds)


TEMPLATE = '''"""Imported from a TradingView Pine Script strategy on {today}: {title}.

Translated by BotScope's Pine import (the common subset only; see `notes` for what was added or left out).
Differences from TradingView: BotScope enters at the close of the signal bar (Pine's default is the next bar's open),
uses its own trading costs, and every trade has a stop. Untested until its honest report says otherwise.
"""
from botscope.bot import Bot, Entry, Exit, NoTrade
from botscope.pine_runtime import run as _run

SERIES = {series!r}
LONG = {long!r}
SHORT = {short!r}
EXIT_LONG = {exit_long!r}
EXIT_SHORT = {exit_short!r}
STOPS = {stops!r}
PLOTS = {plots!r}


class {cls}(Bot):
    name = {name!r}
    version = "1.0"
    description = {description!r}
    rules = {rules!r}
    symbols = {symbols!r}
    timeframe = {timeframe!r}
    sides = {sides!r}
    asset = {asset!r}
    max_trades_per_day = 1
    flat_by_close = {flat}
    lookback_days = {lookback}
    params = {params!r}
    tuned_on = None
    status = "untested"
    notes = {notes!r}

    def _env(self, bars, extra=()):
        return _run(SERIES + [x for x in extra if x[1]], self.p, bars)

    def indicators(self, bars):
        env = self._env(bars)
        return {{k: env[k] for k in PLOTS}}

    def _stop(self, side, env, c):
        e = STOPS.get(side + "_stop")
        v = env.get("_stop")[-1] if e else None
        ok = v is not None and ((side == "long" and v < c) or (side == "short" and v > c))
        if ok:
            return v
        pct = self.p["stop_pct"] / 100
        return c * (1 - pct) if side == "long" else c * (1 + pct)

    def entry(self, view):
        env = self._env(view.bars, [("_long", LONG), ("_short", SHORT)])
        c = view.bars[-1].c
        for side, key in (("long", "_long"), ("short", "_short")):
            sig = env.get(key)
            if sig and sig[-1]:
                stops = self._env(view.bars, [("_stop", STOPS.get(side + "_stop")), ("_target", STOPS.get(side + "_target"))])
                t = stops.get("_target", [None])[-1] if STOPS.get(side + "_target") else None
                return Entry(side, self._stop(side, stops, c), t, f"Pine {{side}} entry condition is true")
        return NoTrade("no Pine entry condition is true on this bar")

    def exit(self, view, pos):
        env = self._env(view.bars, [("_x", EXIT_LONG if pos.side == "long" else EXIT_SHORT),
                                    ("_flip", SHORT if pos.side == "long" else LONG)])
        if env.get("_x") and env["_x"][-1]:
            return Exit("Pine close condition is true")
        if env.get("_flip") and env["_flip"][-1]:
            return Exit("the opposite Pine entry fired (Pine reverses the position)")
        return None
'''


def write_bot(script: str, name: str | None = None, timeframe: str = "1Day", symbols: list[str] | None = None,
              stop_pct: float = 2.0) -> dict:
    t = translate(script)
    if not (t["long"] or t["short"]):
        raise ValueError("no strategy.entry with a condition could be translated, so there's no bot to make: "
                         + "; ".join(f"{x['line']} ({x['why']})" for x in t["not_translated"][:5]))
    if timeframe not in scaffold.TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {', '.join(scaffold.TIMEFRAMES)}")
    name = (name or t["title"] or "Pine import").strip()
    slug = scaffold._slug(name)
    path = loader.bots_dir() / f"{slug}.py"
    if path.exists() or slug in loader.load_all()[0]:
        raise ValueError(f"{path.name} already exists; pass another name")
    added = []
    params = dict(t["params"])
    params["stop_pct"] = stop_pct                    # also the fallback when a script's stop lands on the wrong side
    if (t["long"] and not t["stop_long"]) or (t["short"] and not t["stop_short"]):
        added.append(f"stop_pct = {stop_pct:g}: a {stop_pct:g}% stop where the script has none (BotScope needs a stop on every trade)")
    lg, sh = _or(t["long"]), _or(t["short"])
    rules = []
    if lg:
        rules.append(f"Long when: {lg}.")
    if sh:
        rules.append(f"Short when: {sh}.")
    if t["exit_long"]:
        rules.append(f"Close a long when: {_or(t['exit_long'])}.")
    if t["exit_short"]:
        rules.append(f"Close a short when: {_or(t['exit_short'])}.")
    rules.append("An opposite entry closes the open trade (like Pine).")
    rules.append("Stop: " + "; ".join(x for x in (
        f"long at {t['stop_long']}" if t["stop_long"] else None,
        f"short at {t['stop_short']}" if t["stop_short"] else None) if x)
        + ("; " if t["stop_long"] or t["stop_short"] else "") + f"otherwise {stop_pct:g}% from the entry (stop_pct).")
    rules.append("Settings: " + ", ".join(f"{k} = {v:g}" for k, v in params.items()) + ".")
    ints = [v for v in t["params"].values() if isinstance(v, int) and 2 <= v <= 300] + _inline_lengths(t)
    cls = "".join(w.capitalize() for w in slug.split("_")) or "PineBot"
    if cls[0].isdigit():
        cls = "Pine" + cls
    notes = ("Pine import. Added: " + ("; ".join(added) or "nothing") + ". Not translated: "
             + ("; ".join(x["line"] for x in t["not_translated"]) or "nothing") + ".")
    src = TEMPLATE.format(
        today=datetime.now().date(), title=t["title"] or name, series=t["series"], long=lg, short=sh,
        exit_long=_or(t["exit_long"]), exit_short=_or(t["exit_short"]),
        stops={k: v for k, v in (("long_stop", t["stop_long"]), ("long_target", t["target_long"]),
                                 ("short_stop", t["stop_short"]), ("short_target", t["target_short"])) if v},
        plots=t["plots"], cls=cls, name=name, description=f"Imported Pine Script strategy: {t['title'] or name}.",
        rules=rules, symbols=[s.upper() for s in (symbols or ["SPY", "QQQ", "IWM"])][:5], timeframe=timeframe,
        sides="both" if lg and sh else "long" if lg else "short",
        asset="swing" if timeframe == "1Day" else "stock_intraday", flat=timeframe != "1Day",
        lookback=int(max(ints) * 1.1) + 1 if ints and timeframe == "1Day" else 0, params=params, notes=notes)
    compile(src, str(path), "exec")
    cp = checkpoints.save(f"before import_pine {name}")
    path.write_text(src)
    return {"file": str(path), "bot_id": loader.bot_id(loader.get(slug)), "checkpoint_before": cp["id"],
            "translated": t["translated"], "skipped": t["skipped"], "not_translated": t["not_translated"],
            "added": added, "warnings": stop_warnings(t)}


def stop_warnings(t: dict) -> list[str]:
    """A stop at the lowest low (or highest high) of a window that includes the signal candle often sits a few cents
    from the entry, which blows R up (docs/when-r-lies-tight-stops.md). Said at import, before any report."""
    out = []
    for side, k, fn in (("long", "stop_long", "lowest"), ("short", "stop_short", "highest")):
        e = t.get(k) or ""
        if re.fullmatch(rf"\s*{fn}\((?:[^()]*)\)\s*", e):
            out.append(f"the {side} stop is {e}, which includes the signal candle itself, so it can sit a few cents "
                       f"from the entry and inflate R; a distance from the usual range, like close - 2 * ta.atr(14), "
                       "keeps it wide (docs/when-r-lies-tight-stops.md)")
    return out
