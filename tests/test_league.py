"""Friends league: league cards carry no keys/dollars/paths; friends' files are checked, never run; honest score."""
import json

import pytest

from botscope import journal, league


def _card(**k):
    c = {"league_card": 1, "bot": "B", "owner": "sam", "timeframe": "1Day", "untested_trades": 100, "avg_r": 0.1,
         "total_r": 10.0, "range_low_r": 2.0, "costs_r": 3.0, "losing_years": 2, "untested_years": 9,
         "luck": "beats luck", "confidence": "medium", "report_day": "2026-10-17", "data": "real market data"}
    return c | k


def test_needs_a_saved_report_then_exports_a_clean_card(monkeypatch):
    with pytest.raises(ValueError):
        league.card("nr7_swing")
    journal.upsert("reports", {"bot": "nr7_swing"}, {"untested": {"trades": 40, "avg_r": 0.2, "total_r": 8.0,
                   "net_usd": 2400.0, "total_r_range_5_50_95": [1.0, 8, 15]}, "years": {"untested": [2020, 2021]},
                   "losing_untested_years": [2021]})
    out = league.export("nr7_swing", owner="Ana <script>")
    text = open(out["file"]).read()
    assert "usd" not in text and "/" not in json.loads(text)["owner"] and "<" not in text
    assert league.read(league.folder() / out["file"].rsplit("/", 1)[1])["untested_trades"] == 40


def test_league_ranks_by_honest_score_not_profit():
    f = league.folder()
    (f / "lucky.league.json").write_text(json.dumps(_card(bot="Lucky", total_r=80.0, range_low_r=-5.0)))
    (f / "steady.league.json").write_text(json.dumps(_card(bot="Steady", total_r=12.0, range_low_r=4.0)))
    (f / "tiny.league.json").write_text(json.dumps(_card(bot="Tiny", untested_trades=8, range_low_r=6.0)))
    (f / "fluke.league.json").write_text(json.dumps(_card(bot="Fluke", range_low_r=5.0, luck="looks like luck")))
    (f / "bad.league.json").write_text(json.dumps(_card(untested_trades="lots")))
    (f / "evil.league.json").write_text("__import__('os').system('echo hi')")
    t = league.league()
    assert [r["bot"] for r in t["table"]] == ["Steady", "Tiny", "Fluke", "Lucky"]
    assert sorted(t["skipped_files"]) == ["bad.league.json", "evil.league.json"]
    (f / "demo.league.json").write_text(json.dumps(_card(bot="Demo", range_low_r=50.0, data="DEMO (made-up prices)")))
    assert next(r for r in league.league()["table"] if r["bot"] == "Demo")["honest_score"] == 0.0
    assert "win" not in json.dumps(t).lower()
