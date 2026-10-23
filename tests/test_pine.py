"""Pine Script import: the common subset translates, everything else is listed, and the bot runs honestly."""
import pytest

from botscope import demo, loader, pine, pine_runtime, report, scaffold

MA_CROSS_V5 = '''//@version=5
strategy("MA Cross", overlay=true)
fastLen = input.int(10, "Fast")
slowLen = input.int(30, title="Slow")
fast = ta.sma(close, fastLen)
slow = ta.sma(close, slowLen)
plot(fast)
longCondition = ta.crossover(fast, slow)
if longCondition
    strategy.entry("Long", strategy.long)
shortCondition = ta.crossunder(fast, slow)
if (shortCondition)
    strategy.close("Long")
x = close > open ? 1 : 0
'''

RSI_V4 = '''//@version=4
strategy("RSI dip")
len = input(14)
lvl = input(30)
r = rsi(close, len)
strategy.entry("L", strategy.long, when = r < lvl)
strategy.close("L", when = r > 70)
strategy.exit("stop", "L", stop = lowest(low, 5))
'''


@pytest.fixture(autouse=True)
def _bots(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_BOTS_DIR", str(tmp_path / "bots"))
    (tmp_path / "bots").mkdir()
    monkeypatch.setattr(pine.checkpoints, "save", lambda label: {"id": "cp"})


def test_translate_the_common_subset_and_list_the_rest():
    t = pine.translate(MA_CROSS_V5)
    assert t["title"] == "MA Cross" and t["params"] == {"fastLen": 10, "slowLen": 30}
    assert t["long"] == ["longCondition"] and t["exit_long"] == ["(shortCondition)"]
    assert t["plots"] == ["fast"]
    assert ("x", "(1 if close > open else 0)") in t["series"]       # Pine's ?: translates now
    t4 = pine.translate(RSI_V4)
    assert t4["long"] == ["r < lvl"] and t4["exit_long"] == ["r > 70"] and t4["stop_long"] == "lowest(low, 5)"


def test_runtime_never_peeks():
    bars = demo.bars("SPY", __import__("datetime").date(2024, 1, 1), __import__("datetime").date(2024, 6, 1), "1Day")
    full = pine_runtime.run([("f", "sma(close, 5)"), ("x", "crossover(f, sma(close, 20))")], {}, bars)
    part = pine_runtime.run([("f", "sma(close, 5)"), ("x", "crossover(f, sma(close, 20))")], {}, bars[:60])
    assert full["f"][:60] == part["f"] and full["x"][:60] == part["x"]
    assert pine_runtime.run([("r", "rsi(close, 2)")], {}, bars)["r"][-1] is not None


@pytest.mark.parametrize("script", [MA_CROSS_V5, RSI_V4])
def test_imported_bot_passes_check_bot_and_runs_a_report(script):
    out = pine.write_bot(script, symbols=["SPY"])
    cls = loader.get(out["bot_id"])
    chk = scaffold.check_class(cls)
    assert chk["ok"], [c for c in chk["checks"] if not c["pass"]]
    rep = report.full_report(cls, fetch=demo.bars, crashes=False, save=False)
    assert rep["untested"].get("trades", 0) > 0
    assert bool(out["added"]) == (script is MA_CROSS_V5)


def test_nothing_translatable_is_an_error():
    with pytest.raises(ValueError, match="no strategy.entry"):
        pine.write_bot('strategy("x")\nplot(close)\n')


def test_ternaries_nested_and_inside_calls():
    assert pine._ternary("a > b ? 1 : c > d ? 2 : 3") == "(1 if a > b else (2 if c > d else 3))"
    assert pine._ternary("sma(close, fast ? 10 : 20)") == "sma(close,(10 if fast else 20))"
    import ast
    assert ast.dump(ast.parse(pine._ternary("a ? (b ? 1 : 2) : 3"))) == ast.dump(ast.parse("(1 if b else 2) if a else 3"))
    assert pine._ternary("a ? 1") == "a ? 1"                         # unbalanced: left alone, then listed
    env = pine_runtime.run([("x", "(close if close > open else open)")], {}, demo.bars("SPY", *_days(), "1Day", "sip")[:5])
    assert all(v == max(c, o) or c == o for v, c, o in zip(env["x"], env["close"], env["open"]))


def _days():
    from datetime import date
    return date(2025, 3, 3), date(2025, 3, 14)


def test_inline_lengths_count_toward_lookback():
    t = pine.translate('strategy("x")\ntrend = close > ta.sma(close, 200) ? 1 : 0\n'
                       'strategy.entry("L", strategy.long, when = trend == 1 and ta.rsi(close, 5) < 30)\n')
    assert sorted(pine._inline_lengths(t)) == [5, 200]


def test_stop_at_the_signal_candles_own_low_is_warned():
    t = pine.translate(RSI_V4)
    assert "ta.atr(14)" in pine.stop_warnings(t)[0]
    t["stop_long"] = "lowest(low, 5)[1]"
    assert pine.stop_warnings(t) == []


def test_on_off_inputs_and_close_all_translate():
    t = pine.translate('''//@version=5
strategy("Breakout filter")
useFilter = input.bool(true, "Use filter")
quiet = input(false)
longCond = close > ta.highest(high, 20)[1] and (not useFilter or close > ta.ema(close, 200))
strategy.entry("L", strategy.long, when=longCond)
if close < ta.lowest(low, 10)[1]
    strategy.close_all()
strategy.close_all(when=quiet)
if bar_index % 5 == 0
    strategy.close_all()
''')
    assert ("useFilter", "True") in t["series"] and ("quiet", "False") in t["series"]
    assert t["long"] == ["longCond"] and "useFilter" not in t["params"]
    assert t["exit_long"] == t["exit_short"] == ["close < lowest(low, 10)[1]", "quiet"]
    assert [n["line"] for n in t["not_translated"]] == ["if bar_index % 5 == 0 → strategy.close_all()"]


def test_if_blocks_never_turn_sometimes_into_always():
    t = pine.translate('''strategy("x")
r = ta.rsi(close, 14)
lvl = 30
if r < 20
    lvl := 40
if ta.crossover(r, lvl)
    strategy.entry("L", strategy.long)
    alert("buy")
    if close > open
        strategy.close("L")
if r > 80
    strategy.close("L")
else
    strategy.close("L", when=r > 70)
''')
    assert t["series"] == [("r", "rsi(close, 14)"), ("lvl", "30")]        # lvl := 40 only sometimes: not translated
    assert t["long"] == ["crossover(r, lvl)"] and t["exit_long"] == ["r > 80"]   # every line in the block gets its if
    why = {n["line"]: n["why"] for n in t["not_translated"]}
    assert "only set-always" in why["if r < 20 → lvl := 40"]
    assert "nested" in why["if ta.crossover(r, lvl) → if close > open"] and "nested" in why["if ta.crossover(r, lvl) → strategy.close(\"L\")"]
    assert "isn't translated" in why['strategy.close("L", when=r > 70)']             # the else body never runs always
