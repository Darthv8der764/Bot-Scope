"""Offline checks of ghost trades, the full honest report and the crash time machine (made-up bars, no network)."""
from datetime import date, datetime, timedelta

import pytest

from botscope import backtest, journal, loader, report
from botscope.data import ET
from test_format import fake_day


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_JOURNAL_DIR", str(tmp_path))


def shifted(day: date, up=True):
    """fake_day() moved to another date."""
    base = fake_day(up)
    delta = datetime(day.year, day.month, day.day, tzinfo=ET) - datetime(2026, 9, 1, tzinfo=ET)
    return [b.__class__(b.t + delta, b.o, b.h, b.l, b.c, b.v) for b in base]


def fake_fetch(sym, start, end, tf, feed):
    """Two weekdays per window: one breakout up (a win), one down (a short win)."""
    days, d = [], start
    while len(days) < 2 and d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    out = []
    for i, d in enumerate(days):
        out += shifted(d, up=i % 2 == 0)
    return out


def test_ghost_trade_when_a_filter_blocks_a_break():
    bot = loader.get("first_hour_breakout")(min_width=0.05)       # range filter now blocks the day
    trace, ghosts = [], []
    trades, _ = backtest.run_day(bot, "TEST", date(2026, 9, 1), fake_day(), backtest.COSTS[bot.asset],
                                 trace=trace, ghosts=ghosts)
    assert trades == [] and len(ghosts) == 1
    g = ghosts[0]
    assert g.ghost and g.side == "long" and g.why_out == "target hit" and g.r > 1.5
    assert any("ghost" in x and "too quiet" in x["reason"] for x in trace)
    s = backtest.ghost_summary(ghosts)
    assert s["ghosts"] == 1 and "costing you" in s["verdict"] and "luck" in s["verdict"]


def test_no_ghost_when_the_bot_trades():
    bot = loader.get("first_hour_breakout")()
    ghosts = []
    trades, _ = backtest.run_day(bot, "TEST", date(2026, 9, 1), fake_day(), backtest.COSTS[bot.asset], ghosts=ghosts)
    assert len(trades) == 1 and ghosts == []


def test_costs_are_shown():
    bot = loader.get("first_hour_breakout")()
    trades, _ = backtest.run_day(bot, "TEST", date(2026, 9, 1), fake_day(), backtest.COSTS[bot.asset])
    s = backtest.summarize(trades, 10_000)
    assert s["before_costs_r"] > s["total_r"] and s["costs_r"] > 0


def test_year_windows_split_tuned_and_untested(relabel):
    cls = relabel("first_hour_breakout", tuned_on=("2025-10-01", "2026-10-01"))
    ws = report.year_windows(cls, today=date(2026, 10, 16))
    assert ws[0]["year"] == 2016 and ws[-1]["year"] == 2026
    assert {w["period"] for w in ws if w["year"] <= 2024} == {"untested"}
    assert any(w["period"] == "tuned" for w in ws)
    assert all((w["to"] - w["from"]).days <= 31 for w in ws)        # intraday: one month per year
    daily = report.year_windows(loader.get("nr7_swing"), today=date(2026, 10, 16))
    assert daily[0]["from"] == date(2016, 1, 1) and daily[-1]["to"] == date(2026, 10, 15)


def test_full_report_is_honest_and_saved(relabel):
    cls = relabel("first_hour_breakout", tuned_on=("2025-10-01", "2026-10-01"))
    r = report.full_report(cls, symbols=["TEST"], fetch=fake_fetch, today=date(2026, 10, 16))
    assert r["untested"]["trades"] >= 10 and r["tuned"]["trades"] >= 1
    assert "total_r_range_5_50_95" in r["untested"] and "worst_losing_streak" in r["untested"]
    assert r["untested"]["costs_r"] > 0
    assert "untested trades" in r["headline"] and "%" not in r["headline"]
    rows = {c["crash"]: c for c in r["crashes"]}
    assert rows["2008 financial crisis"]["tested"] is False and "2016" in rows["2008 financial crisis"]["result"]
    assert rows["2020 covid crash"]["tested"] and rows["2020 covid crash"]["trades"] == 2
    assert report.saved(cls)["untested"]["trades"] == r["untested"]["trades"]
    assert journal.find("backtests", bot="first_hour_breakout")[-1]["source"] == "full report"


def test_crash_test_keeps_going_when_a_symbol_has_no_data():
    def flaky(sym, *a):
        if sym == "BAD":
            raise ValueError("no such symbol")
        return fake_fetch(sym, *a)
    ct = report.crash_test(loader.get("first_hour_breakout"), ["BAD", "TEST"], fetch=flaky)
    assert ct["problems"] and any(c.get("trades") for c in ct["crashes"])


def test_nutrition_label_says_what_is_missing_then_fills_in():
    from botscope import label
    lb = label.build("first_hour_breakout")
    vals = {r["label"]: r["value"] for r in lb["rows"]}
    assert vals["Untested trades"] == label.MISSING and "Untested trades" in lb["missing"]
    md = label.markdown(lb)              # a fresh install says how to fill it in, and claims no data source
    assert "rows not measured yet. Run honest_report first_hour_breakout (one backtest)" in md
    assert "Data: none yet" in md and "Alpaca" not in md
    report.full_report(loader.get("first_hour_breakout"), symbols=["TEST"], fetch=fake_fetch, today=date(2026, 10, 16))
    lb = label.build("first_hour_breakout")
    vals = {r["label"]: r["value"] for r in lb["rows"]}
    assert vals["Untested trades"] != label.MISSING and "R" in vals["Per trade, after costs"]
    assert "2020 covid crash" in vals["Crashes"] and "2008" not in vals["Crashes"]
    assert vals["If costs doubled"].endswith("R") and vals["If costs doubled"] != vals["Total, after costs"]
    md = label.markdown(lb)
    assert md.startswith("**First hour breakout") and "| Confidence |" in md and "%" not in md



def test_summary_counts_wins_never_a_win_percent():
    from botscope.backtest import Trade, summarize
    ts = [Trade("A", "2026-01-02", "long", 10, 11, 9, "", "", r, r, 0.1, risk_pct=1) for r in (1.0, -1.0, 2.0)]
    s = summarize(ts, 10_000)
    assert s["wins"] == 2 and s["trades"] == 3 and not any("rate" in k or "pct" in k for k in s)


def test_streak_and_drop_follow_time_not_symbol_order():
    from botscope.backtest import Trade, summarize
    mk = lambda sym, d, r: Trade(sym, d, "long", 10, 11, 9, "", "", r, r, 0.1, t_in=d + "T10:00", t_out=d + "T11:00",
                                 risk_pct=1)
    a = [mk("A", "2026-01-02", -1), mk("A", "2026-01-06", -1), mk("B", "2026-01-05", 2), mk("B", "2026-01-07", 2)]
    b = a[2:] + a[:2]
    assert summarize(a, 10_000)["worst_losing_streak"] == summarize(b, 10_000)["worst_losing_streak"] == 1
    assert summarize(a, 10_000)["max_drawdown_r"] == summarize(b, 10_000)["max_drawdown_r"]


def test_costs_doubled_stress_line():
    from botscope.backtest import Trade, summarize
    ts = [Trade("A", "2026-01-02", "long", 10, 11, 9, "", "", r, r * 1, 0.1, risk_pct=1) for r in (1.0, -0.5)]
    s = summarize(ts, 10_000)
    assert s["costs_r"] == 0.2 and s["if_costs_doubled_r"] == round(s["total_r"] - 0.2, 2)


def test_receipt_adds_up_and_names_slippage():
    from botscope import backtest
    t = backtest.Trade("X", "2025-01-02", "long", 100.0, 98.9923, 99.0, "broke the range", "stop hit",
                       -1.1, -1.1923, 0.01, slip_pct=0.077)
    r = backtest.receipt(t)
    assert r["shares_about"] == 100 and r["costs_usd"] == -1.0 and r["slippage_usd"] == -7.7
    assert round(r["price_move_usd"] + r["costs_usd"] + r["slippage_usd"], 2) == r["net_usd"] == -119.23


def test_without_best_3_shows_dependence_on_a_few_trades():
    from botscope.backtest import Trade, summarize
    rs = [-0.5] * 9 + [6.0, 0.2, 0.1]
    ts = [Trade("A", f"2026-01-{i + 2:02d}", "long", 10, 11, 9, "", "", r, r, 0.1, risk_pct=1) for i, r in enumerate(rs)]
    s = summarize(ts, 10_000)
    assert s["total_r"] > 0 and s["without_best_3_r"] == -4.5
    assert "without_best_3_r" not in summarize(ts[:9], 10_000)          # under 10 trades: too few to say


def test_every_label_row_but_status_has_a_plain_help_line():
    from botscope import label
    for k, v in label.HELP.items():
        assert v.endswith((".", "?")) and len(v) < 140, k


def test_costs_in_plain_dollars_per_trade():
    from botscope.label import _per_trade_usd
    assert _per_trade_usd({"trades": 963, "costs_usd": 9630.0}, {"position_size_usd": 10_000}) == \
        " ($10.00/trade at $10k)"
    assert _per_trade_usd({"trades": 0}, {}) == ""


def test_label_warns_when_the_bot_file_changed_since_its_report(tmp_path, monkeypatch):
    from botscope import label
    cls = loader.get("first_hour_breakout")
    f = tmp_path / "copy.py"
    f.write_text("x = 1\n")
    monkeypatch.setattr(cls, "source_file", str(f))
    monkeypatch.setattr(loader, "get", lambda name: cls)             # the loader re-reads bot files on each call
    r = report.full_report(cls, symbols=["TEST"], fetch=fake_fetch, today=date(2026, 10, 16))
    assert report.saved(cls)["bot_file_hash"] == report.fingerprint(cls)
    assert label.build("first_hour_breakout")["bot_changed"] is None          # same file: quiet
    f.write_text("x = 2\n")
    lbl = label.build("first_hour_breakout")
    assert "changed after this report" in lbl["bot_changed"] and "honest_report" in lbl["bot_changed"]
    assert lbl["bot_changed"] in label.markdown(lbl)
    journal.upsert("reports", {"bot": "first_hour_breakout"}, {"untested": r["untested"]})   # old report, no fingerprint
    assert label.build("first_hour_breakout")["bot_changed"] is None


def test_notes_and_comments_in_the_bot_file_are_not_a_change(tmp_path, monkeypatch):
    cls = loader.get("first_hour_breakout")
    f = tmp_path / "copy.py"
    f.write_text('"""A bot."""\nclass B:\n    """Rules."""\n    x = 1  # stop\n')
    monkeypatch.setattr(cls, "source_file", str(f))
    rep = {"bot_file_hash": report.fingerprint(cls)}
    legacy = {"bot_file_hash": report.fingerprint(cls, code_only=False)}   # reports saved before this change
    f.write_text('"""A bot.\n\nFirst report: +3R over 40 untested trades."""\nclass B:\n    """Rules, longer."""\n    x = 1  # the stop\n')
    assert not report.changed_since(cls, rep)
    assert report.changed_since(cls, legacy)          # whole-file fingerprint: the file did change
    f.write_text('"""A bot."""\nclass B:\n    """Rules."""\n    x = 2  # stop\n')
    assert report.changed_since(cls, rep)
    f.write_text("def broken(:\n")                   # can't parse: falls back to the raw file
    assert report.changed_since(cls, rep)


def test_every_label_row_explains_itself():
    from botscope import label
    lbl = label.build("nr7_swing")
    assert [r["label"] for r in lbl["rows"] if not r["help"]] == []


def test_preflight_flags_a_bot_changed_since_its_report(tmp_path, monkeypatch):
    from botscope import preflight
    cls = loader.get("first_hour_breakout")
    f = tmp_path / "copy.py"
    f.write_text("x = 1\n")
    monkeypatch.setattr(cls, "source_file", str(f))
    journal.upsert("reports", {"bot": "first_hour_breakout"}, {"untested": {}, "bot_file_hash": report.fingerprint(cls)})
    assert not any("changed" in w for w in preflight.warnings_for(cls))
    f.write_text("x = 2\n")
    assert "changed since its report (honest_report again)" in preflight.warnings_for(cls)


def test_label_warns_when_trading_costs_changed_since_its_report(tmp_path, monkeypatch):
    from botscope import label
    cls = loader.get("first_hour_breakout")
    f = tmp_path / "copy.py"
    f.write_text("# same file\n")
    monkeypatch.setattr(cls, "source_file", str(f))
    monkeypatch.setattr(loader, "get", lambda name: cls)
    journal.upsert("reports", {"bot": "first_hour_breakout"}, {"untested": {}, "bot_file_hash": report.fingerprint(cls)})
    assert label.build("first_hour_breakout")["bot_changed"] is None
    monkeypatch.setitem(backtest.COSTS, "stock_intraday", {**backtest.COSTS["stock_intraday"], "_test": 1})
    assert "trading costs changed" in label.build("first_hour_breakout")["bot_changed"]


def test_preflight_flags_an_old_report(monkeypatch):
    from botscope import preflight
    cls = loader.get("nr7_swing")
    journal.upsert("reports", {"bot": "nr7_swing"}, {"untested": {}})
    monkeypatch.setattr(preflight, "_today", lambda: date.today() + timedelta(days=89))
    assert not any("days old" in w for w in preflight.warnings_for(cls))
    monkeypatch.setattr(preflight, "_today", lambda: date.today() + timedelta(days=120))
    assert "report is 120 days old (newer days aren't in it; honest_report again)" in preflight.warnings_for(cls)


def test_signed_dollars_read_naturally():
    from botscope import benchmark
    assert benchmark.usd(8324.48) == "+$8,324" and benchmark.usd(-578.9) == "-$579" and benchmark.usd(0) == "+$0"
    v = benchmark.verdict(529.44, {"usd": 1146.69})
    assert "(bot +$529, SPY +$1,147)" in v and "$+" not in v


def test_warmup_covers_a_daily_bots_lookback():
    from botscope import backtest
    pb, orb = loader.get("pullback_swing"), loader.get("first_hour_breakout")
    assert backtest.warmup_days(orb, 30) == 0                              # intraday: each session stands alone
    assert backtest.warmup_days(loader.get("nr7_swing"), 30) == 30         # no lookback declared: the old floor
    assert backtest.warmup_days(pb, 30) >= 200 * 365 / 252                  # 200 trading days in calendar days


def test_report_says_which_years_are_still_warming_up():
    from botscope import backtest
    pb, nr7 = loader.get("pullback_swing")(), loader.get("nr7_swing")()
    rows = [{"year": y, "from": f"{y}-01-01"} for y in (2016, 2017, 2018)]
    assert report.warming_up_years(pb, rows, backtest.warmup_days(pb, 30)) == [2016]
    assert report.warming_up_years(nr7, rows, backtest.warmup_days(nr7, 30)) == []      # no long lookback


def test_a_quick_run_replaces_a_full_report_from_an_older_bot_version():
    from botscope import backtest
    cls = loader.get("first_hour_breakout")
    report.full_report(cls, symbols=["TEST"], fetch=fake_fetch, today=date(2026, 10, 16))
    backtest.run(cls, ["TEST"], days=10, fetch=fake_fetch)
    assert journal.find("backtests", bot="first_hour_breakout")[-1]["source"] == "full report"   # same bot: kept
    row = journal.find("backtests", bot="first_hour_breakout")[-1]
    journal.upsert("backtests", {"bot": "first_hour_breakout"}, {k: v for k, v in row.items() if k != "bot"} | {"version": "0.1"})
    backtest.run(cls, ["TEST"], days=10, fetch=fake_fetch)
    now = journal.find("backtests", bot="first_hour_breakout")[-1]
    assert now.get("source") != "full report" and now["version"] == cls.version   # the meter reads today's bot


def test_symbols_past_the_cap_are_named_not_dropped_quietly():
    from botscope import backtest, luck, timemap, whatif
    cls = loader.get("first_hour_breakout")
    many = ["TEST", "B", "C", "D", "E", "F", "G"]
    assert backtest.left_out(many) == "tested on the first 5 symbols only; left out: F, G"
    assert backtest.left_out(many[:5]) is None and backtest.left_out(["a", "A"]) is None
    assert any("left out: F, G" in p for p in backtest.run(cls, many, days=10, fetch=fake_fetch)["problems"])
    r = report.full_report(cls, symbols=many, fetch=fake_fetch, today=date(2026, 10, 16), crashes=False, save=False)
    assert any("left out: F, G" in p for p in r["problems"])
    assert "F, G" in whatif.grid(cls, many, days=10, fetch=fake_fetch)["left_out"]
    assert any("F, G" in p for p in timemap.time_map(cls, many, days=10, fetch=fake_fetch)["problems"])
    assert "F, G" in luck.luck_meter(cls, many, fetch=fake_fetch, twins=3, shuffles=1, save=False)["left_out"]


def test_crypto_results_never_say_sip(monkeypatch):
    from botscope import demo, timemap, whatif
    monkeypatch.setattr(demo, "active", lambda: False)
    cls = loader.get("crypto_trend")
    for out in (timemap.time_map(cls, ["BTC/USD"], days=10, fetch=fake_fetch),
                whatif.grid(cls, ["BTC/USD"], days=10, fetch=fake_fetch)):
        assert "SIP" not in out["data"] and "crypto" in out["data"].lower()
    assert "SIP" in report.data_line(["SPY"])


def test_label_shows_the_newest_optimizer_verdict_in_short():
    from botscope import journal, label
    assert {r["label"]: r["value"] for r in label.build("nr7_swing")["rows"]}["Optimizer"] == label.MISSING
    for when, v in (("2026-10-01T00:00:00", "lead to test: a=1, b=2 sits on a plateau"),
                    ("2026-10-18T00:00:00", "keep today's settings: the best cell is a lone island")):
        journal.upsert("optimizer", {"bot": "nr7_swing", "settings": ["a", "b"] if "lead" in v else ["c", "d"]},
                       {"verdict": v, "settings": ["a", "b"] if "lead" in v else ["c", "d"], "cells_tried": 25, "saved_at": when})
    row = {r["label"]: r["value"] for r in label.build("nr7_swing")["rows"]}["Optimizer"]
    assert row == "keep today's settings (c × d, 25 tried, 10-18)"
    from botscope.label import _short_verdict
    assert _short_verdict("no cell makes money after costs on the untested years (best -0.05R a trade): x") == \
        "no setting pair makes money"
