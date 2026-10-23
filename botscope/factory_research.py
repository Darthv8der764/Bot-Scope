"""Strategy factory research: your own Claude Code (headless `claude -p`, your own login) looks up well-known,
documented strategies that fit the goal and writes 5 candidate bot files in the BotScope format, each with its rules
in plain English and the source of the idea.

Claude only answers with text (a JSON with the 5 files): its tools are web search and web fetch, no MCP servers (so
no broker tools at all), BotScope's live-order guard attached anyway, and it runs in the run's own folder. BotScope
then reads every file before running any of it and refuses anything a bot has no business doing: imports other than
a few plain math modules and botscope.bot, file / network / process calls, eval and friends, double-underscore
tricks, anything that looks like an order. A refused file is never saved as a .py, so nothing can load it. Each bad
candidate gets one retry; if research can't run at all (no `claude` command, not logged in, offline, the Claude
panel switched off), the factory says so and uses its built-in textbook templates.

Research only changes where the ideas come from. Every candidate still goes through the same honest pipeline, and
the run still says how many were tried. Paper only: nothing here places an order.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from . import console, scaffold

COUNT = 5
TIMEOUT = 900                        # seconds for one Claude run (research with web search can take minutes)
MAX_CODE = 30_000
TOOLS = "WebSearch,WebFetch"
SAFE_IMPORTS = {"__future__", "math", "statistics", "datetime", "collections", "itertools", "functools",
                "dataclasses", "typing", "bisect", "heapq", "operator", "enum", "botscope.bot"}
BANNED_CALLS = {"open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "getattr", "setattr",
                "delattr", "input", "breakpoint", "help", "exit", "quit", "memoryview", "print"}
ORDERISH = re.compile(r"order|submit|broker|alpaca|trading_?client|close_?position|liquidat", re.I)
DUNDER_OK = {"__init__"}
TOP_OK = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign)

SCHEMA = {
    "type": "object", "required": ["candidates"],
    "properties": {"candidates": {"type": "array", "items": {
        "type": "object", "required": ["name", "idea", "source", "why_it_fits", "code"],
        "properties": {"name": {"type": "string"}, "idea": {"type": "string"}, "source": {"type": "string"},
                       "why_it_fits": {"type": "string"}, "code": {"type": "string"}}}}}}


class Unavailable(RuntimeError):
    """Research couldn't run; the factory falls back to its templates and says why."""


# ---------------------------------------------------------------- reading a file before running any of it

def scan(code: str) -> list[str]:
    """Why this candidate file is refused (empty = it may be loaded). Reads the source only; nothing runs."""
    if len(code) > MAX_CODE:
        return [f"too long ({len(code)} characters; a bot needs far fewer)"]
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"not valid Python (line {e.lineno}: {e.msg})"]
    bad: list[str] = []
    add = lambda why: bad.append(why) if why not in bad else None     # noqa: E731
    for i, node in enumerate(tree.body):
        if not isinstance(node, TOP_OK) and not (i == 0 and _is_doc(node)):
            add(f"runs code when the file is loaded (line {node.lineno}): a bot file only defines things")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name not in SAFE_IMPORTS:
                    add(f"imports {a.name} (only plain math modules and botscope.bot are allowed)")
        elif isinstance(node, ast.ImportFrom):
            if node.level or node.module not in SAFE_IMPORTS:
                add(f"imports from {'.' * node.level}{node.module or ''} (only plain math modules and botscope.bot "
                    "are allowed)")
        elif isinstance(node, ast.ClassDef):
            for b in node.body:
                if not isinstance(b, (ast.Assign, ast.AnnAssign, ast.FunctionDef)) and not _is_doc(b):
                    add(f"runs code inside the class body (line {b.lineno})")
        elif isinstance(node, (ast.Global, ast.Nonlocal, ast.AsyncFunctionDef, ast.Await, ast.AsyncWith,
                               ast.AsyncFor)):
            add(f"uses {type(node).__name__.lower()} (line {node.lineno}): a bot doesn't need it")
        names = []
        if isinstance(node, ast.Name):
            names = [node.id]
        elif isinstance(node, ast.Attribute):
            names = [node.attr]
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.arg):
            names = [node.arg]
        elif isinstance(node, ast.keyword) and node.arg:
            names = [node.arg]
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "__" in node.value:
            add(f"has a text with a double underscore (line {node.lineno}): a way to reach Python's insides")
        for n in names:
            if n in BANNED_CALLS and isinstance(node, ast.Name):      # (a method named exit() is fine)
                add(f"uses {n}() (line {node.lineno}): files, input and running text as code are not allowed")
            elif n.startswith("__") and n not in DUNDER_OK:
                add(f"uses {n} (line {node.lineno}): a way to reach Python's insides")
            elif ORDERISH.search(n):
                add(f"mentions {n} (line {node.lineno}): looks like an order or broker call, and bots never place orders")
    return bad


def _is_doc(node) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def _set_name(code: str, name: str) -> str | None:
    """The file with the bot's `name = ...` set to `name` (so the bot id matches the file name), or None."""
    tree = ast.parse(code)
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        for st in cls.body:
            if (isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name)
                    and st.targets[0].id == "name" and st.value.lineno == st.value.end_lineno):
                lines = code.splitlines(keepends=True)
                ln = lines[st.value.lineno - 1]
                raw = ln.encode()
                new = raw[:st.value.col_offset] + repr(name).encode() + raw[st.value.end_col_offset:]
                lines[st.value.lineno - 1] = new.decode()
                return "".join(lines)
    return None


def _one_line(s, n: int = 300) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def accept(item: dict, spec: dict, run_id: str, folder: Path, taken: set) -> dict:
    """One candidate from Claude's answer -> {slug, path, label, idea, source, why} once its file is saved, loads,
    and passes check_bot; or {refused: reason, ...} with nothing saved as .py."""
    from . import backtest, strategy_factory
    label = _one_line(item.get("name"), 60) or "Researched idea"
    out = {"label": label, "idea": _one_line(item.get("idea")), "source": _one_line(item.get("source")),
           "why": _one_line(item.get("why_it_fits"))}
    code = str(item.get("code") or "")
    if not out["source"]:
        return {**out, "refused": "no source given for the idea"}
    bad = scan(code)
    if bad:
        return {**out, "refused": "; ".join(bad[:3]), "code": code}
    if scaffold._slug(f"{label} {run_id}") in taken:          # two ideas with the same name: number the second
        label = f"{label} {len(taken) + 1}"
    slug = scaffold._slug(f"{label} {run_id}")
    named = _set_name(code, f"{label} ({run_id})")
    if named is None:
        return {**out, "refused": "the bot class has no plain `name = \"...\"` line", "code": code}
    head = (f"# Researched by your own Claude Code for the strategy factory (run {run_id}).\n"
            f"# Idea: {out['idea']}\n# Source of the idea: {out['source']}\n")
    path = folder / f"{slug}.py"
    path.write_text(head + named)
    why = None
    try:
        cls = strategy_factory.load_file(path)
        if strategy_factory.loader.bot_id(cls) != slug:
            why = "the bot's name doesn't match its file"
        elif cls.timeframe != spec["timeframe"]:
            why = f"uses {cls.timeframe} candles, but the goal is read as {spec['timeframe']}"
        elif spec["sides"] != "both" and cls.sides != spec["sides"]:
            why = f"trades {cls.sides}, but the goal is {spec['sides']} only"
        elif cls.asset not in backtest.COSTS:
            why = f"unknown cost profile asset = {cls.asset!r}"
        elif cls.tuned_on is not None:
            why = "says it was tuned (tuned_on); research candidates must use published settings"
        else:
            chk = scaffold.check_class(cls)
            failed = [c for c in chk["checks"] if not c["pass"]]
            if failed:
                why = f"failed check_bot: {failed[0]['check']} ({_one_line(failed[0]['detail'], 160)})"
    except Exception as e:                       # it loads with a crash: refused, never a factory crash
        why = f"crashed when loaded: {type(e).__name__}: {_one_line(e, 160)}"
    if why:
        path.unlink(missing_ok=True)
        return {**out, "refused": why, "code": code}
    taken.add(slug)
    return {**out, "slug": slug, "path": path}


# ---------------------------------------------------------------- asking Claude

def command() -> list[str]:
    exe = shutil.which("claude")
    if not exe:
        raise Unavailable("Claude Code (the `claude` command) isn't installed or isn't on the PATH")
    return [exe, "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
            "--settings", console.guard_settings(), "--strict-mcp-config", "--tools", TOOLS,
            "--allowedTools", TOOLS, "--json-schema", json.dumps(SCHEMA)]


def prompt(goal: str, spec: dict, run_id: str, n: int = COUNT, redo: list[dict] | None = None) -> str:
    from . import strategy_factory as sf
    key = "dip_buy" if spec["timeframe"] == "1Day" else "opening_range"
    _, example = sf.source(key, {**spec, "sides": sf.TEMPLATES[key]["sides"][0], "calm": False}, run_id)
    asset = "crypto" if spec.get("asset") == "crypto" else "swing" if spec["timeframe"] == "1Day" else "stock_intraday"
    ask = (f"Research and write exactly {n} candidate trading bots for this goal: {goal!r}.\n"
           if not redo else
           f"Some candidate files you wrote for the goal {goal!r} were refused. Write exactly {n} replacement(s), "
           "each a different well-known strategy from the ones refused, avoiding the problems named:\n"
           + "\n".join(f"- {r['label']}: {r['refused']}" for r in redo) + "\n")
    return f"""[BotScope strategy factory. Paper only: nothing you write places an order.]
{ask}
BotScope read the goal as: {spec['read_as']}.
Use: timeframe = {spec['timeframe']!r}, symbols = {spec['symbols']!r}, sides = {spec['sides']!r}
{'(each bot may pick long or short or both)' if spec['sides'] == 'both' else ''}, asset = {asset!r}.

How to choose:
- Pick well-known, documented strategies that fit the goal (books, papers, the author who published it). You may use
  web search to check the rules and the published default settings. Give the source of each idea (author, book or
  paper, and a URL if you have one). Each candidate must be a different idea.
- Use the textbook / published settings. Do NOT tune settings to recent years and do not run any backtests: BotScope
  tests every candidate itself on years it was never tuned on, with costs, doubled costs, luck and a held-out year.
- Simple rules a beginner can read. Every entry has a stop.

How to write each file (one Python file per candidate, the BotScope bot format, like the example below):
- Only `from botscope.bot import Bot, Entry, Exit, NoTrade` and, if needed, the math / statistics modules. Nothing
  else: no files, no network, no subprocess, no orders, no print, no getattr/eval/exec, no names with double
  underscores. Files that do any of that are refused unread.
- Module level: one docstring, the imports, helper functions, and one Bot subclass. No other code.
- Class attributes: name (short, plain), version = "1.0", description (1-2 sentences), rules (plain English, one per
  line, mentioning the value of every setting in params), symbols, timeframe, sides, asset, max_trades_per_day = 1,
  flat_by_close ({spec['timeframe'] != '1Day'} for this goal), lookback_days (at least the longest *_days setting
  for daily bots), params (every number setting), tuned_on = None, status = "untested", notes (start with
  "Source: " and the source).
- entry(view) returns Entry(side, stop, target_or_None, reason) or NoTrade("reason"); exit(view, pos) returns
  Exit("reason") or None. view.bars holds finished bars only, oldest first; each bar has t, o, h, l, c, v.
  indicators(bars) is optional; each value may only use bars up to its own index.

Answer only with the JSON the schema asks for: {{"candidates": [{{"name", "idea" (one sentence), "source",
"why_it_fits" (one sentence), "code" (the whole file)}}]}}.

Example of the format (one of BotScope's own templates):
```python
{example}
```
"""


def ask(text: str, folder: Path, progress: dict, n: int, what: str = "candidate") -> list[dict]:
    """One headless Claude run. Streams progress into `progress`; returns the candidate list from its answer."""
    cmd = command()
    if not console.STATE["on"]:
        raise Unavailable("the Claude panel is switched off (Studio settings)")
    with tempfile.TemporaryFile() as err:
        try:
            p = subprocess.Popen(cmd, cwd=folder, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err,
                                 env=console._env(), text=True, start_new_session=True)
        except OSError as e:
            raise Unavailable(f"couldn't start Claude Code: {e}") from e
        with console._live_lock:
            console._live.add(p)                 # switching the Claude panel off stops research too
        timer = threading.Timer(TIMEOUT, console._kill, (p,))
        timer.start()
        searches, buf, answer, result = 0, "", None, {}
        try:
            p.stdin.write(text)
            p.stdin.close()
            for line in p.stdout:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = e.get("type")
                if t == "stream_event":
                    ev = e.get("event") or {}
                    blk = ev.get("content_block") or {}
                    if ev.get("type") == "content_block_start" and blk.get("type") in ("tool_use", "server_tool_use") \
                            and blk.get("name") in ("WebSearch", "web_search", "WebFetch", "web_fetch"):
                        searches += 1
                        progress["say"] = (f"{'Researching strategies that fit the goal' if what == 'candidate' else 'Looking up a replacement'}"
                                           f" ({searches} web look-up{'s' * (searches != 1)} so far)…")
                    d = ev.get("delta") or {}
                    piece = d.get("text") or d.get("partial_json") or ""
                    if piece:
                        buf += piece
                        k = min(buf.count('"code"'), n)
                        if k:
                            progress.update(phase="writing" if what == "candidate" else "retry",
                                            say=f"Writing {what} {k} of {n}…")
                elif t == "assistant":
                    for c in (e.get("message") or {}).get("content", []):
                        if c.get("type") == "tool_use" and c.get("name") == "StructuredOutput":
                            answer = c.get("input")
                elif t == "result":
                    result = e
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass
        finally:
            timer.cancel()
            console._kill(p)
            with console._live_lock:
                console._live.discard(p)
        if not console.STATE["on"]:
            raise Unavailable("the Claude panel was switched off during research")
        if p.returncode or result.get("is_error") or not result:
            err.seek(0)
            tail = _one_line(err.read()[-600:].decode("utf-8", "replace") or result.get("result")
                             or f"exit code {p.returncode}", 300)
            if p.returncode and p.returncode < 0:
                tail = "it took too long and was stopped" if not tail.strip() else tail
            raise Unavailable(f"Claude Code didn't finish: {tail}. If it says it isn't logged in, open the Terminal "
                              "tab, run `claude` once and log in")
    answer = result.get("structured_output") or answer or _json_in(result.get("result") or "")
    items = (answer or {}).get("candidates") if isinstance(answer, dict) else None
    if not isinstance(items, list) or not items:
        raise Unavailable("Claude Code answered without the candidate files")
    return [x for x in items if isinstance(x, dict)][:n]


def _json_in(text: str):
    s = text.find("{")
    e = text.rfind("}")
    if s < 0 or e <= s:
        return None
    try:
        return json.loads(text[s:e + 1])
    except json.JSONDecodeError:
        return None


def research(goal: str, spec: dict, run_id: str, folder: Path, progress: dict) -> list[dict]:
    """5 candidates for the run: accepted ones ({slug, path, label, idea, source, why}) and refused ones ({refused})
    after one retry each. Raises Unavailable when research can't run at all."""
    progress.update(phase="research", say="Asking your Claude Code to research strategies that fit the goal…")
    taken: set = set()
    first = ask(prompt(goal, spec, run_id), folder, progress, COUNT)
    got = [accept(x, spec, run_id, folder, taken) for x in first]
    got += [{"label": "Missing candidate", "idea": "", "source": "", "why": "",
             "refused": "Claude Code wrote fewer than 5 candidates"} for _ in range(COUNT - len(got))]
    bad = [i for i, g in enumerate(got) if g.get("refused")]
    if bad:
        progress.update(phase="retry", say=f"{len(bad)} candidate file{'s' * (len(bad) != 1)} refused; asking Claude "
                                           "for a replacement (one retry each)…")
        try:
            again = ask(prompt(goal, spec, run_id, len(bad), [got[i] for i in bad]), folder, progress, len(bad),
                        "replacement")
        except Unavailable as e:
            again = []
            for i in bad:
                got[i]["refused"] += f" (the retry didn't run: {_one_line(e, 120)})"
        for i, item in zip(bad, again):
            new = accept(item, spec, run_id, folder, taken)
            if new.get("refused"):
                new["refused"] = f"{new['refused']} (retry; first try: {got[i]['refused']})"
                new["code"] = new.get("code", "")
            got[i] = new
    for i, g in enumerate(got):                  # refused files are kept as text to read, never as a loadable .py
        if g.get("refused"):
            slug = scaffold._slug(f"{g['label']} {run_id}") or f"candidate_{i + 1}"
            g["slug"] = f"refused_{i + 1}_{slug}"[:90]
            if g.get("code"):
                (folder / f"{g['slug']}.refused.txt").write_text(
                    f"# Refused before running: {g['refused']}\n\n{g.pop('code')}")
        g.pop("code", None)
    if all(g.get("refused") for g in got):
        raise Unavailable("every researched candidate was refused: " + _one_line(got[0]["refused"], 200))
    return got
