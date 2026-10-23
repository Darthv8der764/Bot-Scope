"""Plain error text for the user. str(KeyError("no bot named 'x'")) adds a second layer of quotes and backslashes
("\"no bot named 'x'\""), so a KeyError's own message is used as is."""


def say(e: BaseException) -> str:
    if isinstance(e, KeyError) and len(e.args) == 1 and isinstance(e.args[0], str):
        return e.args[0]
    return str(e)
