"""A new user with an empty .env gets short, useful messages (where to get a free key), never a crash."""
import pytest

from botscope import daily_log
from botscope.market_data import _http, market_calendar


@pytest.fixture
def empty_env(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('FRED_API_KEY=\nSEC_USER_AGENT="BotScope your-email@example.com"\n')
    monkeypatch.setenv("BOTSCOPE_ENV_FILE", str(f))
    for k in ("FRED_API_KEY", "FINNHUB_API_KEY", "SEC_USER_AGENT"):
        monkeypatch.delenv(k, raising=False)


def test_missing_key_says_where_to_get_it(empty_env):
    with pytest.raises(RuntimeError, match="FRED_API_KEY missing: get one free at fred.stlouisfed.org"):
        _http.need_key("FRED_API_KEY")


def test_placeholder_sec_contact_is_not_sent(empty_env):
    with pytest.raises(RuntimeError, match="SEC_USER_AGENT missing"):
        _http.sec_user_agent()


def test_calendar_row_stays_short():
    assert market_calendar._short(RuntimeError("FRED_API_KEY missing: get one free at x")) == \
        "FRED_API_KEY missing (free: add it in Studio's Get started tab)"
    assert market_calendar._short(RuntimeError("timeout")) == "timeout"


def test_same_error_for_every_bot_is_one_line():
    out = daily_log.group_problems([("a AAPL", "RuntimeError: keys missing"), ("a MSFT", "RuntimeError: keys missing"),
                                    "bad.py: SyntaxError"])
    assert out == ["a AAPL, a MSFT: RuntimeError: keys missing", "bad.py: SyntaxError"]


def test_keys_fall_back_to_home_botscope_env(tmp_path, monkeypatch):
    from botscope import env
    monkeypatch.delenv("BOTSCOPE_ENV_FILE", raising=False)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr(env, "ROOT", tmp_path / "plugin")          # no .env in the plugin folder
    home = tmp_path / "home.env"
    home.write_text("FRED_API_KEY=abc\n")
    monkeypatch.setattr(env, "HOME_ENV", home)
    assert env.key("FRED_API_KEY") == "abc"
