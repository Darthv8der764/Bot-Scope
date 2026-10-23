"""Keys come from the user's own computer only: the environment, else BOTSCOPE_ENV_FILE, else botscope/.env, else
~/.botscope/.env (the place that survives plugin updates).
Values are never printed or logged."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


HOME_ENV = Path("~/.botscope/.env")


def _env_file() -> Path:
    if os.getenv("BOTSCOPE_ENV_FILE"):
        return Path(os.path.expanduser(os.environ["BOTSCOPE_ENV_FILE"]))
    return ROOT / ".env" if (ROOT / ".env").is_file() else HOME_ENV.expanduser()


def key(name: str) -> str:
    if os.getenv(name):
        return os.environ[name].strip()
    f = _env_file()
    if f.is_file():
        for line in f.read_text().splitlines():
            if line.strip().startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def demo_mode() -> bool:
    """Demo mode = made-up prices, zero keys (see demo.py). On when BOTSCOPE_DEMO is 1/true/on, off when it is
    0/false/off, and otherwise on exactly when no Alpaca keys are found, so a new user can try everything at once."""
    v = key("BOTSCOPE_DEMO").lower()
    if v in ("1", "true", "on", "yes"):
        return True
    if v in ("0", "false", "off", "no"):
        return False
    return not (key("ALPACA_API_KEY") and key("ALPACA_SECRET_KEY"))


def alpaca_keys() -> tuple[str, str]:
    k, s = key("ALPACA_API_KEY"), key("ALPACA_SECRET_KEY")
    if not (k and s):
        raise RuntimeError("Alpaca paper keys missing: put ALPACA_API_KEY and ALPACA_SECRET_KEY in ~/.botscope/.env "
                           "(or botscope/.env; see .env.example)")
    return k, s
