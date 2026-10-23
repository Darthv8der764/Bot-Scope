"""Offline checks of checkpoints / undo for bot files (a temporary bots folder)."""
import shutil

import pytest

from botscope import checkpoints, loader


@pytest.fixture
def bots(tmp_path, monkeypatch):
    d = tmp_path / "bots"
    shutil.copytree(loader.bots_dir(), d, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setenv("BOTSCOPE_BOTS_DIR", str(d))
    return d


def test_save_skips_when_nothing_changed(bots):
    a = checkpoints.save("first")
    assert checkpoints.save("again")["unchanged"] and checkpoints.save("again")["id"] == a["id"]


def test_change_diff_restore_and_undo_the_restore(bots):
    cp = checkpoints.save("before my edit")
    f = bots / "nr7_swing.py"
    orig = f.read_text()
    f.write_text(orig.replace('"r_multiple": 2.0', '"r_multiple": 3.0'))
    (bots / "new_bot.py").write_text("# new\n")
    lst = checkpoints.list_all()["checkpoints"][0]
    assert lst["id"] == cp["id"] and lst["changed_since"] == ["new_bot.py", "nr7_swing.py"]
    ch = checkpoints.changes(cp["id"])
    d = next(x for x in ch["diffs"] if x["file"] == "nr7_swing.py")["diff"]
    assert '-    params = {"nr_days": 7, "r_multiple": 2.0' in d and '"r_multiple": 3.0' in d
    assert "question" in checkpoints.restore(cp["id"])
    assert '"r_multiple": 3.0' in f.read_text()                       # nothing happens without confirm
    out = checkpoints.restore(cp["id"], confirm=True)
    assert f.read_text() == orig and out["left_in_place"] == ["new_bot.py"]
    checkpoints.restore(out["undo_with"], confirm=True)                # undo the undo
    assert '"r_multiple": 3.0' in f.read_text()


def test_hook_checkpoints_only_bot_files(bots):
    checkpoints.hook({"tool_name": "Edit", "tool_input": {"file_path": "/elsewhere/x.py"}})
    assert checkpoints.list_all()["checkpoints"] == []
    checkpoints.hook({"tool_name": "Edit", "tool_input": {"file_path": str(bots / "nr7_swing.py")}})
    assert "auto, before Edit" in checkpoints.list_all()["checkpoints"][0]["note"]


def test_bots_private_are_loaded_and_checkpointed(tmp_path, monkeypatch):
    d, priv = tmp_path / "bots", tmp_path / "bots_private"
    shutil.copytree(loader.bots_dir(), d, ignore=shutil.ignore_patterns("__pycache__"))
    priv.mkdir()
    mine = (d / "nr7_swing.py").read_text().replace('"NR7 swing"', '"My own swing"')
    (priv / "my_own_swing.py").write_text(mine)
    monkeypatch.setattr(loader, "bots_dir", lambda: d)
    monkeypatch.setattr(loader, "PRIVATE", priv)
    bots, errors = loader.load_all()
    assert not errors and {"my_own_swing", "nr7_swing"} <= set(bots)
    assert bots["my_own_swing"].source_file == str(priv / "my_own_swing.py")
    cp = checkpoints.save("with my own bot")
    assert "bots_private/my_own_swing.py" in cp["files"]
    (priv / "my_own_swing.py").write_text(mine.replace('"r_multiple": 2.0', '"r_multiple": 3.0'))
    assert checkpoints.list_all()["checkpoints"][0]["changed_since"] == ["bots_private/my_own_swing.py"]
    assert checkpoints.restore(cp["id"], confirm=True)["files"] == ["bots_private/my_own_swing.py"]
    assert (priv / "my_own_swing.py").read_text() == mine
    monkeypatch.setenv("BOTSCOPE_BOTS_DIR", str(d))                  # your own bots folder: no second folder
    assert "my_own_swing" not in loader.load_all()[0]
