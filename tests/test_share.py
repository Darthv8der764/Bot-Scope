"""Share as a page: a standalone HTML file with the honest report, and nothing private in it."""
import shutil
from pathlib import Path

import pytest

from botscope import demo, env, loader, report, share


@pytest.fixture
def bot(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_BOTS_DIR", str(tmp_path / "bots"))
    (tmp_path / "bots").mkdir()
    shutil.copy(Path(share.__file__).resolve().parent.parent / "bots" / "pullback_swing.py", tmp_path / "bots")
    monkeypatch.setattr(env, "ROOT", tmp_path)
    monkeypatch.setattr(share, "ROOT", tmp_path)
    return "pullback_swing"


def test_needs_a_saved_report_first(bot):
    with pytest.raises(ValueError, match="run honest_report first"):
        share.export(bot)


def test_page_has_the_report_and_nothing_private(bot, monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "PKSECRETKEY123")
    report.full_report(loader.get(bot), ["SPY"], fetch=demo.bars, crashes=False)
    out = share.export(bot)
    text = Path(out["file"]).read_text()
    assert text.startswith("<!doctype html>") and "Pullback swing" in text and "UNTESTED" in text
    assert "Not financial advice" in text and "<script" not in text and "http" not in text
    assert "PKSECRETKEY123" not in text and str(Path.home()) not in text
    assert Path(out["file"]).parent.name == "shares"
