"""Shared plumbing for tools/market_data: .env key lookup, HTTPS GET with a file cache, SEC rate limit.
Copied from the private prototype 2026-10-15; personal defaults removed.

Portable on purpose (BotScope can copy the whole folder): standard library only, plus certifi when present.
Keys are read from the environment or the nearest .env and are never printed; error messages drop the URL
because some URLs carry a key."""
import hashlib
import json
import os
import ssl
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE_DIR = Path(os.getenv("MARKET_DATA_CACHE") or HERE.parent.parent / "data" / "market_data_cache")
DEFAULT_UA = "BotScope market_data (information only)"

_sec_lock = threading.Lock()
_sec_last = [0.0]
SEC_MIN_GAP = 0.15                          # ~6.7 requests/sec, under SEC's 10/sec limit


def env_key(name):
    """Key from the environment, else BOTSCOPE_ENV_FILE, else botscope/.env (botscope.env.key)."""
    from botscope.env import key
    return key(name)


WHERE = {"FRED_API_KEY": "free at fred.stlouisfed.org (My Account > API Keys)",
         "FINNHUB_API_KEY": "free at finnhub.io (free plan)"}


def need_key(name):
    """The key, or a plain error that says where to get it free and where to put it."""
    k = env_key(name)
    if not k:
        raise RuntimeError(f"{name} missing: get one {WHERE.get(name, '')}, then add {name}=... to your .env".replace("  ", " "))
    return k


def sec_user_agent():
    """SEC asks every caller to send contact info. Each user sets their own (SEC_USER_AGENT="BotScope you@example.com")."""
    ua = env_key("SEC_USER_AGENT")
    if not ua or "example.com" in ua:       # the .env.example placeholder is not real contact info
        raise RuntimeError("SEC_USER_AGENT missing: SEC requires contact info, set SEC_USER_AGENT in your .env")
    return ua


def _ctx():
    try:
        import certifi                      # python.org Python on macOS ships without root certificates
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def get(url, params=None, ttl=3600, headers=None, raw=False, secret_params=()):
    """GET url (JSON unless raw=True), cached on disk for ttl seconds. secret_params are added to the
    request but left out of the cache key and of any error text."""
    params = dict(params or {})
    public = {k: v for k, v in params.items() if k not in secret_params}
    cache_id = hashlib.sha1(f"{url}?{urllib.parse.urlencode(sorted(public.items()))}".encode()).hexdigest()
    path = CACHE_DIR / f"{cache_id}.{'txt' if raw else 'json'}"
    if ttl and path.exists() and time.time() - path.stat().st_mtime < ttl:
        text = path.read_text()
        return text if raw else json.loads(text)

    hdrs = {"User-Agent": DEFAULT_UA, "Accept-Encoding": "identity"}
    hdrs.update(headers or {})
    if "sec.gov" in urllib.parse.urlparse(url).netloc:
        hdrs["User-Agent"] = sec_user_agent()
        with _sec_lock:
            wait = SEC_MIN_GAP - (time.time() - _sec_last[0])
            if wait > 0:
                time.sleep(wait)
            _sec_last[0] = time.time()
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(full, headers=hdrs), timeout=30, context=_ctx()) as r:
            text = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{urllib.parse.urlparse(url).netloc}{urllib.parse.urlparse(url).path} -> HTTP {e.code}") from None
    except Exception as e:
        raise RuntimeError(f"{urllib.parse.urlparse(url).netloc} request failed: {type(e).__name__}") from None
    data = text if raw else json.loads(text)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return data
