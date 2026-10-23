"""Data adapters: one interface, Alpaca by default, a keyless read-only Coinbase crypto adapter as proof."""
from datetime import date, datetime, timezone

import pytest

from botscope import brokers, data


def fake_get(calls):
    def get(url):
        calls.append(url)
        day = int(datetime(2024, 3, 4, tzinfo=timezone.utc).timestamp())
        # Coinbase rows: [time, low, high, open, close, volume], newest first
        return [[day + 86400, 99.0, 112.0, 105.0, 110.0, 5.0], [day, 95.0, 106.0, 100.0, 105.0, 4.0]]
    return get


def test_coinbase_maps_candles_and_pages_requests():
    calls = []
    a = brokers.CoinbasePublic(get=fake_get(calls))
    bs = a.bars("BTC/USD", date(2024, 3, 4), date(2024, 3, 5), "1Day")
    assert [(b.o, b.h, b.l, b.c) for b in bs] == [(100.0, 106.0, 95.0, 105.0), (105.0, 112.0, 99.0, 110.0)]
    assert "BTC-USD/candles" in calls[0] and "granularity=86400" in calls[0]
    assert data.clean(bs)[1] == []
    with pytest.raises(ValueError):
        a.bars("BTC/USD", date(2024, 3, 4), date(2024, 3, 5), "2Day")


def test_sources_list_and_switch(monkeypatch):
    s = brokers.sources()
    assert [a["name"] for a in s["adapters"]] == ["alpaca", "coinbase"] and s["crypto_uses"] == "alpaca"
    assert all(a["read_only"] for a in s["adapters"]) and not s["adapters"][1]["needs_keys"]
    monkeypatch.setenv("BOTSCOPE_CRYPTO_DATA", "coinbase")
    assert brokers.crypto_source() == "coinbase"
    with pytest.raises(ValueError):
        brokers.get("robinhood")


def test_crypto_fetch_goes_through_the_chosen_adapter(monkeypatch):
    monkeypatch.setenv("BOTSCOPE_CRYPTO_DATA", "coinbase")
    calls = []
    monkeypatch.setattr(brokers.CoinbasePublic, "_http", staticmethod(fake_get(calls)))
    rows = data._fetch("BTC/USD", date(2024, 3, 4), date(2024, 3, 5), "1Day", "sip")
    assert len(rows) == 2 and calls
