"""Strategy factory: goal reading, candidate files in the normal bot format, the honest pipeline, and adopting one."""
import pytest

from botscope import demo, journal, loader, scaffold, strategy_factory as sf


@pytest.fixture(autouse=True)
def _folders(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_FACTORY_DIR", str(tmp_path / "factory"))
    monkeypatch.setenv("BOTSCOPE_BOTS_DIR", str(tmp_path / "bots"))
    (tmp_path / "bots").mkdir()


def test_understand_reads_the_goal():
    s = sf.understand("a calm daily ETF bot")
    assert (s["timeframe"], s["sides"], s["symbols"], s["calm"]) == ("1Day", "long", sf.ETFS, True)
    s = sf.understand("intraday opening range bot, long and short, on SPY and QQQ")
    assert s["timeframe"] == "5Min" and s["sides"] == "both" and s["symbols"] == ["SPY", "QQQ"]
    assert sf.understand("short-only swing bot")["sides"] == "short"


def test_pick_caps_at_five_and_fits_the_goal():
    assert len(sf.pick(sf.understand("any daily bot"), max_candidates=99)) <= sf.MAX_CANDIDATES
    calm = sf.pick(sf.understand("a calm daily ETF bot"))
    assert calm and all(sf.TEMPLATES[k]["calm"] for k in calm)
    assert sf.pick(sf.understand("short-only daily breakout")) == ["breakout", "spike_fade"]


@pytest.mark.parametrize("key", list(sf.TEMPLATES))
def test_every_template_makes_a_bot_that_passes_check_bot(key, tmp_path):
    t = sf.TEMPLATES[key]
    spec = sf.understand("a daily bot" if t["timeframe"] == "1Day" else "an intraday bot")
    spec["sides"] = t["sides"][0]
    slug, src = sf.source(key, spec, "01011200")
    path = tmp_path / f"{slug}.py"
    path.write_text(src)
    res = scaffold.check_class(sf.load_file(path))
    assert res["ok"], [c for c in res["checks"] if not c["pass"]]


def test_run_on_demo_data_keeps_survivors_and_explains_every_drop():
    out = sf.run("a calm daily ETF bot", max_candidates=3, fetch=demo.bars, demo=True)
    assert out["tried"] == len(out["kept"]) + len(out["dropped"]) <= 3
    assert all(d["reason"] for d in out["dropped"])
    for k in out["kept"]:
        assert k["confidence"] in ("very low", "low", "medium", "high", "very high")
        assert k["untested_trades"] >= 30 and k["if_costs_doubled_r"] > 0 and k["luck"] != "looks like luck"
    assert "DEMO DATA" in out["markdown"] and "UNTESTED" in out["markdown"]
    assert "tried" in out["tries_note"]
    assert journal.load("factory_runs")[-1]["run"] == out["run"]
    assert not journal.load("reports") and not journal.load("luck")       # candidates never touch the real journal


def test_a_failing_candidate_is_dropped_with_a_reason(monkeypatch):
    monkeypatch.setattr(sf, "judge", lambda cls, spec, fetch=None: {"kept": False, "reason": "lost money"})
    out = sf.run("a calm daily ETF bot", max_candidates=1, fetch=demo.bars, demo=True)
    assert out["kept"] == [] and out["dropped"][0]["reason"] == "lost money"
    assert "No candidate survived" in out["markdown"]


def test_adopt_copies_into_the_bots_folder_after_a_checkpoint(monkeypatch):
    monkeypatch.setattr(sf, "judge", lambda cls, spec, fetch=None: {"kept": False, "reason": "x"})
    saved = []
    monkeypatch.setattr(sf.checkpoints, "save", lambda label: saved.append(label) or {"id": "cp1"})
    out = sf.run("a calm daily ETF bot", max_candidates=1, fetch=demo.bars, demo=True)
    res = sf.adopt(out["run"], out["dropped"][0]["id"])
    assert res["checkpoint_before"] == "cp1" and saved
    assert res["bot_id"] in loader.load_all()[0]
    with pytest.raises(ValueError):
        sf.adopt(out["run"], out["dropped"][0]["id"])                      # never overwrites


def test_later_half_check_drops_an_edge_that_faded():
    rows = [{"year": y, "period": "untested", "trades": 10, "total_r": 5.0 if y < 2020 else -1.0} for y in range(2016, 2024)]
    row = {}
    assert "only in the earlier years" in sf.later_half_check({"by_year": rows}, row)
    assert row["halves_r"]["split_year"] == 2020
    rows = [r | {"total_r": 1.0} for r in rows]
    assert sf.later_half_check({"by_year": rows}, {}) is None


def test_nudged_moves_every_setting_and_the_lookback(tmp_path):
    slug, src = sf.source("dip_buy", sf.understand("a calm daily ETF bot"), "01011200")
    (tmp_path / f"{slug}.py").write_text(src)
    cls = sf.load_file(tmp_path / f"{slug}.py")
    big = sf.nudged(cls, 1.2)
    assert big.params["trend_days"] == 240 and big.params["stop_ranges"] == 3.6 and big.lookback_days >= 240
    assert sf.nudged(cls, 0.8).params["rsi_days"] == 2 and cls.params["trend_days"] == 200      # original untouched


def test_knife_edge_settings_are_dropped(monkeypatch, tmp_path):
    calls = []

    def fake_report(c, *a, **k):
        calls.append(c.params["trend_days"])
        return {"untested": {"trades": 50, "avg_r": -0.1 if c.params["trend_days"] == 160 else 0.2, "total_r": 1}}
    monkeypatch.setattr(sf.report, "full_report", fake_report)
    slug, src = sf.source("dip_buy", sf.understand("a calm daily ETF bot"), "01011200")
    (tmp_path / f"{slug}.py").write_text(src)
    row = {}
    msg = sf.neighbors_check(sf.load_file(tmp_path / f"{slug}.py"), {"symbols": ["SPY"]}, None, row)
    assert "knife-edge" in msg and "20% smaller" in msg and calls == [160, 240]


def test_hindsight_note_only_for_hand_picked_stocks():
    assert sf.hindsight_note(["SPY", "QQQ", "IWM"]) is None
    assert "NVDA" in sf.hindsight_note(["QQQ", "NVDA"]) and "ETFs" in sf.hindsight_note(["AAPL"])


def test_drop_reasons_point_at_the_note_that_explains_them():
    from pathlib import Path
    root = Path(sf.__file__).resolve().parent.parent
    assert sf.learn_more("made +3.1R, but with trading costs doubled it's -2.1R") == "docs/what-costs-do-to-small-edges.md"
    assert sf.learn_more("looks like luck: beat 38 of 50") == "docs/why-the-best-setting-looks-better.md"
    assert sf.learn_more("not calm: 17 losses in a row") is None
    assert sf.learn_more("rests on a few lucky trades: without its 3 best") == "docs/how-many-trades-before-you-know.md"
    assert all((root / doc).is_file() for _, doc in sf.LEARN)


def test_busy_words_set_a_trades_a_year_limit(monkeypatch):
    assert sf.understand("an active daily bot")["busy"] == ("active", sf.ACTIVE_MIN_PER_YEAR)
    assert sf.understand("a hands-off swing bot")["busy"][0] == "hands-off"
    assert sf.understand("a daily bot")["busy"] is None and "trades a year" in sf.understand("a part-time bot")["read_as"]
    rep = {"untested": {"trades": 300, "avg_r": 0.2, "total_r": 60, "if_costs_doubled_r": 30, "without_best_3_r": 50,
                        "max_drawdown_r": -5, "worst_losing_streak": 3},
           "years": {"untested": list(range(2016, 2026))}, "losing_untested_years": [], "by_year": []}
    monkeypatch.setattr(sf.report, "full_report", lambda *a, **k: rep)
    monkeypatch.setattr(sf.scaffold, "check_class", lambda c: {"checks": []})
    res = sf.judge(object, sf.understand("a hands-off daily ETF bot"))
    assert not res["kept"] and "too busy for hands-off: 30 trades a year" in res["reason"]


def test_reruns_on_the_same_symbols_count_as_more_tries(monkeypatch):
    kept = {"kept": True, "untested_trades": 100, "avg_r": 0.1, "if_costs_doubled_r": 5, "confidence": "medium",
            "confidence_step": 2, "confidence_why": [], "without_best_3_r": 4, "luck": "beats luck",
            "years_beat_spy": 5, "untested_years": 10}
    monkeypatch.setattr(sf, "judge", lambda cls, spec, fetch=None: dict(kept, confidence_why=[]))
    first = sf.run("a calm daily ETF bot", fetch=demo.bars, demo=True)
    assert "were tried on the same untested years" in first["tries_note"]
    for _ in range(4):
        out = sf.run("a calm daily ETF bot", fetch=demo.bars, demo=True)
    assert "15 candidates have now been tried" in out["tries_note"] and "5 factory runs" in out["tries_note"]
    assert out["kept"][0]["confidence"] == "low" and "down one level" in out["kept"][0]["confidence_why"][-1]
    assert "now been tried" not in sf.run("a calm daily bot on AAPL", fetch=demo.bars, demo=True)["tries_note"]


def test_closest_miss_names_the_best_dropped_candidate():
    d = [{"name": "A", "avg_r": 0.05, "untested_trades": 200, "reason": "not calm: its deepest drop was -15.5R"},
         {"name": "B", "avg_r": -0.1, "untested_trades": 200, "reason": "lost money"},
         {"name": "C", "reason": "failed check_bot"}]
    msg = sf.closest_miss(d)
    assert msg.startswith("Closest miss: A (+0.05R a trade over 200)") and "Without 'calm'" in msg
    assert sf.closest_miss([d[2]]) is None


def test_keep_drop_decisions_never_see_the_held_out_year(monkeypatch):
    seen = []
    real = sf.report.full_report
    monkeypatch.setattr(sf.report, "full_report", lambda *a, **k: seen.append(k.get("today")) or real(*a, **k))
    out = sf.run("a calm daily ETF bot", max_candidates=3, fetch=demo.bars, demo=True)
    assert seen and all(t == sf.holdout_start() for t in seen)
    for k in out["kept"]:
        h = k["held_out"]
        assert h["from"] == str(sf.holdout_start()) and "held out" in h["note"]
    assert "held-out year" in out["markdown"].lower()


def test_a_candidate_opens_by_its_factory_name_before_adopting(monkeypatch):
    monkeypatch.setattr(sf, "judge", lambda cls, spec, fetch=None: {"kept": False, "reason": "x"})
    out = sf.run("a calm daily ETF bot", max_candidates=1, fetch=demo.bars, demo=True)
    cls = loader.get(f"factory/{out['run']}/{out['dropped'][0]['id']}")
    assert cls.name == out["dropped"][0]["name"] == f"{cls.name.split(' (')[0]} ({out['run']})"
    assert loader.bot_id(cls) == out["dropped"][0]["id"]               # the id matches the file, so commands work
    assert f"The number after each name is the run: {sf.run_label(out['run'])}" in out["markdown"]
    assert sf.run_label("1017193647") == "factory run 10-17 19:36:47"
    assert cls.name not in [c.name for c in loader.load_all()[0].values()]          # not in the bots folder
    for bad in ("factory/../../etc/x", "factory/123/x", f"factory/{out['run']}/nope"):
        with pytest.raises(KeyError):
            loader.get(bad)


def test_report_file_and_history(monkeypatch):
    monkeypatch.setattr(sf, "judge", lambda cls, spec, fetch=None: {"kept": False, "reason": "lost money"})
    a = sf.run("a calm daily ETF bot", max_candidates=2, fetch=demo.bars, demo=True)
    sf.run("a calm daily ETF bot", max_candidates=1, fetch=demo.bars, demo=True)
    text = open(a["report_file"]).read()
    assert "a calm daily ETF bot" in text and "Not financial advice" in text and "DEMO DATA" in text
    h = sf.history()
    assert h["runs"][0]["tried"] == 1 and h["runs"][1]["tried"] == 2 and h["runs"][0]["demo"]
    assert h["tries_by_symbols"][0] == {"symbols": "DIA, IWM, QQQ, SPY (1Day)", "runs": 2, "candidates": 3}


def test_same_bets_flags_survivors_that_mostly_trade_together():
    a = {"name": "A", "_entries": [("SPY", "2024-01-02"), ("SPY", "2024-02-01"), ("QQQ", "2024-03-01")]}
    b = {"name": "B", "_entries": [["SPY", "2024-01-02"], ["SPY", "2024-02-01"]]}
    c = {"name": "C", "_entries": [("IWM", "2024-01-02")]}
    out = sf.same_bets([a, b, c])
    assert len(out) == 1 and out[0].startswith("A and B entered the same symbol on the same day in 2 of 2 trades")


def test_robustness_shows_every_check_on_any_bot():
    from pathlib import Path
    root = Path(sf.__file__).resolve().parent.parent
    import shutil
    shutil.copy(root / "bots" / "pullback_swing.py", loader.bots_dir())
    out = sf.robustness(loader.get("pullback_swing"), ["SPY"], fetch=demo.bars)
    names = [c["check"] for c in out["checks"]]
    assert names[:3] == ["check_bot", "30+ untested trades", "makes money after costs"]
    assert "settings ±20% still work" in names and "beats luck" in names and "stops wider than costs" in names
    assert len(names) == 10
    assert out["passed"].endswith(f"of {len(names)}") and out["held_out"]["from"] == str(sf.holdout_start())


def test_saved_robustness_shows_on_the_label():
    from pathlib import Path
    import shutil
    from botscope import label
    shutil.copy(Path(sf.__file__).resolve().parent.parent / "bots" / "pullback_swing.py", loader.bots_dir())
    row = lambda: next(r for r in label.build("pullback_swing")["rows"] if r["label"] == "Robustness checks")  # noqa: E731
    assert row()["value"] == label.MISSING
    sf.robustness(loader.get("pullback_swing"), ["SPY"], fetch=demo.bars, save=True)
    assert " pass" in row()["value"] and row()["help"]


def test_tiny_results_read_as_zero():
    assert sf._r(-0.004) == "0.00R" and sf._r(0.004) == "0.00R" and sf._r(-0.05) == "-0.05R" and sf._r(None) == "–"


def test_tight_stop_drop_links_its_research_note():
    from pathlib import Path
    note = dict(sf.LEARN)["R can't be trusted"]
    assert (Path(sf.__file__).resolve().parent.parent / note).is_file()


def test_next_step_names_the_exact_adopt_command(monkeypatch, tmp_path):
    monkeypatch.setenv("BOTSCOPE_BOTS_DIR", str(tmp_path / "mybots")); (tmp_path / "mybots").mkdir()
    out = sf.run("a calm daily ETF bot", max_candidates=3, fetch=demo.bars, demo=True)
    assert out["kept"], "the demo goal has a survivor (Dip buy) on the seeded demo prices"
    k = out["kept"][0]
    assert f"`botscope adopt_candidate {out['run']} {k['id']}`" in out["next"]
    assert "nutrition_label" in sf.adopt(out["run"], k["id"])["next"]     # and that command really works


def test_crypto_goals_make_crypto_candidates():
    s = sf.understand("a bitcoin trend bot")
    assert s["symbols"] == ["BTC/USD"] and s["asset"] == "crypto" and s["sides"] == "long" and s["timeframe"] == "1Day"
    assert sf.understand("a crypto bot")["symbols"] == sf.CRYPTO and "crypto trading costs" in sf.understand("crypto")["read_as"]
    assert sf.understand("ETH day trading bot")["symbols"] == ["ETH/USD"]             # crypto stays on daily candles
    assert sf.understand("a calm daily ETF bot")["asset"] is None
    _, src = sf.source("trend_ride", s, "1017202228")
    assert "asset = 'crypto'" in src and "symbols = ['BTC/USD']" in src


def test_wishful_goals_get_a_plain_answer_first():
    for g in ("a safe bot for my retirement", "make me money fast", "a risk-free passive income bot"):
        assert "no trading bot is safe" in sf.understand(g)["caution"], g
    assert sf.understand("a calm daily ETF bot")["caution"] is None
    spec = sf.understand("a safe bot for my retirement")
    assert sf.markdown(spec, [], [], 0, False).startswith("_A word on the goal")


@pytest.mark.parametrize("key", [k for k in sf.TEMPLATES if "_rsi(" in sf.TEMPLATES[k]["entry"]])
def test_rsi_templates_skip_the_rsi_when_the_trend_already_says_no(key, tmp_path, monkeypatch):
    """Speed: the RSI is the slow part, so it's only worked out on days the trend filter lets through."""
    from types import SimpleNamespace as NS
    t = sf.TEMPLATES[key]
    spec = sf.understand("a daily bot")
    spec["sides"] = t["sides"][0]
    slug, src = sf.source(key, spec, "01011200")
    path = tmp_path / f"{slug}.py"
    path.write_text(src)
    cls = sf.load_file(path)
    calls = []
    monkeypatch.setitem(cls.entry.__globals__, "_rsi", lambda *a: calls.append(a) or 50.0)
    bot = cls()
    n = bot.p["trend_days"]
    up = [NS(c=100.0 + i, h=101.0 + i, l=99.0 + i, t=i) for i in range(n + 5)]
    down = [NS(c=500.0 - i, h=501.0 - i, l=499.0 - i, t=i) for i in range(n + 5)]
    wrong_way = down if bot.sides == "long" else up
    bot.entry(NS(bars=wrong_way))
    assert calls == []
    bot.entry(NS(bars=up if wrong_way is down else down))
    assert len(calls) == 1


def test_goal_with_too_many_tickers_says_which_were_left_out():
    spec = sf.understand("a daily swing bot for SPY QQQ IWM DIA XLF XLK")
    assert spec["symbols"] == ["SPY", "QQQ", "IWM", "DIA", "XLF"]
    assert "XLK left out: 5 symbols at most" in spec["read_as"]
    assert "left out" not in sf.understand("a daily swing bot for SPY QQQ")["read_as"]
    assert "IWM left out: 3 symbols at most intraday" in sf.understand("an intraday bot for SPY QQQ AAPL IWM")["read_as"]
