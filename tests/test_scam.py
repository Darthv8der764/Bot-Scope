from botscope import journal, scam


def test_red_flags_are_held_back_with_reasons():
    r = scam.check("Guaranteed profits every week! 95% win rate. Join our VIP Telegram group, limited spots, "
                   "use my referral link. If you lose, just double down after a loss to recover.")
    names = {f["flag"] for f in r["flags"]}
    assert r["verdict"] == "red" and r["held_back"]
    assert {"guaranteed returns", "too-good win rate", "pay to join signals", "urgency", "affiliate broker links",
            "doubling down after losses"} <= names
    assert all(f["why"] for f in r["flags"])


def test_plain_strategy_is_green_but_not_called_good():
    r = scam.check("Buy when the price closes above the 20-day high, stop below the 10-day low. It lost money in 2022.")
    assert r["verdict"] == "green" and not r["held_back"] and "doesn't make it good" in r["next"]


def test_one_soft_flag_is_yellow():
    assert scam.check("Sign up with my referral link to get the broker bonus.")["verdict"] == "yellow"


def test_pump_wording_alone_is_red():
    assert scam.check("This hidden gem is about to explode, next 100x, load up now")["verdict"] == "red"


def test_letting_red_through_is_logged():
    scam.let_through("some video", "I want to see the backtest anyway")
    assert journal.find("scam_overrides")[0]["reason"] == "I want to see the backtest anyway"
