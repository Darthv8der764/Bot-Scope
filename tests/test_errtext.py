"""Error text the user reads: plain, no doubled quotes."""
from botscope.errtext import say


def test_tool_errors_read_plainly_without_extra_quotes():
    from botscope import server
    out = server._safe(server.view.open_view, "nope")
    assert out["error"].startswith("no bot named 'nope'") and '\\' not in out["error"] and '"' not in out["error"]


def test_say_keeps_other_errors_as_they_are():
    assert say(KeyError("x")) == "x" and say(ValueError("bad day")) == "bad day" and say(KeyError(1, 2)) == "(1, 2)"
