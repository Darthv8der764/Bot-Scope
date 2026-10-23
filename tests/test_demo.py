"""Demo mode: zero keys, made-up prices, a DEMO DATA badge everywhere, and doctor says how to switch."""
import re
from datetime import date

import pytest

from botscope import data, demo, desk, doctor, env


@pytest.fixture
def no_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_ENV_FILE", str(tmp_path / "none.env"))
    for k in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "BOTSCOPE_DEMO"):
        monkeypatch.delenv(k, raising=False)


def test_demo_is_on_without_keys_and_can_be_forced(no_keys, monkeypatch):
    assert env.demo_mode()
    monkeypatch.setenv("BOTSCOPE_DEMO", "0")
    assert not env.demo_mode()
    monkeypatch.setenv("ALPACA_API_KEY", "PKx"); monkeypatch.setenv("ALPACA_SECRET_KEY", "y")
    monkeypatch.setenv("BOTSCOPE_DEMO", "")
    assert not env.demo_mode()
    monkeypatch.setenv("BOTSCOPE_DEMO", "1")
    assert env.demo_mode()


def test_demo_bars_are_repeatable_and_clean():
    a = demo.bars("SPY", date(2024, 1, 1), date(2024, 3, 1), "1Day")
    b = demo.bars("SPY", date(2024, 2, 1), date(2024, 3, 1), "1Day")
    assert a[-1] == b[-1] and len(a) > len(b) > 15            # same day = same bar, whatever window was asked for
    assert data.clean(a)[1] == []
    m = demo.bars("AAPL", date(2024, 3, 4), date(2024, 3, 4), "5Min")
    assert len(m) == 78 and m[0].t.hour == 9 and m[0].t.minute == 30 and data.clean(m)[1] == []
    assert demo.bars("SPY", date(2024, 3, 9), date(2024, 3, 10), "5Min") == []      # weekend


def test_data_layer_uses_demo_bars_without_keys(no_keys):
    bs, src = data.day_bars("SPY", date(2024, 3, 4), "5Min")
    assert len(bs) == 78 and src.startswith("DEMO DATA")
    assert data.bars("QQQ", date(2024, 3, 1), date(2024, 3, 8), "1Day")


def test_label_badges_results_and_turns_key_errors_into_a_how_to(no_keys):
    out = demo.label({"data": "Alpaca SIP (all US exchanges), your own keys", "x": 1})
    assert out["data_badge"] == "DEMO DATA" and out["data"].startswith("DEMO DATA") and out["x"] == 1
    err = demo.label({"error": "Alpaca paper keys missing: put ALPACA_API_KEY ..."})
    assert "needs real data" in err["demo"] and ".botscope/.env" in err["demo"]


def test_desk_board_works_and_key_only_panels_explain(no_keys):
    board = desk.panel("board")
    assert board["data_badge"] == "DEMO DATA" and board["indexes"] and board["source"].startswith("DEMO DATA")
    assert "needs real data" in desk.panel("news")["demo"]


def test_doctor_is_ready_in_demo_and_says_how_to_switch(no_keys):
    d = doctor.check(via_mcp=True)
    row = next(r for r in d["checks"] if r["check"] == "Data")
    assert "DEMO DATA" in row["detail"] and "ALPACA_API_KEY" in row["detail"]
    assert d["demo"] and "DEMO" in d["summary"]


def test_every_tool_result_gets_the_badge(no_keys):
    from botscope import server
    out = server.list_bots()
    assert out["data_badge"] == "DEMO DATA"
    for res in (server.morning_brief(), server.weekly_checkup()):       # no line may say the made-up prices are Alpaca's
        assert res["data_badge"] == "DEMO DATA" and "Alpaca SIP" not in str(res)
    assert "DEMO DATA (made-up prices)" in str(server.morning_brief()["sources"])
    for real in ("Alpaca SIP (all US exchanges), downloaded with your own keys", "SPY daily closes from Alpaca SIP (your own keys)",
                 "Alpaca SIP bars (all US exchanges), your own keys", "Alpaca SIP daily closes, last 60 days, your own keys"):
        assert "keys" not in demo._no_sip(real) and "DEMO DATA" in demo._no_sip(real)
    from botscope import report
    assert report.data_line(["SPY", "BTC/USD"]) == demo.SOURCE


def test_demo_results_go_to_their_own_journal(no_keys, monkeypatch):
    from botscope import journal, strategy_factory
    monkeypatch.delenv("BOTSCOPE_JOURNAL_DIR", raising=False)
    monkeypatch.delenv("BOTSCOPE_FACTORY_DIR", raising=False)
    assert journal.folder().parts[-2:] == ("demo", "journal")
    assert strategy_factory.factory_dir().parts[-2:] == ("demo", "factory")
    monkeypatch.setenv("BOTSCOPE_DEMO", "0")
    assert journal.folder().parts[-2:] == ("data", "journal")


def test_botscope_demo_runs_the_whole_tour(monkeypatch, tmp_path, capsys):
    from botscope import cli
    monkeypatch.setenv("BOTSCOPE_FACTORY_DIR", str(tmp_path / "f"))
    monkeypatch.setenv("BOTSCOPE_DEMO", "1")              # the tour sets it too; this way it's undone after the test
    monkeypatch.setattr("botscope.strategy_factory.MAX_CANDIDATES", 1)
    assert cli.main(["demo"], wait=False) == 0
    out = capsys.readouterr().out
    assert "DEMO DATA" in out and "ready in DEMO mode" in out and "Strategy factory" in out
    assert "/studio#factory" in out and "ALPACA_API_KEY" in out and "Demo paper days" in out
    assert "Next: " in out and "Paper trade a survivor" in out           # a new user is told what to do next
    assert "The number after each name is the run: factory run " in out          # the 10 digits are explained


def test_demo_paper_days_fill_once_without_alerts(no_keys, monkeypatch, tmp_path):
    from botscope import alerts, journal
    monkeypatch.setenv("BOTSCOPE_BOTS_DIR", str(tmp_path / "bots"))
    (tmp_path / "bots").mkdir()
    import shutil
    from pathlib import Path
    shutil.copy(Path(demo.__file__).resolve().parent.parent / "bots" / "pullback_swing.py", tmp_path / "bots")
    sent = []
    monkeypatch.setattr(alerts, "send", lambda *a, **k: sent.append(a))
    out = demo.fill_paper_days(10)
    assert out["days"] == 10 and out["paper_results"] == len(journal.load("paper_results")) and not sent
    assert "skipped" in demo.fill_paper_days(10)
    monkeypatch.setenv("BOTSCOPE_DEMO", "0")
    with pytest.raises(RuntimeError):
        demo.fill_paper_days()


def test_doctor_points_at_leftover_demo_results_in_real_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(env, "ROOT", tmp_path)
    (tmp_path / "data" / "demo" / "journal").mkdir(parents=True)
    (tmp_path / "data" / "demo" / "journal" / "reports.json").write_text("[]")
    row = next(r for r in doctor.check(via_mcp=True)["checks"] if r["check"].startswith("Demo results"))
    assert "1 file in" in row["detail"] and "delete the folder" in row["detail"]
