"""Free mode: run any BotScope tool from the terminal, no AI needed (and no AI usage spent).

    botscope                         list the tools
    botscope help run_backtest       one tool: what it does and its settings
    botscope luck_meter first_hour_breakout
    botscope bot_arena first_hour_breakout params_a='{"r_multiple": 1.5}' params_b='{"r_multiple": 2}'
    botscope weekly_recap --json

The first plain word fills the tool's first setting; the rest are name=value (JSON where it parses, else text).
Routine runs (the end-of-day log, the weekly recap, the pre-flight list) work the same from a schedule. Claude only
needs to wake up to think: explain a result, write a bot, or decide something with you. Paper only; nothing here
places an order. Not financial advice.
"""
from __future__ import annotations

import difflib
import inspect
import json
import re
import sys

HIDDEN = {"main"}


def tools() -> dict:
    from . import server
    out = {}
    for name, fn in vars(server).items():
        if inspect.isfunction(fn) and fn.__module__ == server.__name__ and not name.startswith("_") \
                and name not in HIDDEN and fn.__doc__:
            out[name] = fn
    return out


HEAVY = {"honest_report", "luck_meter", "crash_test", "what_if_stop_target", "strategy_factory",
         "robustness_check", "import_pine",
         "honest_optimizer", "team_report"}   # many backtests: minutes, not seconds


def weight(name: str, fn) -> str:
    """How long a tool takes on this computer (no AI either way): light / 1 backtest / heavy."""
    if name in HEAVY:
        return "heavy"
    return "1 backtest" if "_one_backtest" in inspect.getsource(fn) else "light"


def tools_table() -> str:
    """The README's "All tools" table, made from the code (weight + first sentence of each tool's description)."""
    rows = ["| Tool | Weight | What it does |", "|---|---|---|"]
    for name, fn in sorted(tools().items()):
        rows.append(f"| `{name}` | {weight(name, fn)} | {first_sentence(fn.__doc__).replace('|', '/')} |")
    return "\n".join(rows)


def tool_help(name: str, fn) -> str:
    """One tool in full: weight, its whole description and each setting (required ones first)."""
    lines = [f"{name}  [{weight(name, fn)}]", "", inspect.cleandoc(fn.__doc__), "", "Settings:"]
    ps = sorted(inspect.signature(fn).parameters.values(), key=lambda p: p.default is not inspect.Parameter.empty)
    for p in ps:
        kind = getattr(p.annotation, "__name__", None) or str(p.annotation).replace("typing.", "")
        lines.append(f"  {p.name:22} {kind:20} " + ("required" if p.default is inspect.Parameter.empty
                                                    else f"default {p.default!r}"))
    if not ps:
        lines.append("  none")
    need = [p.name for p in ps if p.default is inspect.Parameter.empty]
    lines += ["", f"Example: botscope {name}" + "".join(f" <{n}>" for n in need)]
    return "\n".join(lines)


def parse(fn, args: list[str]) -> dict:
    sig = inspect.signature(fn).parameters
    params = list(sig)
    text = {p for p, v in sig.items() if str(v.annotation).replace(" ", "") in ("str", "str|None", "<class'str'>")}
    lists = {p for p, v in sig.items() if str(v.annotation).replace(" ", "").startswith("list[str]")}
    conv = lambda p, v: v if p in text else [x.strip() for x in v.split(",") if x.strip()] \
        if p in lists and not v.lstrip().startswith("[") else _value(v)            # SPY,QQQ -> ["SPY", "QQQ"]
    kw, plain = {}, []
    for a in args:
        if "=" in a and a.split("=", 1)[0] in params:
            k, v = a.split("=", 1)
            kw[k] = conv(k, v)
        else:
            plain.append(a)
    free = [p for p in params if p not in kw]
    if len(plain) > len(free):
        raise ValueError(f"too many plain values; settings are: {', '.join(params)}")
    kw.update((p, conv(p, v)) for p, v in zip(free, plain))       # a run id like 1017200950 stays text
    return kw


def first_sentence(doc: str) -> str:
    """The doc's first sentence, not cut at 'e.g.' or 'i.e.'."""
    text = " ".join(doc.strip().split("\n\n")[0].split())
    m = re.search(r"(?<!e\.g)(?<!i\.e)\.(\s|$)", text)
    return text[:m.start()] if m else text


def missing(fn, kw: dict) -> str | None:
    """None when every required setting is there, else a plain-English hint with an example."""
    sig = inspect.signature(fn)
    need = [p for p, v in sig.parameters.items() if v.default is inspect.Parameter.empty and p not in kw]
    if not need:
        return None
    msg = f"needs: {', '.join(need)}. Example: botscope {fn.__name__} " + " ".join(f"<{p}>" for p in need)
    if any(p in ("bot", "bot_a") for p in need):
        try:
            from . import loader
            msg += "\nyour bots: " + ", ".join(sorted(loader.load_all()[0]))
        except Exception:   # noqa: BLE001 - a hint only
            pass
    return msg


def _value(v: str):
    try:
        return json.loads(v)
    except ValueError:
        return v


def _scalar(v) -> str:
    if isinstance(v, float):
        return f"{v:,.2f}"
    if v is None:
        return "–"
    return str(v)


# Shown under a tool's markdown when the markdown doesn't already say them: which days the numbers are from, the data
# source, and the warnings and next step that sit next to the markdown in the result.
AFTER_MARKDOWN = ("period", "data", "drop_note", "same_bet", "same_bets", "tries_note", "warnings", "verdict", "next",
                  "note", "demo_note")


WIDE = 70       # a table cell longer than this turns the table into one block per row


def render(obj, indent: str = "") -> list[str]:
    """Plain-text tables: scalars as 'key: value', lists of flat dicts as aligned columns."""
    if isinstance(obj, dict) and isinstance(obj.get("markdown"), str):
        md = obj["markdown"]
        top = [f"**{obj['data_badge']}**", ""] if obj.get("data_badge") and obj["data_badge"] not in md else []
        extra = [f"{k}: " + ("; ".join(map(str, v)) if isinstance(v, list) else str(v))
                 for k in AFTER_MARKDOWN if (v := obj.get(k)) and isinstance(v, (str, list))
                 and all(isinstance(x, str) for x in (v if isinstance(v, list) else [v]))
                 and (v if isinstance(v, str) else "; ".join(v)).rstrip(".") not in md]
        return top + [md] + ([""] + extra if extra else [])
    lines = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)) and v:
                lines.append(f"{indent}{k}:")
                lines += render(v, indent + "  ")
            else:
                lines.append(f"{indent}{k}: {_scalar(v)}")
    elif isinstance(obj, list):
        flat = obj and all(isinstance(x, dict) and all(not isinstance(y, (dict, list)) for y in x.values()) for x in obj)
        if flat and any(len(_scalar(y)) > WIDE for x in obj for y in x.values()):
            for x in obj:                           # a long cell would stretch every row: one block per row instead
                first, *rest = x.items()
                lines.append(f"{indent}- {first[0]}: {_scalar(first[1])}")
                lines += [f"{indent}  {k}: {_scalar(v)}" for k, v in rest if _scalar(v) not in ("–", "")]
        elif flat:
            cols = list(dict.fromkeys(k for x in obj for k in x))
            rows = [[_scalar(x.get(c)) for c in cols] for x in obj]
            w = [max(len(c), *(len(r[i]) for r in rows)) for i, c in enumerate(cols)]
            lines.append(indent + "  ".join(c.ljust(w[i]) for i, c in enumerate(cols)))
            lines += [indent + "  ".join(r[i].ljust(w[i]) for i in range(len(cols))) for r in rows]
        else:
            for x in obj:
                if isinstance(x, (dict, list)):
                    lines += render(x, indent + "  ")
                    lines.append("")
                else:
                    lines.append(f"{indent}- {_scalar(x)}")
    else:
        lines.append(indent + _scalar(obj))
    return lines


def main(argv: list[str] | None = None, wait: bool = True) -> int:
    argv = sys.argv[1:] if argv is None else argv
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    ts = tools()
    if len(argv) == 2 and argv[0] in ("-h", "--help", "help"):
        if argv[1] in ts:
            print(tool_help(argv[1], ts[argv[1]]))
            return 0
        argv = argv[1:]                     # unknown name: falls through to the "did you mean" below
    if argv[:1] == ["demo"]:
        return demo(argv[1:], wait)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("BotScope free mode: run a tool without AI. Usage: botscope <tool> [value] [name=value ...] [--json]")
        from . import demo as d
        if d.active():
            print(f"{d.BADGE}: no Alpaca keys found, so every tool runs on made-up prices. New here? "
                  "`botscope demo` is the 2-minute tour; `botscope doctor` says how to add free keys.")
        print("Weight = time on this computer: light (seconds), 1 backtest (up to a minute), heavy (minutes).\n")
        for name, fn in sorted(ts.items()):
            first = first_sentence(fn.__doc__)
            print(f"  {name:28} {'[' + weight(name, fn) + ']':13} {first[:80] + ('...' if len(first) > 80 else '')}")
        return 0
    if argv[0] == "publish-check" and "--make-repo" in argv:              # botscope publish-check --make-repo
        argv = [a for a in argv if a != "--make-repo"] + ["how=make_repo"]
    if argv[0] == "publish-check" and "--update" in argv:                 # botscope publish-check --update
        argv = [a for a in argv if a != "--update"] + ["how=update"]
    name = {"publish-check": "publish_check"}.get(argv[0], argv[0])
    if name not in ts:
        close = difflib.get_close_matches(name, ts, n=1)
        hint = f" Did you mean {close[0]}?" if close else ""
        print(f"no tool {name!r}.{hint} Run `botscope` to list them.", file=sys.stderr)
        return 1
    try:
        kw = parse(ts[name], argv[1:])
    except ValueError as e:
        print(f"{name}: {e}", file=sys.stderr)
        return 1
    if hint := missing(ts[name], kw):
        print(f"{name} {hint}", file=sys.stderr)
        return 1
    sys.modules[ts[name].__module__].FREE_MODE = True      # doctor then checks Claude Code really sees BotScope
    try:
        out = ts[name](**kw)
    except Exception as e:  # noqa: BLE001 - say what broke instead of a wall of traceback
        print(f"{name} stopped with an error ({type(e).__name__}): {e}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=1, default=str) if as_json else "\n".join(render(out)))
    _keep_page_open(wait)
    if isinstance(out, dict) and out.get("ok") is False:          # publish-check: fail loudly
        return 3
    return 1 if isinstance(out, dict) and "error" in out and len(out) == 1 else 0


def demo(argv: list[str], wait: bool = True) -> int:
    """`botscope demo`: the 2-minute tour in one command, always on made-up prices (even when you have keys), with
    its own journal so nothing mixes with your real results."""
    import os
    os.environ["BOTSCOPE_DEMO"] = "1"
    from . import demo as d, doctor, server, strategy_factory
    goal = " ".join(argv) or "a calm daily ETF bot"
    print(f"BotScope demo ({d.BADGE}: made-up prices generated on this computer; results mean nothing about real "
          "markets). Paper only. Not financial advice.\n")
    print("1. Setup check:", doctor.check(via_mcp=True)["summary"].split(". To switch")[0])
    print(f'\n2. Strategy factory: "{goal}" (a few candidate bots, each tested honestly)\n')
    fac = strategy_factory.run(goal, demo=True)
    print(fac["markdown"])
    print(f"\n{fac['tries_note']}\nNext: {fac['next']}")
    paper = d.fill_paper_days()
    if "paper_results" in paper:
        print(f"\n3. Demo paper days: the example bots paper traded {paper['from']} to {paper['to']} on made-up prices "
              f"({paper['paper_results']} closed trades), so the confidence meter and graduation test have something to show.")
    url = server.open_studio()["url"]
    print(f"\n4. BotScope Studio: {url}#factory\n   Try the Bot view (click a candle), the Desk, and the Tutorial tab.")
    print("\n" + d.HOW_TO_SWITCH)
    _keep_page_open(wait)
    return 0


def _keep_page_open(wait: bool) -> None:
    """A page tool starts the page server inside this process, so it dies when the command ends. In a terminal,
    keep it up until Ctrl+C; from a schedule, say so instead of hanging."""
    from . import view
    if view._server is None:
        return
    if wait and sys.stdin.isatty():
        print("\nThe page is open while this runs. Press Ctrl+C to stop.", flush=True)
        try:
            import threading
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    else:
        print("\nnote: the page closes when this command ends; run it in a terminal to keep it open.",
              file=sys.stderr)                       # stderr, so `--json` output stays valid JSON


if __name__ == "__main__":
    sys.exit(main())
