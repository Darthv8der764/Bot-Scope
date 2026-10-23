"""Offline checks of the devil's advocate security tester: probes find holes, fixes work, undo works."""
import pytest

from botscope import guard, redteam, settings


@pytest.fixture(autouse=True)
def no_env(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.delenv("BOTSCOPE_LIVE_TRADING", raising=False)


def test_this_repo_has_no_holes():
    out = redteam.run(fix=False)
    holes = [f for f in out["findings"] if f["result"] == "HOLE"]
    assert not holes, holes
    assert out["headline"].startswith("All clear")


def test_open_key_file_is_fixed_and_undone(tmp_path, monkeypatch):
    env = tmp_path / "keys.env"
    env.write_text("ALPACA_API_KEY=PK" + "X" * 18 + "\n")   # built at runtime so the leak probe stays clean
    env.chmod(0o644)
    monkeypatch.setenv("BOTSCOPE_ENV_FILE", str(env))
    f = redteam.probe_env_permissions(fix=True)[0]
    assert f["result"] == "HOLE" and oct(env.stat().st_mode & 0o777) == "0o600"
    redteam.undo_fix(f["undo_id"])
    assert oct(env.stat().st_mode & 0o777) == "0o644"


def test_broken_guard_is_caught_and_stop_turns_on(monkeypatch):
    monkeypatch.setattr(guard, "check_order", lambda *a, **k: {"decision": "allow", "mode": "live", "reason": "x"})
    out = redteam.run(fix=True)
    assert out["headline"].startswith("I could've taken out the whole system")
    f = next(x for x in out["findings"] if x["probe"] == "live-trading lock")
    assert f["result"] == "HOLE" and settings.load()["stopped"]
    redteam.undo_fix(f["undo_id"])
    assert not settings.load()["stopped"]


def test_dangerous_bot_is_flagged(tmp_path, monkeypatch):
    (tmp_path / "sneaky.py").write_text("import subprocess\nopen('/tmp/x', 'w')\n")
    monkeypatch.setenv("BOTSCOPE_BOTS_DIR", str(tmp_path))
    f = redteam.probe_bot_code(fix=False)[0]
    assert f["result"] == "warning" and "runs other programs" in f["what"] and "writes files" in f["what"]


def test_bad_data_is_dropped_not_crashing():
    assert redteam.probe_bad_data(fix=False)[0]["result"] == "safe"
