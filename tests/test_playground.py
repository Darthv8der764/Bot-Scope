"""Offline checks of the rule playground (fake bars, no keys)."""
import time

from botscope import playground
from botscope.backtest import Trade


def _t(r, side="long", blocked="", i=0):
    t = Trade("SPY", "2026-01-02", side, 100, 101, 99, "", "stop", r, r * 0.5, 0.05,
              t_in=f"2026-01-{i % 28 + 1:02d}T10:00:00-05:00", risk_pct=0.5)
    t.blocked_by, t.ghost = blocked, bool(blocked)
    return t


def _cache(monkeypatch):
    c = {"bot": "x", "name": "X", "window": {"from": "2026-01-01", "to": "2026-03-01", "period": "untested"}, "trading_days": 42, "problems": [], "seconds": 0.1,
         "trades": [_t(0.5 if i % 3 else -1.0, "long" if i % 2 else "short", i=i) for i in range(30)],
         "ghosts": [_t(-1.0, blocked=f"range too narrow ({0.1 + i / 100:.2f}%)", i=i) for i in range(6)]
                   + [_t(2.0, blocked="past 11:00, no new trades", i=i) for i in range(2)]}
    monkeypatch.setattr(playground, "precompute", lambda bot_id, fetch=None: c)
    monkeypatch.setitem(playground._cache, "x", c)


def test_rule_key_groups_numbers():
    assert playground.rule_key("range too narrow (0.15%)") == playground.rule_key("range too narrow (0.31%)")
    assert playground.rule_key("past 11:00, no new trades") == "past 11:00, no new trades"


def test_toggle_is_fast_and_marks_what_matters(monkeypatch):
    _cache(monkeypatch)
    t0 = time.time()
    p = playground.play("x", rules_off=["range too narrow (9%)"])
    assert time.time() - t0 < 5 and p["trades"] == 36
    r = {x["rule"]: x for x in p["rules"]}
    assert r["range too narrow"]["matters"].startswith("yes: it saves 6.0R") and not r["range too narrow"]["on"]
    assert r["past 11:00, no new trades"]["matters"].startswith("barely")
    assert p["this_mix"]["middle_usd"] < p["as_coded"]["middle_usd"]


def test_projection_is_a_labeled_range_and_never_a_percent(monkeypatch):
    _cache(monkeypatch)
    p = playground.play("x", side="short")
    m = p["this_mix"]
    assert m["bad_usd"] <= m["middle_usd"] <= m["good_usd"] and "untested trades" in m["text"]
    assert "%" not in m["text"] and p["trades"] == 15 and "$-" not in m["text"] and "$+" not in m["text"]


def test_too_few_trades_says_so(monkeypatch):
    _cache(monkeypatch)
    assert playground.month_range([_t(1)] * 5, 42, 10_000)["enough"] is False


def test_every_mix_counts_as_a_setting_tried_on_the_same_days(monkeypatch):
    _cache(monkeypatch)
    assert "tries_note" not in playground.play("x")                    # as coded
    playground.play("x", rules_off=["range too narrow"])
    p = playground.play("x", side="long")
    assert p["settings_tried_on_these_days"] == 3 and "tuned days" in p["tries_note"]
    assert playground.play("x", side="long")["settings_tried_on_these_days"] == 3   # same mix again: not a new try


def test_a_big_lead_says_how_to_test_it_not_to_flip_it(monkeypatch):
    _cache(monkeypatch)
    c = playground.precompute("x")
    c["ghosts"] += [_t(1.0, blocked="gap too small", i=i) for i in range(12)]
    r = {x["rule"]: x for x in playground.play("x")["rules"]}
    assert "make_shadow x" in r["gap too small"]["worth_testing"] and "worth_testing" not in r["range too narrow"]


def test_disk_cache_survives_a_restart_and_goes_stale_when_the_stamp_changes():
    c = {"bot": "x", "name": "X", "window": {"from": "a", "to": "b"}, "trading_days": 42, "problems": [],
         "seconds": 3.0, "stamp": "s1", "trades": [_t(0.5, i=i) for i in range(3)], "ghosts": [_t(-1, blocked="r")]}
    playground._save(c)
    back = playground._load("x", "s1")
    assert back["trades"][0].r == 0.5 and back["ghosts"][0].blocked_by == "r" and back["ghosts"][0].ghost
    assert playground._load("x", "s2") is None


def test_each_rule_lists_its_newest_blocked_trades(monkeypatch):
    _cache(monkeypatch)
    r = {x["rule"]: x for x in playground.play("x")["rules"]}
    nb = r["range too narrow"]["newest_blocked"]
    assert len(nb) == 6 and nb[0]["day"] >= nb[-1]["day"] and set(nb[0]) == {"day", "symbol", "side", "r"}


def test_sides_lead_only_when_one_side_is_clearly_better(monkeypatch):
    _cache(monkeypatch)
    c = playground.precompute("x")
    c["trades"] = [_t(0.5, "long", i=i) for i in range(12)] + [_t(-0.6, "short", i=i) for i in range(12)]
    p = playground.play("x")                     # shorts lost 7.2R: longs only is clearly better
    assert (p["sides_lead"] or "").startswith("longs only made +7.2R") and "make_shadow" in p["sides_lead"]
    c["trades"] = [t for t in c["trades"] if t.side == "long"]
    assert playground.play("x")["sides_lead"] is None
