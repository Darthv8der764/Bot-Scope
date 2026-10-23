"""Team of bots: one combined result, the team's worst drop and the overlap between bots."""
import shutil
from pathlib import Path

import pytest

from botscope import demo, team


@pytest.fixture(autouse=True)
def bots(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_BOTS_DIR", str(tmp_path / "bots"))
    (tmp_path / "bots").mkdir()
    for b in ("pullback_swing.py", "nr7_swing.py"):
        shutil.copy(Path(team.__file__).resolve().parent.parent / "bots" / b, tmp_path / "bots")


def test_team_adds_up_and_compares_drops():
    out = team.team(fetch=demo.bars)
    t = out["team"]
    assert t["bots"] == 2 and t["trades"] == sum(b["trades"] for b in out["bots"])
    assert t["total_r"] == pytest.approx(sum(b["total_r"] for b in out["bots"]), abs=0.05)
    assert t["worst_drop_r"] >= t["sum_of_own_worst_drops_r"] - 0.01     # a team can't drop more than all at once
    assert out["overlap"][0]["bots"] == ["NR7 swing", "Pullback swing"] and "**Team**" in out["markdown"]


def test_one_bot_is_not_a_team():
    with pytest.raises(ValueError, match="at least 2"):
        team.team(["pullback_swing"], fetch=demo.bars)


def test_drop_note_never_says_they_lose_together_without_losses():
    from botscope import team
    assert "no bot had a losing stretch" in team.drop_note(0.0, 0.0)
    assert "don't all lose at the same time" in team.drop_note(-30.0, -100.0)
    assert "tend to lose together" in team.drop_note(-90.0, -100.0)
