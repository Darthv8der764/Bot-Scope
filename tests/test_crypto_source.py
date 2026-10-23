from datetime import date

from botscope import data, view


def test_crypto_is_never_labelled_sip(monkeypatch):
    monkeypatch.setattr(data, "demo_mode", lambda: False)
    monkeypatch.setattr(data, "bars", lambda *a, **k: [])
    _, src = data.view_bars("BTC/USD", date(2026, 10, 16), "1Day")
    assert "SIP" not in src.replace("not SIP", "") and "crypto" in src
    _, src = data.day_bars("BTC/USD", date(2026, 10, 16), "15Min")
    assert "SIP" not in src and "crypto" in src
    _, src = data.view_bars("SPY", date(2026, 10, 16), "1Day")
    assert "SIP" in src


def test_crypto_label_names_the_adapter(monkeypatch):
    from botscope import brokers
    monkeypatch.setattr(brokers, "crypto_source", lambda: "coinbase")
    assert data.crypto_label(daily=True).startswith("Coinbase crypto daily bars")


def test_symbol_boxes_fit_btc_usd_and_hidden_charts_refit():
    page = view.PAGE.read_text()
    assert "#f-symbol { width: 10ch; }" in page
    assert "ResizeObserver" in page and "fitContent" in page
    assert "#sym { width: 10ch" in view.PAGE.with_name("flight.html").read_text()
