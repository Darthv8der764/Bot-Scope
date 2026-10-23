from datetime import date, datetime

from botscope import journal, phantom
from botscope.data import ET


def _run(tmp_path):
    f = tmp_path / "dip.py"
    f.write_text("x = 1\n")
    journal.add("factory_runs", {"run": "r1", "kept": [{"id": "dip_buy", "name": "Dip buy", "file": str(f), "avg_r": 0.2,
                                                       "untested_trades": 120}], "dropped": []})


class _Cls:
    asset, symbols, timeframe = "stock", ["SPY"], "1Day"


def test_start_update_report(tmp_path, monkeypatch):
    _run(tmp_path)
    monkeypatch.setattr("botscope.strategy_factory.load_file", lambda p: _Cls)
    out = phantom.start("r1", ["dip buy", "nope"], today=date(2026, 10, 12))
    assert out["started"] == [{"name": "Dip buy", "from": "2026-10-12"}] and "nope: not in run r1" in out["problems"]
    assert "already" in phantom.start("r1", ["dip_buy"])["problems"][0]
    seen = []

    def replay(cls, d, since):
        assert since == date(2026, 10, 12)
        seen.append(d)
        return [{"symbol": "SPY", "side": "long", "t_in": f"{d}T10:00", "t_out": f"{d}T15:00", "r": 1.0, "why_out": "target"}]
    now = datetime(2026, 10, 17, 12, 0, tzinfo=ET)                   # Saturday
    up = phantom.update(now=now, replay=replay)
    assert seen == [date(2026, 10, d) for d in (12, 13, 14, 15, 16)]  # weekdays from the start, never before it
    assert up["updated"][0]["new_signals"] == 5
    phantom.update(now=now, replay=replay)                          # nothing new: days already checked
    assert len(seen) == 5 and len(journal.load("phantom_results")) == 5
    r = phantom.report()["phantoms"][0]
    assert r["signals"] == 5 and r["total_r"] == 5 and r["backtest_avg_r"] == 0.2 and r["verdict"].startswith("too early")
    assert phantom.stop("Dip buy")["stopped"] == ["Dip buy"]
    assert phantom.update(now=now, replay=replay)["updated"] == []


def test_verdicts():
    assert "losing live" in phantom.verdict([-0.1] * 12, 0.2)
    assert "weaker" in phantom.verdict([0.05] * 12, 0.2)
    assert "holding up" in phantom.verdict([0.3] * 12, 0.2)


def test_no_orders_in_phantom():
    src = open(phantom.__file__).read()
    assert "TradingClient" not in src and "submit_order" not in src
