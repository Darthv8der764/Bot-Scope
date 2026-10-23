"""Free mode: the terminal runs the same tools with no AI."""
import json

from botscope import cli, server


def test_lists_every_tool(capsys):
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    for name in ("run_backtest", "luck_meter", "bot_arena", "weekly_recap", "teach_me", "stop_everything"):
        assert name in out
    assert "main" not in cli.tools()


def test_parse_plain_and_named_values():
    kw = cli.parse(server.bot_arena, ["orb", 'params_a={"r_multiple": 1.5}', "days=20"])
    assert kw == {"bot_a": "orb", "params_a": {"r_multiple": 1.5}, "days": 20}
    kw = cli.parse(server.run_backtest, ["orb", '["AAPL","MSFT"]'])
    assert kw == {"bot": "orb", "symbols": ["AAPL", "MSFT"]}
    kw = cli.parse(server.adopt_candidate, ["1017200950", "dip_buy_1017200950"])     # text settings stay text
    assert kw == {"run": "1017200950", "candidate": "dip_buy_1017200950"}
    assert cli.parse(server.adopt_candidate, ["run=0101", "candidate=x"])["run"] == "0101"
    assert cli.parse(server.run_backtest, ["orb", "SPY,QQQ"])["symbols"] == ["SPY", "QQQ"]   # not letter by letter
    assert cli.parse(server.run_backtest, ["orb", "symbols=SPY"])["symbols"] == ["SPY"]
    try:
        cli.parse(server.list_bots, ["x"])
        assert False
    except ValueError as e:
        assert "too many" in str(e)


def test_runs_a_tool_as_table_and_json(capsys):
    assert cli.main(["list_bots"]) == 0
    assert "First hour breakout" in capsys.readouterr().out
    assert cli.main(["list_bots", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["bots"]


def test_unknown_tool_and_tool_errors_exit_1(capsys):
    assert cli.main(["nope"]) == 1
    assert cli.main(["nutrition_label", "no_such_bot"]) == 1


def test_render_table():
    lines = cli.render({"rows": [{"a": 1, "b": 2.5}, {"a": 10, "b": None}], "x": "y"})
    assert lines[0] == "rows:" and lines[1].split() == ["a", "b"] and lines[3].split() == ["10", "–"]
    assert lines[-1] == "x: y"


def test_missing_setting_says_what_and_shows_example(capsys):
    assert cli.main(["run_backtest"]) == 1
    err = capsys.readouterr().err
    assert "needs: bot" in err and "botscope run_backtest <bot>" in err and "first_hour_breakout" in err
    assert "positional argument" not in err


def test_help_line_not_cut_at_eg():
    assert cli.first_sentence("Save answers, e.g. 'a on'. More here.") == "Save answers, e.g. 'a on'"
    assert cli.first_sentence("One line only") == "One line only"


def test_unknown_tool_suggests_close_name(capsys):
    assert cli.main(["luck_metre"]) == 1
    assert "Did you mean luck_meter?" in capsys.readouterr().err


def test_crash_inside_a_tool_is_not_called_a_settings_problem(capsys, monkeypatch):
    def boom(bot: str) -> dict:
        """Boom."""
        raise TypeError("bad math inside")
    monkeypatch.setattr(cli, "tools", lambda: {"boom": boom})
    assert cli.main(["boom", "x"]) == 2
    assert "stopped with an error (TypeError): bad math inside" in capsys.readouterr().err


def test_page_tool_warns_page_closes_when_not_in_a_terminal(capsys, monkeypatch):
    from botscope import view
    monkeypatch.setattr(view, "_server", object())
    monkeypatch.setattr(cli, "tools", lambda: {"pg": lambda: {"url": "x"}})
    assert cli.main(["pg"], wait=False) == 0
    assert "page closes when this command ends" in capsys.readouterr().err


def test_every_tool_has_a_weight():
    w = {n: cli.weight(n, f) for n, f in cli.tools().items()}
    assert set(w.values()) <= {"light", "1 backtest", "heavy"}
    assert w["honest_report"] == "heavy" and w["run_backtest"] == "1 backtest" and w["morning_brief"] == "light"
    assert cli.HEAVY <= set(w)


def test_readme_tools_table_matches_the_code():
    """Docs drift: the README's All tools table must be the one the code makes (regenerate it when a tool changes:
    python -c 'from botscope import cli; print(cli.tools_table())')."""
    from pathlib import Path
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text()
    block = readme.split("<!-- tools:start -->\n", 1)[1].split("\n<!-- tools:end -->", 1)[0]
    assert block == cli.tools_table()


def test_help_for_one_tool_shows_its_settings(capsys):
    assert cli.main(["help", "run_backtest"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("run_backtest  [1 backtest]") and "Settings:" in out
    assert "bot " in out and "required" in out and "default" in out and "Example: botscope run_backtest <bot>" in out
    assert cli.main(["help"]) == 0 and "luck_meter" in capsys.readouterr().out      # plain help still lists all


def test_help_with_a_typo_suggests_the_tool(capsys):
    assert cli.main(["help", "luckmeter"]) == 1
    assert "Did you mean luck_meter?" in capsys.readouterr().err


def test_markdown_results_still_say_period_source_and_warnings():
    out = {"data_badge": "DEMO DATA", "markdown": "| a |\n|---|\n| 1 |", "period": "UNTESTED years",
           "data": "Alpaca SIP", "same_bet": ["A and B are one bet"], "note": "Not financial advice.", "url": "x",
           "verdict": "keep"}
    text = "\n".join(cli.render(out))
    assert text.startswith("**DEMO DATA**") and "period: UNTESTED years" in text and "data: Alpaca SIP" in text
    assert "same_bet: A and B are one bet" in text and "url" not in text
    again = "\n".join(cli.render({"markdown": "x. Not financial advice.", "note": "Not financial advice."}))
    assert again.count("Not financial advice") == 1                  # nothing said twice


def test_a_long_cell_turns_the_table_into_blocks():
    rows = [{"check": "Data", "ok": True, "detail": "DEMO DATA: " + "x" * 120, "fix": ""},
            {"check": "Bots", "ok": True, "detail": "5 load", "fix": ""}]
    lines = cli.render({"checks": rows})
    assert lines[1] == "  - check: Data" and lines[2] == "    ok: True" and lines[3].startswith("    detail: DEMO DATA")
    assert "  - check: Bots" in lines and not any("fix" in ln for ln in lines)
    assert max(len(ln) for ln in lines if "x" * 50 not in ln) < 40          # no row padded out to the long cell


def test_no_arguments_in_demo_points_at_the_tour(capsys, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_DEMO", "1")
    assert cli.main([]) == 0
    assert "`botscope demo` is the 2-minute tour" in capsys.readouterr().out
