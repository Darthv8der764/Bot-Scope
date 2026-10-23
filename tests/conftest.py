"""Every test gets its own empty journal folder, so no test can write to the real data/journal."""
import pytest


@pytest.fixture(autouse=True)
def _isolated_journal(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTSCOPE_JOURNAL_DIR", str(tmp_path / "journal"))


@pytest.fixture(autouse=True)
def _no_spy_download(monkeypatch):
    """The 'beat just holding?' SPY download never reaches the network in tests (tests pass their own fetch)."""
    from botscope import benchmark

    def offline(*a):
        raise ConnectionError("tests are offline")
    monkeypatch.setattr(benchmark, "_fetch", offline)


@pytest.fixture(autouse=True)
def _no_phone_alerts(monkeypatch):
    """No test ever pushes to a real ntfy topic, even if the developer has one set in .env."""
    import os
    from botscope import alerts
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.delenv("NTFY_SERVER", raising=False)
    for k in ("DISCORD_WEBHOOK_URL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(alerts, "key", lambda name: os.environ.get(name, "").strip())


@pytest.fixture(autouse=True)
def _real_data_mode(monkeypatch):
    """Tests run in real-data mode (demo mode is on whenever keys are missing); demo tests turn it on themselves."""
    monkeypatch.setenv("BOTSCOPE_DEMO", "0")
    monkeypatch.setenv("BOTSCOPE_DEMO_CRYPTO", "made-up")    # demo tests never reach the network for crypto


@pytest.fixture(autouse=True)
def _dev_checkout_paths(tmp_path, monkeypatch):
    """Tests see a developer checkout (never the plugin-mode ~/.botscope), even when run from inside a plugin session;
    plugin-mode tests turn it on themselves, with a made-up home."""
    from botscope import loader, userdata
    monkeypatch.setattr(loader, "PRIVATE", tmp_path / "no-bots-private")   # your own bots_private/ never joins a test
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.setenv("BOTSCOPE_PLUGIN_MODE", "0")
    monkeypatch.setenv("BOTSCOPE_HOME", str(tmp_path / "botscope-home"))
    monkeypatch.setattr(userdata, "_done", False)


@pytest.fixture
def relabel(monkeypatch):
    """relabel("bot_id", status="failed", tuned_on=(...)): that bot's labels changed for this test only. The example
    bots are honestly untested and untuned, so tests of tuned or failed bots set those labels here, not in the files."""
    from botscope import loader
    real, changes = loader.load_all, {}

    def patched():
        bots, errors = real()
        for bid, attrs in changes.items():
            if bid in bots:
                bots[bid] = type(bots[bid].__name__, (bots[bid],), {**attrs, "__module__": bots[bid].__module__})
        return bots, errors

    def apply(bot_id, **attrs):
        changes.setdefault(bot_id, {}).update(attrs)
        monkeypatch.setattr(loader, "load_all", patched)
        return loader.get(bot_id)
    return apply
