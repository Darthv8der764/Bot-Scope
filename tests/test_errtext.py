"""Error text the user reads: plain, no doubled quotes."""
from botscope.errtext import say


def test_tool_errors_read_plainly_without_extra_quotes():
    from botscope import server
    out = server._safe(server.view.open_view, "nope")
    assert out["error"].startswith("no bot named 'nope'") and '\\' not in out["error"] and '"' not in out["error"]


def test_say_keeps_other_errors_as_they_are():
    assert say(KeyError("x")) == "x" and say(ValueError("bad day")) == "bad day" and say(KeyError(1, 2)) == "(1, 2)"


def test_alpaca_refusing_the_keys_reads_as_a_keys_message_not_html():
    class APIError(Exception):      # the same name and field as alpaca.common.exceptions.APIError
        status_code = 401
    assert say(APIError("<html><title>401 Authorization Required</title></html>")).startswith("Alpaca didn't accept")


def test_offline_reads_as_couldnt_reach_not_a_connection_pool_dump():
    import requests
    from botscope.errtext import short
    e = requests.ConnectionError("HTTPSConnectionPool(host='data.alpaca.markets', port=443): Max retries exceeded "
                                 "with url: /v2/stocks/bars (Caused by NameResolutionError(...))")
    assert say(e).startswith("Couldn't reach data.alpaca.markets (is this computer online?)")
    assert short(e).startswith("Couldn't reach data.alpaca.markets") and "Max retries" not in short(e)
    assert say(ConnectionError("tests are offline")) == "tests are offline"      # Python's own error keeps its text
