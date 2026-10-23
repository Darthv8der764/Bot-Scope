from botscope import alerts


def test_off_until_a_topic_is_set():
    r = alerts.send("t", "m", post=lambda req: 1 / 0)
    assert r["sent"] is False and "NTFY_TOPIC" in r["why"]


def test_sends_to_own_topic_and_hides_secrets(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "my-long-secret-topic-123")
    got = {}
    fake_key = "PK" + "ABCDEFGHIJKLMNOP"                 # built here so the repo's leak scan doesn't flag the test
    r = alerts.send("Day done", f"made $1,234.50 with key {fake_key}", post=lambda req: got.update(
        url=req.full_url, body=req.data.decode(), title=req.headers["Title"]))
    assert r["sent"] and r["to"] == "your ntfy topic" and r["channels"] == {"ntfy": "sent"}
    assert got["url"] == "https://ntfy.sh/my-long-secret-topic-123"
    assert "1,234" not in got["body"] and "PKABC" not in got["body"] and "[hidden]" in got["body"]


def test_bad_topic_or_server_refused_and_failures_are_quiet(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "short")
    assert "8-64" in alerts.send("t", "m")["why"]
    monkeypatch.setenv("NTFY_TOPIC", "a-good-long-topic")
    monkeypatch.setenv("NTFY_SERVER", "http://plain.example")
    assert "https" in alerts.send("t", "m")["why"]
    monkeypatch.setenv("NTFY_SERVER", "https://ntfy.sh")
    def boom(req):
        raise TimeoutError()
    assert alerts.send("t", "m", post=boom)["sent"] is False


def test_discord_and_telegram_from_env_never_echo_secrets(monkeypatch):
    import json
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/123456/abcDEF_ghi-jkl")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "12345678:" + "A" * 35)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-1001234")
    sent = []
    r = alerts.send("NVDA alert", "NVDA broke yesterday's high, made $50", post=lambda req: sent.append(req))
    assert r["sent"] and set(r["channels"]) == {"discord", "telegram"}
    assert "webhooks" not in json.dumps(r) and "AAAA" not in json.dumps(r)
    d, t = (json.loads(x.data) for x in sent)
    assert d["content"].startswith("**NVDA alert**") and "$50" not in d["content"]
    assert t["chat_id"] == "-1001234" and sent[1].full_url.endswith("/sendMessage")


def test_bad_webhook_is_off_and_one_failure_does_not_stop_the_others(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://evil.example/hook")
    assert alerts.channels()["discord"] is False
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/123456/abc")
    monkeypatch.setenv("NTFY_TOPIC", "a-good-long-topic")
    def post(req):
        if "ntfy" in req.full_url:
            raise OSError("down")
    r = alerts.send("t", "m", post=post)
    assert r["sent"] and r["channels"]["discord"] == "sent" and "didn't answer" in r["channels"]["ntfy"]


def test_demo_mode_never_sends_made_up_results(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "botscope-test-topic-123")
    monkeypatch.setenv("BOTSCOPE_DEMO", "1")
    sent = []
    out = alerts.send("BotScope alert: BTC/USD", "BTC/USD goes below 50000: 903.11", post=sent.append)
    assert out == {"sent": False, "why": "demo mode: results on made-up prices are never sent to your phone"} and not sent
    assert alerts.send("BotScope test", "phone alerts work", post=sent.append, demo_ok=True)["sent"] and len(sent) == 1
