"""Alerts through your own free ntfy topic (ntfy.sh, or your own ntfy server), Discord webhook or Telegram bot.

Off until you set NTFY_TOPIC in your .env. Pick a long, hard-to-guess topic name: anyone who knows it can read it.
Alerts carry bot names and results in R only: never keys, account numbers or dollar balances. A failed send never
stops anything else. Install the free ntfy app and subscribe to the same topic.
"""
from __future__ import annotations

import re
from urllib.request import Request, urlopen

from .env import key

DEFAULT_SERVER = "https://ntfy.sh"
_TOPIC = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_SECRETS = re.compile(r"(PK|AK|SK)[A-Z0-9]{12,}|\$\s?\d[\d,]*(\.\d+)?")   # key-like strings and dollar amounts


def config() -> dict:
    topic, server = key("NTFY_TOPIC"), (key("NTFY_SERVER") or DEFAULT_SERVER).rstrip("/")
    if not topic:
        return {"on": False, "why": "set NTFY_TOPIC=<a long random name> in your .env to turn phone alerts on"}
    if not _TOPIC.match(topic):
        return {"on": False, "why": "NTFY_TOPIC must be 8-64 letters, numbers, - or _ (longer is safer)"}
    if not server.startswith("https://"):
        return {"on": False, "why": "NTFY_SERVER must start with https://"}
    return {"on": True, "server": server, "topic": topic}


def clean(text: str) -> str:
    return _SECRETS.sub("[hidden]", text)[:400]


_DISCORD = re.compile(r"^https://(discord\.com|discordapp\.com)/api/webhooks/\d+/[A-Za-z0-9_-]+$")
_TG_TOKEN = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")
_TG_CHAT = re.compile(r"^(-?\d{3,}|@[A-Za-z0-9_]{5,})$")


def channels() -> dict:
    """Which alert channels are on (names only, never the topic, webhook or token)."""
    d, t, c = key("DISCORD_WEBHOOK_URL"), key("TELEGRAM_BOT_TOKEN"), key("TELEGRAM_CHAT_ID")
    return {"ntfy": config()["on"],
            "discord": bool(d and _DISCORD.match(d)),
            "telegram": bool(t and c and _TG_TOKEN.match(t) and _TG_CHAT.match(c))}


def _json(url: str, body: dict) -> Request:
    import json
    return Request(url, data=json.dumps(body).encode(), method="POST",
                   headers={"Content-Type": "application/json", "User-Agent": "BotScope"})


def _post_default(r):
    from .market_data import _http as h
    return urlopen(r, timeout=8, context=h._ctx()).status


def send(title: str, message: str, tags: str = "chart_with_upwards_trend", post=None, demo_ok: bool = False) -> dict:
    """Send to every channel that's on: ntfy (NTFY_TOPIC), Discord (DISCORD_WEBHOOK_URL), Telegram
    (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID), all from your own .env. A failed channel never stops the others.
    In demo mode nothing is sent (made-up prices must never reach a phone as if they were real), except messages
    with no prices in them that pass demo_ok=True (the phone test, the STOP notice)."""
    from . import demo
    if demo.active() and not demo_ok:
        return {"sent": False, "why": "demo mode: results on made-up prices are never sent to your phone"}
    post = post or _post_default
    title, message = clean(title)[:120], clean(message)
    on, results = channels(), {}
    reqs = []
    c = config()
    if c["on"]:
        reqs.append(("ntfy", Request(f"{c['server']}/{c['topic']}", data=message.encode(), method="POST",
                                     headers={"Title": title, "Tags": tags})))
    if on["discord"]:
        reqs.append(("discord", _json(key("DISCORD_WEBHOOK_URL"), {"content": f"**{title}**\n{message}"[:1900]})))
    if on["telegram"]:
        reqs.append(("telegram", _json(f"https://api.telegram.org/bot{key('TELEGRAM_BOT_TOKEN')}/sendMessage",
                                       {"chat_id": key("TELEGRAM_CHAT_ID"), "text": f"{title}\n{message}"})))
    if not reqs:
        return {"sent": False, "why": c["why"] + " (or DISCORD_WEBHOOK_URL, or TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)"}
    for name, req in reqs:
        try:
            post(req)
            results[name] = "sent"
        except Exception as e:
            results[name] = f"didn't answer ({type(e).__name__})"
    ok = [n for n, r in results.items() if r == "sent"]
    out = {"sent": bool(ok), "channels": results}
    if ok:
        out["to"] = "your " + " + ".join({"ntfy": "ntfy topic", "discord": "Discord webhook", "telegram": "Telegram chat"}[n] for n in ok)
    else:
        out["why"] = "no channel answered; nothing else was affected"
    return out
