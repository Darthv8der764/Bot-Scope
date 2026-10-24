"""Get started: the newcomer's setup, step by step, with a live status for each step (Studio's "Get started" tab).

Steps: try it (demo), real market data (free Alpaca PAPER keys), your bots, Claude inside Studio (optional), extra
market data (optional keys). Keys are typed into the user's own Studio page and written to their own .env on this
computer (readable only by them). They are never shown back (only "PK…AB12"), never logged, never sent anywhere but
Alpaca's own paper API to check they work. Only PAPER keys are accepted: a live key is refused.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import env, loader

PAPER_ACCOUNT_URL = "https://paper-api.alpaca.markets/v2/account"
OPTIONAL = {   # name: (what it unlocks, where to get it, check)
    "FRED_API_KEY": ("economy panels and the economic calendar on the Desk", "https://fred.stlouisfed.org/docs/api/api_key.html",
                     re.compile(r"[a-f0-9]{32}")),
    "FINNHUB_API_KEY": ("earnings dates and analyst views on the Desk", "https://finnhub.io/register",
                        re.compile(r"[A-Za-z0-9]{10,64}")),
    "SEC_USER_AGENT": ("insider trades on the Desk (the SEC asks for your name and email, nothing to sign up for)",
                       "https://www.sec.gov/os/accessing-edgar-data", re.compile(r"[^\r\n<>]{5,120}")),
}
_cache: dict = {}


def mask(k: str) -> str:
    return f"{k[:2]}…{k[-4:]}" if len(k) > 8 else "…"


def env_file() -> Path:
    """The .env BotScope reads (and so the one to write)."""
    return env._env_file().expanduser()


def shown(p: Path) -> str:
    """A path as people read it: ~ for the home folder."""
    return str(p).replace(str(Path.home()), "~", 1)


def check_alpaca(api_key: str, secret: str, timeout: float = 10) -> dict:
    """Read-only check of a key pair against Alpaca's PAPER account API: {ok, why}. Nothing is placed or changed."""
    req = urllib.request.Request(PAPER_ACCOUNT_URL, headers={"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret,
                                                             "User-Agent": "BotScope setup check"})
    try:
        from .market_data._http import _ctx         # certifi: python.org Python on macOS has no root certificates
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
            acct = json.loads(r.read() or b"{}")
        return {"ok": True, "why": "Alpaca accepted the keys (paper account)", "status": acct.get("status")}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"ok": False, "why": "Alpaca didn't accept these keys. Check you copied both, from your PAPER "
                                        "account (they may also have been regenerated since)."}
        return {"ok": False, "why": f"Alpaca answered {e.code}; try again in a minute"}
    except (urllib.error.URLError, TimeoutError, OSError):
        return {"ok": False, "why": "couldn't reach Alpaca: are you online?", "offline": True}


def keys_status(fresh: bool = False) -> dict:
    k, s = env.key("ALPACA_API_KEY"), env.key("ALPACA_SECRET_KEY")
    if not (k and s):
        return {"state": "none", "file": shown(env_file())}
    if not k.startswith("PK"):
        return {"state": "live_key", "masked": mask(k), "why": "this isn't a paper key (paper keys start with PK)"}
    hit = _cache.get("alpaca")
    if fresh or not hit or hit[0] != (k, s) or time.time() - hit[1] > 300:
        _cache["alpaca"] = ((k, s), time.time(), check_alpaca(k, s))
    got = _cache["alpaca"][2]
    state = "ok" if got["ok"] else "offline" if got.get("offline") else "rejected"
    return {"state": state, "masked": mask(k), "why": got["why"], "file": shown(env_file()),
            "from_environment": bool(os.getenv("ALPACA_API_KEY"))}


def claude_status() -> dict:
    exe = shutil.which("claude")
    if not exe:
        return {"found": False, "logged_in": False}
    from .console import _env
    try:
        out = subprocess.run([exe, "auth", "status"], capture_output=True, text=True, timeout=15, env=_env(),
                             stdin=subprocess.DEVNULL)
        logged = bool(json.loads(out.stdout or "{}").get("loggedIn"))
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        logged = None                               # unknown: the page says how to check
    return {"found": True, "logged_in": logged}


def status(fresh: bool = False) -> dict:
    from . import console, imports
    keys = keys_status(fresh)
    bots, _ = loader.load_all()
    imported = imports.summary()
    steps = {"try": True, "keys": keys["state"] == "ok", "bots": bool(imported["bots"]),
             "claude": console.STATE["on"] and bool(claude_status().get("logged_in")),
             "extras": all(env.key(n) for n in OPTIONAL)}
    return {"keys": keys, "claude": claude_status(), "console_on": console.STATE["on"], "terminal": console.terminal_allowed(),
            "bots": {"count": len(bots), "folder": str(loader.bots_dir()), "imported": len(imported["bots"])},
            "optional": {n: {"set": bool(env.key(n)), "unlocks": u, "where": w} for n, (u, w, _) in OPTIONAL.items()},
            "custom": custom_keys(), "steps": steps, "done": sum(steps.values()), "total": len(steps)}


def _write_env(updates: dict[str, str]) -> Path:
    """Set some lines in the .env (keeps every other line), readable only by you."""
    p = env_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = p.read_text().splitlines() if p.is_file() else []
    seen = set()
    for i, line in enumerate(lines):
        name = line.split("=", 1)[0].strip()
        if name in updates:
            lines[i] = f"{name}={updates[name]}"
            seen.add(name)
    lines += [f"{n}={v}" for n, v in updates.items() if n not in seen]
    tmp = p.with_name(p.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, p)
    os.chmod(p, 0o600)
    return p


def save_alpaca(api_key: str, secret: str) -> dict:
    """Check the pair with Alpaca first; save only if Alpaca accepts it. Paper keys only."""
    api_key, secret = (api_key or "").strip(), (secret or "").strip()
    if api_key.startswith("AK"):
        return {"saved": False, "why": "That's a LIVE money key (it starts with AK). BotScope is paper only: switch "
                                       "to your Paper account on alpaca.markets and make keys there (they start with PK)."}
    if not re.fullmatch(r"PK[A-Z0-9]{10,40}", api_key):
        return {"saved": False, "why": "The Key ID doesn't look right: paper Key IDs start with PK, letters and digits only."}
    if not re.fullmatch(r"[A-Za-z0-9/+=]{20,100}", secret):
        return {"saved": False, "why": "The Secret Key doesn't look right: copy the whole secret (about 40 characters)."}
    got = check_alpaca(api_key, secret)
    if not got["ok"]:
        return {"saved": False, "why": got["why"]}
    p = _write_env({"ALPACA_API_KEY": api_key, "ALPACA_SECRET_KEY": secret})
    _cache.pop("alpaca", None)
    out = {"saved": True, "masked": mask(api_key), "file": shown(p),
           "next": "Reload Studio: the DEMO badge goes away and real market data loads."}
    if os.getenv("ALPACA_API_KEY"):
        out["warning"] = ("Your environment also sets ALPACA_API_KEY, and that one wins over the file. Remove it "
                          "(or update it too) for these keys to be used.")
    return out


def save_optional(name: str, value: str) -> dict:
    if name not in OPTIONAL:
        return {"saved": False, "why": f"unknown setting; one of {', '.join(OPTIONAL)}"}
    value = (value or "").strip()
    if not OPTIONAL[name][2].fullmatch(value):
        return {"saved": False, "why": f"that doesn't look like a {name}"}
    p = _write_env({name: value})
    return {"saved": True, "name": name, "file": shown(p), "next": "Reload the Desk to see the new panels."}


# ---------- other API keys (any service the user wants; Claude helps wire it in) ----------
_RESERVED = re.compile(r"(ALPACA_|BOTSCOPE_|APCA_|CLAUDE|ANTHROPIC_|PYTHON|DYLD_|LD_)|(PATH|HOME|SHELL|USER|TERM|LANG)$")


def custom_keys() -> list[dict]:
    """Other keys saved in your .env (names and a masked value only), not BotScope's own settings."""
    p = env_file()
    out = []
    for line in (p.read_text().splitlines() if p.is_file() else []):
        name, _, value = line.partition("=")
        name = name.strip()
        if name and not name.startswith("#") and value and name not in OPTIONAL and not _RESERVED.match(name):
            out.append({"name": name, "masked": mask(value.strip())})
    return out


def save_custom(name: str, value: str) -> dict:
    """Save another service's key under your own name for it (e.g. POLYGON_API_KEY). BotScope's own switches
    (BOTSCOPE_*, like the live-trading lock) and the Alpaca keys can never be set here."""
    name, value = (name or "").strip().upper(), (value or "").strip()
    if name in OPTIONAL:
        return save_optional(name, value)
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,40}", name):
        return {"saved": False, "why": "use a name like POLYGON_API_KEY: capital letters, digits and _ only"}
    if _RESERVED.match(name):
        return {"saved": False, "why": f"{name} is one of BotScope's own settings or a system name: it can't be set "
                                       "here (Alpaca keys have their own checked step above)"}
    if not re.fullmatch(r"[^\r\n]{1,500}", value):
        return {"saved": False, "why": "paste the key on one line (500 characters at most)"}
    p = _write_env({name: value})
    return {"saved": True, "name": name, "masked": mask(value), "file": shown(p),
            "next": f'Ask Claude to use it, e.g. "use my {name} to add a Desk panel for ..." (Claude writes the '
                    "code in BotScope; nothing uses the key until that code exists)."}


def remove_custom(name: str) -> dict:
    name = (name or "").strip().upper()
    if name in OPTIONAL or _RESERVED.match(name) or not re.fullmatch(r"[A-Z][A-Z0-9_]{2,40}", name):
        return {"removed": False, "why": "only keys added under Other API keys can be removed here"}
    p = env_file()
    lines = p.read_text().splitlines() if p.is_file() else []
    keep = [l for l in lines if l.partition("=")[0].strip() != name]
    if len(keep) == len(lines):
        return {"removed": False, "why": f"no {name} saved"}
    tmp = p.with_name(p.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(keep) + "\n")
    os.replace(tmp, p)
    return {"removed": True, "name": name}


def import_alpaca() -> dict:
    """Get started's "bring your bots" button: the read-only Alpaca import (filled orders only, nothing traded)."""
    from . import imports
    if keys_status()["state"] != "ok":
        return {"error": "add working paper keys first (step 2)"}
    out = imports.from_alpaca("alpaca", 90, None, None)
    return {k: out.get(k) for k in ("bots", "trades", "source", "note")}
