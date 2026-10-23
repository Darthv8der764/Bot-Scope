"""Get started: keys are checked before saving, paper only, saved readable only by you, never shown back, and the
routes need what the console needs (this computer, exact host and origin, this launch's token)."""
import json
import os
import stat
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import pytest

from botscope import console, setup_guide, view

KEY = "PK" + "TESTKEY" + "0" * 9 + "1"        # built at runtime: no key-shaped text in the repo (redteam scan)
SECRET = "testSecret" + "0" * 29 + "1"


@pytest.fixture(autouse=True)
def _env_file(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    monkeypatch.setenv("BOTSCOPE_ENV_FILE", str(p))
    for k in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "FRED_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    setup_guide._cache.clear()
    return p


def _accept(monkeypatch, ok=True):
    calls = []
    monkeypatch.setattr(setup_guide, "check_alpaca", lambda k, s, timeout=10: calls.append((k, s)) or
                        ({"ok": True, "why": "accepted"} if ok else {"ok": False, "why": "Alpaca didn't accept these keys"}))
    return calls


def test_live_keys_are_refused_before_anything_is_sent(monkeypatch, _env_file):
    calls = _accept(monkeypatch)
    r = setup_guide.save_alpaca("AK" + "LIVEKEY" + "0" * 9 + "1", SECRET)
    assert not r["saved"] and "LIVE" in r["why"] and not calls and not _env_file.exists()


def test_bad_looking_keys_are_refused(monkeypatch, _env_file):
    _accept(monkeypatch)
    for k, s in (("pk-lower", SECRET), ("PKOK0000000000", "short"), ("", ""), ("PK00000000000\nX=1", SECRET)):
        assert not setup_guide.save_alpaca(k, s)["saved"]
    assert not _env_file.exists()


def test_rejected_keys_are_not_saved(monkeypatch, _env_file):
    _accept(monkeypatch, ok=False)
    r = setup_guide.save_alpaca(KEY, SECRET)
    assert not r["saved"] and "didn't accept" in r["why"] and not _env_file.exists()


def test_accepted_keys_are_saved_private_and_never_shown_back(monkeypatch, _env_file):
    _env_file.write_text("FRED_API_KEY=abc\n# my note\nALPACA_API_KEY=PKOLD000000000\n")
    _accept(monkeypatch)
    r = setup_guide.save_alpaca(KEY, SECRET)
    assert r["saved"] and r["masked"] == "PK…0001"
    assert SECRET not in json.dumps(r) and KEY not in json.dumps(r)
    text = _env_file.read_text()
    assert f"ALPACA_API_KEY={KEY}" in text and f"ALPACA_SECRET_KEY={SECRET}" in text
    assert "FRED_API_KEY=abc" in text and "# my note" in text and "PKOLD" not in text      # other lines kept
    assert stat.S_IMODE(os.stat(_env_file).st_mode) == 0o600
    st = setup_guide.status()
    assert SECRET not in json.dumps(st) and KEY not in json.dumps(st) and st["keys"]["state"] == "ok"


def test_a_key_from_the_environment_gets_a_warning(monkeypatch):
    _accept(monkeypatch)
    monkeypatch.setenv("ALPACA_API_KEY", "PKFROMENV0000000")
    assert "wins over the file" in setup_guide.save_alpaca(KEY, SECRET)["warning"]


def test_optional_keys_are_checked(_env_file):
    assert not setup_guide.save_optional("FRED_API_KEY", "nope")["saved"]
    assert not setup_guide.save_optional("SEC_USER_AGENT", "a\nALPACA_API_KEY=x")["saved"]
    assert not setup_guide.save_optional("ALPACA_API_KEY", KEY)["saved"]             # only the optional ones here
    assert setup_guide.save_optional("FRED_API_KEY", "a" * 32)["saved"]
    assert "FRED_API_KEY=" + "a" * 32 in _env_file.read_text()


def test_status_without_keys_says_none():
    assert setup_guide.status()["keys"]["state"] == "none"


def _post(path, body, token=True, origin=True):
    base = view.ensure_server()
    h = {"Content-Type": "application/json"}
    if token:
        h["X-BotScope-Token"] = console.TOKEN
    if origin:
        h["Origin"] = base
    try:
        r = urlopen(Request(base + path, data=json.dumps(body).encode(), headers=h), timeout=20)
        return r.status, json.loads(r.read())
    except HTTPError as e:
        return e.code, None


def test_setup_routes_need_the_token_and_origin(monkeypatch, _env_file):
    _accept(monkeypatch)
    for path in ("/api/setup/status", "/api/setup/keys", "/api/setup/optional", "/api/setup/import"):
        assert _post(path, {"api_key": KEY, "secret": SECRET}, token=False)[0] == 403
        assert _post(path, {"api_key": KEY, "secret": SECRET}, origin=False)[0] == 403
    assert not _env_file.exists()
    code, r = _post("/api/setup/keys", {"api_key": KEY, "secret": SECRET})
    assert code == 200 and r["saved"] and SECRET not in json.dumps(r)
    assert urlparse(view.ensure_server()).hostname == "127.0.0.1"


def test_key_check_uses_certifi_certificates(monkeypatch):
    """python.org Python on macOS has no root certificates: without certifi every check looked 'offline'."""
    import urllib.request
    seen = {}
    def fake(req, timeout=None, context=None):
        seen["context"] = context
        raise urllib.error.URLError("stop here")
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    setup_guide.check_alpaca(KEY, SECRET)
    assert seen["context"] is not None


def test_other_api_keys_can_be_added_listed_and_removed(_env_file):
    r = setup_guide.save_custom("polygon_api_key", "abc123secretvalue")
    assert r["saved"] and r["name"] == "POLYGON_API_KEY" and "abc123secretvalue" not in json.dumps(r)
    assert [c["name"] for c in setup_guide.custom_keys()] == ["POLYGON_API_KEY"]
    assert "abc123secretvalue" not in json.dumps(setup_guide.status())
    assert stat.S_IMODE(os.stat(_env_file).st_mode) == 0o600
    assert setup_guide.remove_custom("POLYGON_API_KEY")["removed"] and setup_guide.custom_keys() == []


def test_botscope_switches_and_alpaca_keys_can_never_be_set_as_other_keys(_env_file):
    for name in ("BOTSCOPE_LIVE_TRADING", "BOTSCOPE_ACCOUNT", "ALPACA_API_KEY", "ALPACA_SECRET_KEY", "APCA_API_KEY_ID",
                 "PATH", "PYTHONPATH", "DYLD_INSERT_LIBRARIES", "ANTHROPIC_BASE_URL", "x", "BAD-NAME"):
        assert not setup_guide.save_custom(name, "1")["saved"], name
    assert not setup_guide.save_custom("GOOD_KEY", "line1\nBOTSCOPE_LIVE_TRADING=1")["saved"]
    assert not _env_file.exists() or "BOTSCOPE_LIVE_TRADING" not in _env_file.read_text()
    assert not setup_guide.remove_custom("BOTSCOPE_LIVE_TRADING")["removed"]


def test_keys_given_at_plugin_install_are_read(monkeypatch, _env_file):
    """The plugin asks for keys at install (userConfig): the MCP server gets them as env vars, hooks as
    CLAUDE_PLUGIN_OPTION_<NAME>; an unfilled option ("" or a left-over ${user_config.X}) falls back to the .env."""
    from botscope import env
    _env_file.write_text("FRED_API_KEY=fromfile\n")
    monkeypatch.setenv("FRED_API_KEY", "${user_config.FRED_API_KEY}")
    assert env.key("FRED_API_KEY") == "fromfile"
    monkeypatch.setenv("FRED_API_KEY", "")
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_FRED_API_KEY", "fromhook")
    assert env.key("FRED_API_KEY") == "fromhook"
    monkeypatch.setenv("FRED_API_KEY", "fromserver")
    assert env.key("FRED_API_KEY") == "fromserver"
