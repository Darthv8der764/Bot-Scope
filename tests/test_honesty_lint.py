"""Honesty lint: no tool, page, skill or doc may show a win % or promise results. Counts and confidence levels only.
Quoting someone else's claim to fact-check it is fine (allowed lines say so)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BAD = re.compile(r"(?i)win[_ ]?rate|win ?%|winrate|guarantee|can'?t lose|risk[- ]free|sure thing"
                 r"|garantiz|sin riesgo|no puedes perder|tasa de acierto|% de aciertos|ganancia segura")   # Spanish too
ALLOWED = ("never a win %", "every number they promise")      # the rule itself, and fact-checking a YouTuber's claim


def files():
    for pat in ("botscope/**/*.py", "botscope/web/*.html", "botscope/web/*.js", "skills/**/*.md", "bots/*.py", "README.md", "docs/*.md", ".claude-plugin/*.json"):
        yield from (p for p in ROOT.glob(pat) if "vendor" not in p.parts and p.name != "scam.py")
        # scam.py is the red-flag detector: it has to spell out the very words it warns about


def test_no_win_percent_or_promises_anywhere():
    hits = [f"{p.relative_to(ROOT)}:{i}: {line.strip()}" for p in files()
            for i, line in enumerate(p.read_text().splitlines(), 1)
            if BAD.search(line) and not any(a in line for a in ALLOWED)]
    assert not hits, "honesty lint:\n" + "\n".join(hits)


# A projection must carry its label on the same line: a range, a sample size, or "untested".
PROJ = re.compile(r"(?i)projected|projection|expected (return|profit)|you(\'ll| will) (make|earn)")
TITLES = ("Cross-Section of Expected Returns",)       # a cited paper title in docs/, not a projection
LABEL = re.compile(r"(?i)range|sample|untested|typical|5/50/95|middle|n=|trades?\b")


def test_projections_are_labeled():
    hits = [f"{p.relative_to(ROOT)}:{i}: {line.strip()}" for p in files()
            for i, line in enumerate(p.read_text().splitlines(), 1)
            if PROJ.search(line) and not LABEL.search(line) and not any(t in line for t in TITLES)]
    assert not hits, "unlabeled projection:\n" + "\n".join(hits)


def test_projection_gate_catches_a_bare_number():
    assert PROJ.search("Projected: +$120 next month") and not LABEL.search("Projected: +$120 next month")
    assert LABEL.search("a typical month from untested history: -$40 to +$120 (range, 48 trades)")


def test_lint_catches_a_win_rate():
    assert BAD.search('"win_rate_pct": 41.7') and BAD.search("Win rate 60%") and not BAD.search("5 of 12 won")


def test_tool_outputs_pass_the_gate_too():
    """Run the tools that work offline and lint what they actually return (strings built at run time included)."""
    import json
    from botscope import server
    calls = [("list_bots", {}), ("check_bot", {"bot": "first_hour_breakout"}), ("size_by_risk", {"entry": 50, "stop": 49}),
             ("shadow_scoreboard", {}), ("loss_autopsy", {}), ("veto_scorecard", {}), ("list_checkpoints", {}),
             ("check_order", {"symbol": "AAPL", "side": "buy", "qty": 1}), ("nutrition_label", {"bot": "nr7_swing"}),
             ("scam_check", {"text": "a simple moving average crossover, tested on 10 years"})]
    for name, kw in calls:
        out = json.dumps(getattr(server, name)(**kw), default=str)
        bad = [m.group(0) for m in BAD.finditer(out)]
        assert not bad, f"{name} returned {bad}"
        assert not [m.group(0) for m in PROJ.finditer(out) if not LABEL.search(out)], f"{name}: unlabeled projection"


def test_new_result_tools_name_their_period(monkeypatch):
    """BotScope's rule: every number says whether it's from TUNED days, UNTESTED days, or live paper."""
    import json
    from botscope import autopsy, eventdays, playground, shadow
    from botscope.backtest import Trade
    t = Trade("SPY", "2026-01-05", "long", 1, 1, 1, "", "", 0.5, 0.5, 0, t_in="2026-01-05T10:00:00-05:00", risk_pct=1)
    c = {"bot": "x", "name": "X", "window": {"from": "2026-01-01", "to": "2026-03-01", "period": "untested"},
         "trading_days": 40, "problems": [], "seconds": 0, "trades": [t] * 12, "ghosts": []}
    monkeypatch.setattr(playground, "precompute", lambda bot_id, fetch=None: c)
    outs = {"rule_playground": playground.play("x"),
            "event_days": eventdays.event_days("x", econ=lambda a, b: []),
            "shadow_scoreboard": shadow.scoreboard(bots={}),
            "loss_autopsy": autopsy.autopsy()}
    for name, out in outs.items():
        text = json.dumps(out).lower()
        assert "untested" in text or "paper" in text, f"{name} doesn't say which days its numbers are from"


def test_research_notes_and_example_bots_are_covered():
    notes = [p.name for p in files() if p.parent.name == "docs"]
    assert "why-the-best-setting-looks-better.md" in notes
    assert "pullback_swing.py" in [p.name for p in files() if p.parent.name == "bots"]   # their text shows in tools


def test_readme_links_to_every_research_note():
    readme = (ROOT / "README.md").read_text()
    missing = [p.name for p in (ROOT / "docs").glob("*.md") if f"docs/{p.name}" not in readme]
    assert not missing, f"research notes missing from the README: {missing}"


def test_readme_lists_every_example_bot():
    readme = (ROOT / "README.md").read_text()
    missing = [p.name for p in (ROOT / "bots").glob("*.py") if f"(bots/{p.name})" not in readme]
    assert not missing, f"example bots missing from the README table: {missing}"


def test_every_example_bot_says_what_its_honest_report_found():
    """An example bot's file carries its latest real honest report (with the date and data), or says there is none yet:
    "new and untested" next to a report that lost money would be a quiet hype."""
    import ast
    for f in sorted((ROOT / "bots").glob("*.py")):
        doc = ast.get_docstring(ast.parse(f.read_text())) or ""
        assert ("Honest report (20" in doc and "UNTESTED" in doc) or "No BotScope honest report is saved" in doc, f.name
        assert "New and untested" not in doc or "Honest report (" not in doc, f.name
