"""Demo mode: real past crypto prices when online (keyless), made-up stocks; every label says which. The tutorial's
showcase day is labeled as picked and exists only in demo mode."""
from datetime import date, datetime

from botscope import data, demo, view
from botscope.bot import BarData


def _demo(monkeypatch, crypto="real"):
    monkeypatch.setenv("BOTSCOPE_DEMO", "1")
    monkeypatch.setenv("BOTSCOPE_DEMO_CRYPTO", crypto)
    data._DEMO_REAL.clear()


def test_demo_crypto_uses_real_prices_when_online(monkeypatch):
    _demo(monkeypatch)
    real = [BarData(datetime(2026, 10, 1, tzinfo=data.ET), 1, 2, 0.5, 1.5, 10)]
    monkeypatch.setattr(data, "_real_bars", lambda *a: real)
    assert data.bars("BTC/USD", date(2026, 10, 1), date(2026, 10, 1), "1Day") == real
    lbl = data.source_label("BTC/USD", daily=True)
    assert "real past prices" in lbl and "DEMO" not in lbl
    assert "real past prices" in demo.label({"source": lbl})["source"]          # not rewritten to "made-up"


def test_demo_stocks_stay_made_up_and_say_so(monkeypatch):
    _demo(monkeypatch)
    monkeypatch.setattr(data, "_real_bars", lambda *a: (_ for _ in ()).throw(AssertionError("no real stock fetch in demo")))
    assert data.bars("SPY", date(2026, 10, 1), date(2026, 10, 2), "1Day")
    assert data.source_label("SPY") == demo.SOURCE


def test_demo_crypto_offline_falls_back_to_made_up_and_says_so(monkeypatch):
    _demo(monkeypatch)
    def offline(*a):
        raise ConnectionError("offline")
    monkeypatch.setattr(data, "_real_bars", offline)
    assert data.bars("BTC/USD", date(2026, 10, 1), date(2026, 10, 3), "1Day")      # made-up bars instead
    assert data.source_label("BTC/USD") == demo.SOURCE


def test_showcase_day_is_labeled_and_demo_only(monkeypatch):
    _demo(monkeypatch, crypto="made-up")
    st = view.build("first_hour_breakout", None, "showcase")
    assert st["note"] == view.SHOWCASE_NOTE and len(st["trades"]) == 1               # one whole trade, labeled as picked
    monkeypatch.setenv("BOTSCOPE_DEMO", "0")
    assert view.showcase_day(view.loader.get("first_hour_breakout"), "AAPL") is None   # real data: never a picked day
