"""Offline checks of the daily pre-flight list."""
from datetime import date

import pytest

from botscope import guard, preflight


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_JOURNAL_DIR", str(tmp_path))


D1, D2, D3 = date(2026, 10, 14), date(2026, 10, 15), date(2026, 10, 16)


def test_nothing_runs_until_you_answer():
    s = preflight.settings_for(D1)
    assert s["answered_by"] == "nobody yet" and not any(s["bots"].values())


def test_no_answer_means_yesterdays_settings():
    preflight.answer({"inside_bar_breakout": True, "nr7_swing": True}, D1)
    s = preflight.settings_for(D2)
    assert s["answered_by"] == "yesterday (no answer)" and s["bots"]["inside_bar_breakout"] and s["bots"]["nr7_swing"]
    preflight.answer({"nr7_swing": False}, D2)                          # only nr7 changed today
    s = preflight.settings_for(D3)
    assert s["bots"] == {**s["bots"], "inside_bar_breakout": True, "nr7_swing": False}
    assert preflight.settings_for(D1)["bots"]["nr7_swing"]               # the past is not rewritten


def test_stop_turns_everything_off_but_keeps_answers():
    preflight.answer({"inside_bar_breakout": True}, D1)
    guard.stop_everything()
    s = preflight.settings_for(D2)
    assert not any(s["bots"].values()) and "STOP" in s["answered_by"]
    guard.resume(confirm=True)
    assert preflight.is_on("inside_bar_breakout", D2)


def test_list_flags_failed_bots_and_rejects_unknown(relabel):
    relabel("first_hour_breakout", status="failed")
    lst = preflight.today_list(D2, events=[])
    fhb = next(b for b in lst["bots"] if b["id"] == "first_hour_breakout")
    assert fhb["flag"] == "red" and "failed" in fhb["warnings"][0]
    with pytest.raises(ValueError):
        preflight.answer({"no_such_bot": True}, D2)
