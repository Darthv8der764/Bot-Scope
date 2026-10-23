"""Trade clip: honest label on every clip, long trades merged short, only WebM saved, locally."""
import pytest

from botscope import clip, view


def _state(n=300):
    cs = [{"time": 1000 + 60 * i, "open": 10, "high": 11, "low": 9, "close": 10.5} for i in range(n)]
    t = {"id": "T1", "open": False, "side": "long", "t_in": 1000 + 60 * 40, "t_out": 1000 + 60 * 250, "entry": 10.5,
         "exit": 11, "stop": 9.5, "target": 11, "why_out": "target hit", "r": 0.48}
    return {"bot": {"id": "first_hour_breakout", "name": "First hour breakout"}, "symbol": "AAPL", "day": "2026-10-15",
            "account": "PAPER", "candles": cs, "trades": [t]}


def test_label_says_paper_period_result_and_one_trade_says_little(monkeypatch):
    monkeypatch.setattr(view, "build", lambda *a: _state())
    c = clip.clip_data("first_hour_breakout")
    text = " ".join(c["label"])
    assert "PAPER" in text and "UNTESTED day" in text and "+0.48R after costs" in text and "confidence" in text
    assert "One trade says little" in text and len(c["candles"]) <= clip.MAX_CANDLES and c["merged"] > 1


def test_no_finished_trade_says_so(monkeypatch):
    st = _state(); st["trades"] = []
    monkeypatch.setattr(view, "build", lambda *a: st)
    with pytest.raises(ValueError):
        clip.clip_data("first_hour_breakout")


def test_only_webm_is_saved_locally():
    with pytest.raises(ValueError):
        clip.save("x", b"<html>not a video")
    out = clip.save("../../etc/x", b"\x1a\x45\xdf\xa3" + b"0" * 10)
    assert out["saved"].startswith(str(clip.folder())) and ".." not in out["saved"].rsplit("/", 1)[1]
