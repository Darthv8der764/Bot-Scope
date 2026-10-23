"""Offline checks of stock lookup + key dates."""
from datetime import date, timedelta

from botscope import keydates

T = date(2026, 10, 16)


def _closes(n=60, jump_at=40, jump=0.08):
    out, px = [], 100.0
    for i in range(n):
        px *= 1 + (jump if i == jump_at else (0.005 if i % 2 else -0.004))
        out.append((str(T - timedelta(days=n - i)), round(px, 4)))
    return out


def test_big_move_is_measured_against_a_typical_day():
    rows = keydates.big_move_days(_closes())
    assert len(rows) == 1 and rows[0]["event"].startswith("up 8.0%") and "typical day" in rows[0]["event"]
    assert keydates.big_move_days(_closes(10)) == []                    # too little history to say


def test_past_and_coming_split_and_a_missing_source_is_named():
    ern = lambda s, a, b: [{"date": "2026-10-29", "kind": "earnings", "event": "earnings, after close", "source": "Finnhub"},
                           {"date": "2026-07-30", "kind": "earnings", "event": "earnings, after close", "source": "Finnhub"}]
    def broken(s, a, b):
        raise RuntimeError("no keys")
    k = keydates.key_dates("aapl", T, earnings=ern, corporate=broken, closes=lambda s, a, b: _closes())
    assert k["symbol"] == "AAPL" and [r["date"] for r in k["coming"]] == ["2026-10-29"]
    assert {r["kind"] for r in k["past"]} == {"earnings", "big move"} and k["past"][0]["date"] >= k["past"][-1]["date"]
    assert len(k["problems"]) == 1 and "splits + dividends" in k["problems"][0]
    k = keydates.key_dates("AAPL", T, earnings=lambda *a: [], corporate=lambda *a: [], closes=lambda *a: _closes())
    assert "past earnings: none returned" in k["problems"][0]


def test_bad_ticker():
    import pytest
    with pytest.raises(ValueError):
        keydates.key_dates("$$$", T, earnings=lambda *a: [], corporate=lambda *a: [], closes=lambda *a: [])
