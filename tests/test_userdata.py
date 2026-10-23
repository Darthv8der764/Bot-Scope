"""Plugin install: your bots and journal live in ~/.botscope, so a plugin update (which replaces the plugin folder)
can't take them. A developer checkout keeps its own bots/ and data/."""
import json
import os

import pytest

from botscope import doctor, env, journal, loader, userdata


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    """A made-up installed plugin: ~/.claude/plugins/cache/botscope/botscope/<version>/ with an example bot, and an
    older version next to it holding the user's own files."""
    fake_home = tmp_path / "user"
    monkeypatch.setattr(userdata.Path, "home", classmethod(lambda cls: fake_home))
    versions = fake_home / ".claude" / "plugins" / "cache" / "botscope" / "botscope"
    new, old = versions / "0.2.0", versions / "0.1.0"
    for v in (new, old):
        (v / "botscope").mkdir(parents=True)
        (v / "bots").mkdir()
    (new / "bots" / "example.py").write_text("# example v2\n")
    (old / "bots" / "example.py").write_text("# example, edited by me\n")
    (old / "bots" / "mine.py").write_text("# my own bot\n")
    (old / "data" / "journal").mkdir(parents=True)
    (old / "data" / "journal" / "vetoes.json").write_text("[1]")
    (old / "data" / "demo" / "journal").mkdir(parents=True)
    (old / "data" / "demo" / "journal" / "reports.json").write_text("[2]")
    (old / "data" / "league").mkdir()
    (old / "data" / "league" / "x.json").write_text("{}")
    (old / "data" / "cache").mkdir()
    (old / "data" / "cache" / "SPY.parquet").write_text("prices")
    (old / "botscope.local.json").write_text('{"paths": []}')
    (old / ".env").write_text("ALPACA_API_KEY=PKnope")
    os.utime(new, (2_000_000_000, 2_000_000_000))
    monkeypatch.setattr(env, "ROOT", new)
    home = tmp_path / "bshome"
    monkeypatch.setenv("BOTSCOPE_HOME", str(home))
    monkeypatch.delenv("BOTSCOPE_PLUGIN_MODE")
    monkeypatch.delenv("BOTSCOPE_JOURNAL_DIR")
    return new, old, home


def test_plugin_mode_paths(plugin, monkeypatch):
    new, old, home = plugin
    assert userdata.plugin_install()
    monkeypatch.setattr(loader, "ROOT", new)
    monkeypatch.setattr(journal, "ROOT", new)
    assert loader.bots_dir() == home / "bots"
    assert journal.folder() == home / "journal"
    monkeypatch.setenv("BOTSCOPE_DEMO", "1")
    assert journal.folder() == home / "demo" / "journal"


def test_claude_plugin_root_outside_plugins_folder(tmp_path, monkeypatch):
    """Started by Claude Code as a plugin (CLAUDE_PLUGIN_ROOT) from a folder that isn't a git checkout: plugin mode.
    The same folder as a git checkout (a developer using --plugin-dir) keeps its own paths."""
    monkeypatch.delenv("BOTSCOPE_PLUGIN_MODE")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    assert userdata.plugin_install(tmp_path)
    (tmp_path / ".git").mkdir()
    assert not userdata.plugin_install(tmp_path)


def test_one_time_copy_from_old_version(plugin, monkeypatch):
    new, old, home = plugin
    monkeypatch.setattr(loader, "ROOT", new)
    loader.bots_dir()
    assert (home / "bots" / "mine.py").read_text() == "# my own bot\n"
    assert (home / "bots" / "example.py").read_text() == "# example, edited by me\n"   # the user's edit, not v2
    assert (home / "journal" / "vetoes.json").read_text() == "[1]"
    assert (home / "demo" / "journal" / "reports.json").read_text() == "[2]"
    assert (home / "league" / "x.json").exists() and (home / "botscope.local.json").exists()
    assert not (home / "cache").exists() and not (home / ".env").exists()      # prices refetch; keys never copied
    assert (old / "bots" / "mine.py").exists() and (old / "data" / "journal" / "vetoes.json").exists()  # never deleted
    m = json.loads((home / userdata.MARKER).read_text())
    assert m["files"] == 6 and m["from"] == [str(old)]
    row = next(r for r in doctor.check()["checks"] if r["check"] == "Your files")
    assert str(home) in row["detail"] and "Copied 6 files from the old plugin folder" in row["detail"]


def test_copy_never_overwrites_and_runs_once(plugin, monkeypatch):
    new, old, home = plugin
    (home / "journal").mkdir(parents=True)
    (home / "journal" / "vetoes.json").write_text("[newer]")
    (home / "bots").mkdir()
    (home / "bots" / "mine.py").write_text("# edited since\n")
    userdata.ensure()
    assert (home / "journal" / "vetoes.json").read_text() == "[newer]"
    assert (home / "bots" / "mine.py").read_text() == "# edited since\n"
    assert not (home / "bots" / "example.py").exists() or \
        (home / "bots" / "example.py").read_text() == "# example, edited by me\n"
    (old / "data" / "journal" / "later.json").write_text("[]")
    monkeypatch.setattr(userdata, "_done", False)
    userdata.ensure()                                         # second run: the copy already happened once
    assert not (home / "journal" / "later.json").exists()


def test_examples_seeded_once_never_overwritten(plugin, monkeypatch):
    new, old, home = plugin
    for p in sorted(old.rglob("*"), reverse=True):                # a fresh install: no older version next to it
        p.unlink() if p.is_file() else p.rmdir()
    old.rmdir()
    userdata.ensure()
    assert (home / "bots" / "example.py").read_text() == "# example v2\n"
    assert json.loads((home / userdata.MARKER).read_text())["files"] == 0
    (home / "bots" / "example.py").write_text("# my edit\n")
    (new / "bots" / "example.py").write_text("# example v3\n")
    (new / "bots" / "another.py").write_text("# new example\n")
    monkeypatch.setattr(userdata, "_done", False)
    userdata.ensure()                                         # after an update
    assert (home / "bots" / "example.py").read_text() == "# my edit\n"
    assert not (home / "bots" / "another.py").exists()       # a bots folder you already have is never touched


def test_overrides_win(plugin, tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_BOTS_DIR", str(tmp_path / "mybots"))
    monkeypatch.setenv("BOTSCOPE_JOURNAL_DIR", str(tmp_path / "myjournal"))
    assert loader.bots_dir() == tmp_path / "mybots"
    assert journal.folder() == tmp_path / "myjournal"
    _, _, home = plugin
    assert not (home / "bots" / "example.py").exists()       # no examples seeded into a folder you aren't using


def test_dev_checkout_unchanged(monkeypatch):
    monkeypatch.delenv("BOTSCOPE_PLUGIN_MODE")
    monkeypatch.delenv("BOTSCOPE_JOURNAL_DIR")
    monkeypatch.setenv("BOTSCOPE_HOME", "/nonexistent-botscope-home")
    assert not userdata.plugin_install()
    assert loader.bots_dir() == env.ROOT / "bots"
    assert journal.folder() == env.ROOT / "data" / "journal"
    assert not os.path.exists("/nonexistent-botscope-home")
    row = next(r for r in doctor.check()["checks"] if r["check"] == "Your files")
    assert "developer checkout" in row["detail"]
