"""Offline checks of shadow mode."""
from botscope import journal, shadow
from botscope.bot import Bot


class Old(Bot):
    name, version = "ORB", "1.0"


class New(Bot):
    name, version, shadows = "ORB", "2.0", "old"


class Lone(Bot):
    name = "Lone"


BOTS = {"old": Old, "new": New, "lone": Lone}


def _log(bot, day, r, n=1):
    for i in range(n):
        journal.upsert("paper_results", {"bot": bot, "symbol": "SPY", "day": day, "trade_id": f"{bot}{day}{i}"},
                       {"r": r})


def test_families_only_with_shadows():
    assert shadow.families(BOTS) == {"old": ["old", "new"]}
    assert "No shadows yet" in shadow.scoreboard(bots={"lone": Lone})["how"]


def test_same_days_only_and_too_early_verdict():
    _log("old", "2026-10-01", 5.0)          # before the shadow existed: left out
    _log("old", "2026-10-14", -1.0)
    _log("new", "2026-10-14", 2.0)
    _log("old", "2026-10-15", 1.0)
    _log("new", "2026-10-15", 1.0)
    f = shadow.scoreboard(bots=BOTS)["families"][0]
    v = {b["bot"]: b for b in f["versions"]}
    assert f["compared_since"] == "2026-10-14" and f["day"] == "2026-10-15"
    assert v["old"]["total_r"] == 0.0 and v["new"]["total_r"] == 3.0 and v["new"]["day_r"] == 1.0
    assert v["new"]["role"] == "shadow of old" and "too early" in f["verdict"]


def test_leader_named_only_with_enough_trades_and_no_percent():
    _log("old", "2026-10-14", -0.1, 20)
    _log("new", "2026-10-14", 0.2, 20)
    f = shadow.scoreboard(bots=BOTS)["families"][0]
    assert "v2.0 leads" in f["verdict"] and "%" not in str(f)


def test_waiting_until_both_have_results():
    _log("old", "2026-10-14", 1.0)
    assert "waiting" in shadow.scoreboard(bots=BOTS)["families"][0]["verdict"]


def test_phone_line_for_the_end_of_day_alert():
    assert shadow.phone_line("2026-10-15", BOTS) == ""
    _log("old", "2026-10-15", -2.04)
    _log("new", "2026-10-15", 0.4)
    assert shadow.phone_line("2026-10-15", BOTS) == "Shadows today: ORB: v1.0 -2.04R, v2.0 +0.40R"
    assert shadow.phone_line("2026-10-16", BOTS) == ""
