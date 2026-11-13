"""Plain error text for the user. str(KeyError("no bot named 'x'")) adds a second layer of quotes and backslashes
("\"no bot named 'x'\""), so a KeyError's own message is used as is. Alpaca refusing the keys answers with a raw
"401 Authorization Required" web page; that reads as one plain sentence instead."""


KEYS_REJECTED = ("Alpaca didn't accept your saved keys, so there's no market data. Make new Paper keys and paste them "
                 "into Get started, step 2.")


class KeysRejected(RuntimeError):
    """Alpaca answered 401/403: the saved keys don't work, so every market-data call will fail the same way. A
    RuntimeError, so loops over symbols stop and say so (like missing keys) instead of listing "no data" per symbol."""

    def __init__(self, msg: str = KEYS_REJECTED):
        super().__init__(msg)


def keys_rejected(e: BaseException | None) -> bool:
    """True when e (or what caused it) is Alpaca refusing the keys."""
    seen = 0
    while e is not None and seen < 10:
        if isinstance(e, KeysRejected):
            return True
        if type(e).__name__ == "APIError" and getattr(e, "status_code", None) in (401, 403):
            return True
        e, seen = e.__cause__ or e.__context__, seen + 1
    return False


def unreachable(e: BaseException | None) -> str | None:
    """"Couldn't reach data.alpaca.markets ..." when e (or its cause) is a dropped or timed-out connection from the
    requests library (what Alpaca's SDK uses), instead of its "HTTPSConnectionPool(...): Max retries exceeded" text."""
    import re
    seen = 0
    while e is not None and seen < 10:
        if type(e).__module__.startswith("requests") and type(e).__name__ in (
                "ConnectionError", "ConnectTimeout", "ReadTimeout", "Timeout", "SSLError", "ProxyError"):
            req = getattr(e, "request", None)
            m = re.search(r"https?://([^/:]+)", getattr(req, "url", "") or "") or re.search(r"host='([^']+)'", str(e))
            return (f"Couldn't reach {m.group(1) if m else 'the market-data service'} (is this computer online?). "
                    "Try again in a minute.")
        e, seen = e.__cause__ or e.__context__, seen + 1
    return None


def say(e: BaseException) -> str:
    if keys_rejected(e):
        return KEYS_REJECTED
    if (gone := unreachable(e)):
        return gone
    if isinstance(e, KeyError) and len(e.args) == 1 and isinstance(e.args[0], str):
        return e.args[0]
    return str(e)


def short(e: BaseException, n: int = 120) -> str:
    """'APIError: first n characters' for lists of problems; the plain keys sentence when Alpaca refused the keys."""
    return KEYS_REJECTED if keys_rejected(e) else unreachable(e) or f"{type(e).__name__}: {str(e)[:n]}"
