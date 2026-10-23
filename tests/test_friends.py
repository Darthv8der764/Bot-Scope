"""Friends: friend codes carry honest numbers only (no keys, dollars, paths; rules and tickers only when asked), pasted
codes are checked field by field and never run, compare gives each side its own lessons, and the page routes refuse
other sites."""
import base64
import hashlib
import json
import zlib
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from botscope import friends, journal, loader, view


def _report(bot="nr7_swing", **k):
    rs = [1.5, -1.0, 2.0, -1.0, 0.5] * 8
    journal.upsert("reports", {"bot": bot}, {
        "untested": {"trades": len(rs), "wins": 24, "avg_r": 0.4, "total_r": 16.0, "net_usd": 98765.0, "costs_r": 2.0,
                     "worst_losing_streak": 3, "max_drawdown_r": -4.0, "if_costs_doubled_r": 14.0,
                     "without_best_3_r": 10.0, "total_r_range_5_50_95": [4.0, 16, 25]},
        "years": {"untested": [2020, 2021, 2022]}, "losing_untested_years": [2021], "untested_rs": rs,
        "vs_spy": {"years_beat": 2},
        "by_year": [{"year": y, "period": "untested", "trades": 13, "avg_r": a} for y, a in ((2020, 0.3), (2021, -0.2), (2022, 0.5))],
        **k})


def _code(c: dict) -> str:
    body = base64.urlsafe_b64encode(zlib.compress(json.dumps(c).encode())).decode().rstrip("=")
    return f"{friends.PREFIX}{body}.{hashlib.sha256(body.encode()).hexdigest()[:6]}"


def _card(**k):
    c = {"friend_card": 1, "name": "Sam", "bot": "Dip bot", "timeframe": "1Day", "data": "real market data",
         "untested_trades": 200, "avg_r": 0.2, "total_r": 40.0, "range_low_r": 20.0, "costs_r": 2.0, "luck": "beats luck",
         "wins": 80, "avg_win_r": 1.2, "avg_loss_r": -0.5, "worst_losing_streak": 4, "losing_years": 0,
         "untested_years": 3, "by_year": [{"year": 2021, "trades": 60, "avg_r": 0.3}]}
    return c | k


def test_code_round_trips_and_holds_no_dollars_keys_or_paths(monkeypatch):
    _report()
    monkeypatch.setenv("ALPACA_API_KEY", "PK" + "SECRET" * 3)          # built here so no key-like text sits in the repo
    out = friends.my_code("nr7_swing", "Ana")
    text = json.dumps(friends.decode(out["code"]))
    assert friends.decode(out["code"])["untested_trades"] == 40
    for bad in ("98765", "usd", "PKSECRET", "/Users/", "@", "rules", "symbols"):
        assert bad not in text, bad
    assert out["characters"] < 2000


def test_rules_and_tickers_only_when_asked():
    _report()
    cls = loader.get("nr7_swing")
    plain = friends.decode(friends.my_code("nr7_swing")["code"])
    full = friends.decode(friends.my_code("nr7_swing", include_rules=True)["code"])
    assert "rules" not in plain and "symbols" not in plain
    assert full["symbols"] == [str(s) for s in cls.symbols][:20] and full["rules"]


def test_needs_a_saved_report():
    with pytest.raises(ValueError):
        friends.my_code("nr7_swing")


@pytest.mark.parametrize("code, why", [
    ("hello", "isn't a BotScope friend code"),
    (friends.PREFIX + "abc.000000", "cut off or changed"),
    ("x" * 20_000, "too long"),
])
def test_bad_codes_are_refused_plainly(code, why):
    with pytest.raises(ValueError, match=why):
        friends.decode(code)


def test_zip_bomb_wrong_version_and_missing_fields_are_refused():
    bomb = {"friend_card": 1, "pad": "A" * 5_000_000}
    with pytest.raises(ValueError, match="can't be read"):
        friends.decode(_code(bomb))                      # tiny code, huge inside
    with pytest.raises(ValueError, match="different BotScope version"):
        friends.decode(_code(_card(friend_card=2)))
    with pytest.raises(ValueError, match="missing"):
        friends.decode(_code({"friend_card": 1, "name": "x"}))


def test_extra_fields_dropped_text_cleaned_numbers_bounded():
    c = friends.decode(_code(_card(name="<img src=x onerror=alert(1)>Sam\x00", code="import os; os.system('rm')",
                                   wins=-3, avg_win_r=True, rules=["<b>buy</b> dips"] * 50, by_year=[{"year": "x"}])))
    assert "<" not in c["name"] and ">" not in c["name"] and "\x00" not in c["name"]
    assert "code" not in c and c["wins"] is None and c["avg_win_r"] is None
    assert len(c["rules"]) == 20 and "<" not in c["rules"][0] and c["by_year"] == []


def test_add_replaces_same_friend_and_bot_and_remove_works():
    friends.add(_code(_card()))
    friends.add(_code(_card(avg_r=0.3)))
    rows = friends.listing()["friends"]
    assert len(rows) == 1 and rows[0]["card"]["avg_r"] == 0.3
    friends.remove(rows[0]["id"])
    assert friends.listing()["friends"] == []


def test_compare_gives_each_side_its_own_lessons():
    _report()
    fid = friends.add(_code(_card(costs_r=0.2, worst_losing_streak=20, rules=["buys dips"])))["added"]
    out = friends.compare("nr7_swing", fid, "Ana")
    assert {r["row"] for r in out["rows"]} >= {"Untested trades", "Trades won", "Costs per trade", "Honest score (per trade)"}
    mine = [x["title"] for x in out["for_you"]]
    theirs = [x["title"] for x in out["for_friend"]]
    assert "Their rules are shared" in mine and "Long losing streaks" in theirs
    assert all("run_backtest" in x["use"] for x in out["for_you"] if x["title"] != "Too few trades to learn much")
    assert "UNTESTED" in out["note"] and "Not financial advice" in out["note"]


def test_demo_cards_teach_nothing_and_small_samples_warn():
    me, them = _card(name="me"), _card(data="DEMO (made-up prices)")
    assert friends.lessons(me, them)[0]["title"] == "Made on demo prices"
    assert friends.lessons(me, _card(untested_trades=10))[0]["title"] == "Too few trades to learn much"


def _post(path, body, headers):
    base = view.ensure_server()
    try:
        return urlopen(Request(base + path, data=json.dumps(body).encode(), headers=headers)).status
    except HTTPError as e:
        return e.code


def test_page_routes_work_and_refuse_other_sites():
    base = view.ensure_server()
    ok = {"Content-Type": "application/json"}
    assert _post("/api/friends/check", {"code": _code(_card())}, ok) == 200
    assert _post("/api/friends/add", {"code": _code(_card())}, {"Content-Type": "text/plain"}) == 403
    assert _post("/api/friends/add", {"code": _code(_card())}, ok | {"Origin": "http://evil.example"}) == 403
    assert _post("/api/friends/add", {"code": _code(_card())}, ok | {"Host": "evil.example"}) == 403
    assert journal.load("friends") == []                 # none of the refused calls saved anything
    assert _post("/api/friends/add", {"code": _code(_card())}, ok) == 200
    assert json.loads(urlopen(base + "/api/friends").read())["friends"][0]["card"]["name"] == "Sam"
    assert b"friendsShell" in urlopen(base + "/friends.js").read()


def test_friends_never_names_order_or_file_writing_calls():
    src = (friends.__file__ and open(friends.__file__).read())
    for bad in ("place_", "submit_order", "exec(", "eval(", "subprocess", "open(", "write_text", "importlib"):
        assert bad not in src, bad


def test_no_name_reads_as_your_friend_not_me():
    _report()
    assert friends.card("nr7_swing")["name"] == "your friend"
    assert "me's" not in json.dumps(friends.lessons(_card(name="x"), friends.card("nr7_swing")))


# ---------- a friend can't take or edit a bot, and neither can you ----------
def _bots_snapshot():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(loader.bots_dir().glob("*.py"))}


def test_friends_flow_never_touches_any_bot_file():
    """Making a code, adding a friend (even one whose card smuggles code), comparing and removing leave every bot
    file exactly as it was, and no new bot appears."""
    _report()
    before = _bots_snapshot()
    sneaky = _card(code="class Stolen(Bot): pass", source="import os", bot_file="nr7_swing.py",
                   rules=["buys dips", "open('bots/nr7_swing.py','w').write('')"])
    friends.my_code("nr7_swing", "Ana", include_rules=True)
    fid = friends.add(_code(sneaky))["added"]
    friends.compare("nr7_swing", fid, "Ana")
    friends.remove(fid)
    view.ensure_server()
    _post("/api/friends/add", {"code": _code(sneaky)}, {"Content-Type": "application/json"})
    assert _bots_snapshot() == before
    assert set(loader.load_all()[0]) == {loader.bot_id(c) for c in loader.load_all()[0].values()}   # loads as before


def test_a_friend_card_holds_no_code_only_numbers_and_text():
    c = friends.decode(_code(_card(code="x=1", source="y", file="z.py", python="print(1)")))
    assert set(c) <= {"friend_card", "by_year", "rules", "symbols", *friends.NUM, *friends.TEXT}
    assert not any(isinstance(v, str) and ("class " in v or "import " in v) for v in c.values())


def test_no_way_from_a_friend_card_to_a_bot():
    """Nothing in the Friends code, its page routes or its tool can write, copy or adopt a bot."""
    from pathlib import Path
    root = Path(friends.__file__).parent
    src = (root / "friends.py").read_text() + (root / "web" / "friends.js").read_text()
    for bad in ("adopt", "scaffold", "new_bot", "bots_dir", "checkpoints", ".write(", "write_text", "write_bytes",
                "copyfile", "shutil", "open(", "importlib", "exec(", "eval("):
        assert bad not in src, bad
    view_src = (root / "view.py").read_text()
    block = view_src[view_src.index('"/api/friends/code"'):view_src.index('if path == "/api/phantom"')]
    assert "friends." in block and not any(w in block for w in ("adopt", "scaffold", "loader.", "write_text", ".write(", "open("))
