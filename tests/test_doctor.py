"""Doctor: a new user's setup check. Never shows key values."""
from botscope import doctor, env


def test_empty_setup_lists_what_to_fix(tmp_path, monkeypatch):
    for k in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "FRED_API_KEY", "FINNHUB_API_KEY", "SEC_USER_AGENT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("BOTSCOPE_ENV_FILE", str(tmp_path / "none.env"))
    out = doctor.check()
    rows = {r["check"]: r for r in out["checks"]}
    assert not out["ready"] and not rows["Alpaca keys"]["ok"] and "paper" in rows["Alpaca keys"]["fix"]
    assert "fred.stlouisfed.org" in rows["FRED_API_KEY (optional)"]["fix"]


def test_keys_are_never_shown(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("ALPACA_API_KEY=PKSECRETVALUE123\nALPACA_SECRET_KEY=topsecret999\n")
    monkeypatch.setenv("BOTSCOPE_ENV_FILE", str(f))
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    out = doctor.check()
    text = str(out)
    assert "PKSECRETVALUE123" not in text and "topsecret999" not in text
    assert {r["check"]: r for r in out["checks"]}["Alpaca keys"]["detail"] == "set (paper key)"
    assert env.key("ALPACA_API_KEY")       # (the key really was read)


def test_live_key_is_flagged(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("ALPACA_API_KEY=AKLIVE\nALPACA_SECRET_KEY=x\n")
    monkeypatch.setenv("BOTSCOPE_ENV_FILE", str(f))
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    assert not {r["check"]: r for r in doctor.check()["checks"]}["Alpaca keys"]["ok"]


def test_claude_registration_found_by_name_only(tmp_path):
    home, proj = tmp_path / "home", tmp_path / "work" / "bots"
    proj.mkdir(parents=True)
    (home / ".claude").mkdir(parents=True)
    assert doctor._claude_sees_botscope(home, proj) is None
    (tmp_path / "work" / ".mcp.json").write_text('{"mcpServers": {"botscope": {"env": {"ALPACA_API_KEY": "PKHIDDEN"}}}}')
    where = doctor._claude_sees_botscope(home, proj)
    assert where.endswith(".mcp.json") and "PKHIDDEN" not in where
    (home / ".claude.json").write_text('{"mcpServers": {"botscope": {}}}')
    assert "all projects" in doctor._claude_sees_botscope(home, proj)


def test_plugin_install_counts(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text('{"enabledPlugins": {"botscope@botscope": true}}')
    assert doctor._claude_sees_botscope(tmp_path, tmp_path) == "the botscope plugin"


def test_via_mcp_is_always_seen_and_never_blocks_ready():
    rows = {r["check"]: r for r in doctor.check(via_mcp=True)["checks"]}
    assert rows["Claude Code sees BotScope"]["ok"]


def test_hooks_found_in_settings_or_from_the_plugin(tmp_path):
    home, proj = tmp_path / "home", tmp_path / "work"
    (home / ".claude").mkdir(parents=True)
    (proj / ".claude").mkdir(parents=True)
    assert doctor._hooks_set(home, proj) == {"botscope-guard": None, "botscope.checkpoints": None}
    (proj / ".claude" / "settings.local.json").write_text(
        '{"hooks": {"PreToolUse": [{"matcher": "Edit|Write", "hooks": [{"type": "command", '
        '"command": "/x/.venv/bin/python -m botscope.checkpoints"}]}]}}')
    hk = doctor._hooks_set(home, proj)
    assert hk["botscope.checkpoints"].endswith("settings.local.json") and hk["botscope-guard"] is None
    (home / ".claude" / "settings.json").write_text('{"enabledPlugins": {"botscope@botscope": true}}')
    assert set(doctor._hooks_set(home, proj).values()) == {"the botscope plugin"}


def test_missing_hooks_never_block_ready():
    rows = {r["check"]: r for r in doctor.check(via_mcp=True)["checks"]}
    assert "Order guard hook (optional)" in rows and "Auto-checkpoint hook (optional)" in rows


def test_broken_settings_file_named_with_line_never_content(tmp_path):
    home, proj = tmp_path / "home", tmp_path / "work"
    (home / ".claude").mkdir(parents=True)
    (proj / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text('{"ok": true}')
    assert doctor._broken_settings(home, proj) == []
    (proj / ".claude" / "settings.local.json").write_text('{"a": 1}\n{"SECRET_TOKEN": "x"}\n')
    out = doctor._broken_settings(home, proj)
    assert len(out) == 1 and out[0].endswith("settings.local.json (line 2)") and "SECRET" not in out[0]


def test_alert_channels_named_never_their_secrets(monkeypatch):
    hook = "https://discord.com/api/webhooks/123456/SECRETHOOKPART"
    monkeypatch.setenv("NTFY_TOPIC", "very-secret-topic-name-42")      # (tests never read alert keys from .env)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", hook)
    out = doctor.check()
    row = {r["check"]: r for r in out["checks"]}["Alert channels (optional)"]
    assert row["ok"] and row["detail"] == "ntfy, discord on"
    assert "very-secret-topic" not in str(out) and "SECRETHOOKPART" not in str(out)
