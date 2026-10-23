"""Offline checks of new_bot (one-sentence start) and check_bot (rules match the code)."""
import shutil

import pytest

from botscope import loader, scaffold


@pytest.fixture
def bots(tmp_path, monkeypatch):
    d = tmp_path / "bots"
    shutil.copytree(loader.bots_dir(), d, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setenv("BOTSCOPE_BOTS_DIR", str(d))
    return d


def test_example_bots_pass_the_check():
    found = sorted(f.stem for f in loader.bots_dir().glob("*.py"))
    assert {"first_hour_breakout", "nr7_swing", "inside_bar_breakout", "pullback_swing"} <= set(found)
    for b in found:                                    # every example bot, including ones added later
        r = scaffold.check_bot(b)
        assert r["ok"], (b, [c for c in r["checks"] if not c["pass"]])


def test_new_bot_loads_runs_and_says_what_is_missing(bots):
    out = scaffold.new_bot("Gap and go", 'Buys stocks that gap up 2% and hold the "first" 5 minutes.', "5Min", ["aapl"])
    assert (bots / "gap_and_go.py").exists() and out["checkpoint_before"]
    r = scaffold.check_bot("gap_and_go")
    by = {c["check"]: c for c in r["checks"]}
    assert by["loads"]["pass"] and by["no peeking"]["pass"] and by["runs on made-up bars"]["pass"]
    assert not by["has plain-English rules"]["pass"] and "TODO" in by["has plain-English rules"]["detail"]
    assert loader.get("gap_and_go").symbols == ["AAPL"]
    with pytest.raises(ValueError):
        scaffold.new_bot("Gap and go", "again")


def test_rules_check_spots_a_setting_the_words_never_mention(bots):
    f = bots / "nr7_swing.py"
    f.write_text(f.read_text().replace('"max_hold_days": 10', '"max_hold_days": 12'))
    r = scaffold.check_bot("nr7_swing")
    assert not r["ok"] and "max_hold_days = 12" in next(c for c in r["checks"] if c["check"].startswith("rules"))["detail"]


def test_broken_bot_file_is_reported(bots):
    (bots / "broken.py").write_text("this is not python\n")
    assert scaffold.check_bot("broken")["checks"][0]["pass"] is False


def test_make_shadow_copies_a_bot_as_the_next_version(bots):
    out = scaffold.make_shadow("first_hour_breakout")
    assert out["bot_id"] == "first_hour_breakout_v2_0" and out["shadows"] == "first_hour_breakout" and out["checkpoint_before"]
    new = loader.get("first_hour_breakout_v2_0")
    assert new.shadows == "first_hour_breakout" and new.version == "2.0" and new.name == "First hour breakout v2.0"
    assert loader.get("first_hour_breakout").shadows is None and scaffold.check_bot("first_hour_breakout_v2_0")["ok"]
    from botscope import shadow
    assert shadow.families() == {"first_hour_breakout": ["first_hour_breakout", "first_hour_breakout_v2_0"]}
    with pytest.raises(ValueError):
        scaffold.make_shadow("first_hour_breakout")                       # same version twice


def test_check_bot_flags_history_days_on_a_daily_bot(bots):
    f = bots / "nr7_swing.py"
    f.write_text(f.read_text().replace('    max_trades_per_day = 1\n', '    max_trades_per_day = 1\n    history_days = 1\n', 1))
    r = scaffold.check_bot("nr7_swing")
    by = {c["check"]: c for c in r["checks"]}
    assert not r["ok"] and "view.bars" in by["history_days only for intraday bots"]["detail"]
    assert "history_days only for intraday bots" not in {c["check"] for c in scaffold.check_bot("pullback_swing")["checks"]}


def test_check_bot_flags_a_daily_bot_that_hides_its_lookback(bots):
    f = bots / "pullback_swing.py"
    f.write_text(f.read_text().replace("    lookback_days = 200\n", "", 1))
    by = {c["check"]: c for c in scaffold.check_bot("pullback_swing")["checks"]}
    assert "set lookback_days = 200" in by["declares its lookback"]["detail"]
