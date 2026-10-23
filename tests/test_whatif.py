"""Offline checks of the what-if stop/target grid (made-up bars, no network)."""
import json
from types import SimpleNamespace
from urllib.request import urlopen

from botscope import backtest, loader, view, whatif
from botscope.bot import Entry
from test_luck import fetch_from, walk_day
from test_report import shifted


def test_hook_scales_stop_and_sets_target():
    v = SimpleNamespace(last=SimpleNamespace(c=100.0))
    e = Entry("long", 99.0, 102.0, "why")
    assert whatif.scale_hook(1.0, None)(v, e) == e
    w = whatif.scale_hook(2.0, 1.5)(v, e)
    assert (w.stop, w.target, w.reason) == (98.0, 103.0, "why")
    s = whatif.scale_hook(0.5, 2.0)(v, Entry("short", 101.0, 98.0))
    assert (s.stop, s.target) == (100.5, 99.0)


def test_grid_baseline_matches_plain_run_and_saves(relabel):
    cls = relabel("first_hour_breakout", tuned_on=("2025-10-01", "2026-10-01"))   # 10 untested days before that
    fetch = fetch_from(lambda d, n: shifted(d))
    g = whatif.grid(cls, ["AAA"], days=10, fetch=fetch)
    assert len(g["cells"]) == len(whatif.STOP_X) * len(whatif.TARGET_R) and g["window"]["period"] == "untested"
    (_, a, b), = [w for w in backtest.windows(cls, 10) if w[0] == "untested"]
    plain, _, _ = backtest.run_window(cls(), ["AAA"], a, b, fetch=fetch)
    assert g["baseline"]["trades"] == len(plain) and g["baseline"]["total_r"] == round(sum(t.r for t in plain), 2)
    assert "warning" in g                                  # few made-up trades: says it's noise
    assert whatif.saved("first_hour_breakout")["cells"] == g["cells"]


def test_best_looking_comes_with_a_caution():
    g = whatif.grid(loader.get("first_hour_breakout"), ["AAA", "BBB"], days=20, fetch=fetch_from(walk_day))
    assert "best_looking" in g or "warning" in g
    if "best_looking" in g:
        assert "worse on new days" in g["best_looking"]["caution"]


def test_page_route_uses_saved_grid(monkeypatch):
    monkeypatch.setattr(whatif, "grid", lambda cls: {"cells": [], "fresh": True})
    base = view.ensure_server()
    assert json.loads(urlopen(base + "/api/whatif?bot=first_hour_breakout").read())["fresh"] is True
    html = open(view.PAGE).read()
    assert 'id="wi-load"' in html and "/api/whatif?" in html


def test_cells_with_tight_stops_are_never_best_looking(monkeypatch):
    real = backtest.tight_stops
    monkeypatch.setattr(backtest, "tight_stops", lambda u: "tight" if u.get("trades") and _halved[0] else real(u))
    _halved = [False]
    real_cell = whatif._cell

    def cell(bot, groups, cost, stop_x, target_r, notional):
        _halved[0] = stop_x == 0.5                     # pretend every 0.5x-stop cell has stops inside its costs
        c = real_cell(bot, groups, cost, stop_x, target_r, notional)
        if stop_x == 0.5:
            c["total_r"] = 999.0                       # and that it looks wonderful
        return c
    monkeypatch.setattr(whatif, "_cell", cell)
    g = whatif.grid(loader.get("first_hour_breakout"), ["AAA", "BBB"], days=20, fetch=fetch_from(walk_day))
    assert all(c.get("tight_stops") for c in g["cells"] if c["stop_x"] == 0.5 and c["trades"])
    assert "tight_stop_cells" in g
    assert g.get("best_looking", {}).get("stop_x") != 0.5
