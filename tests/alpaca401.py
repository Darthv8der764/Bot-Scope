"""A fake Alpaca that refuses the keys (HTTP 401, the HTML page Alpaca really sends), with no network at all."""
import requests

PAGE = "<html><head><title>401 Authorization Required</title></head><body><center><h1>401 Authorization Required</h1></center></body></html>"


def refuse(monkeypatch, tmp_path):
    """Real-data mode with made-up paper keys; every Alpaca request answers 401, anything else is offline."""
    from botscope import data
    from botscope.market_data import _http
    monkeypatch.setenv("BOTSCOPE_ENV_FILE", str(tmp_path / "none.env"))
    monkeypatch.setenv("ALPACA_API_KEY", "PKFAKEFAKEFAKE")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "fakesecret")
    monkeypatch.setattr(data, "CACHE", tmp_path / "cache")          # no cached bars hide the refusal

    def offline(*a, **k):
        raise ConnectionError("tests are offline")
    monkeypatch.setattr(_http, "get", offline)                        # calendars, FRED, Kalshi: offline too
    calls = []

    def request(self, method, url, *a, **k):
        calls.append(url)
        if "alpaca" not in url:
            raise requests.ConnectionError("tests are offline")
        r = requests.Response()
        r.status_code, r._content, r.url = 401, PAGE.encode(), url
        r.headers["Content-Type"] = "text/html"
        r.request = requests.Request(method, url).prepare()
        return r
    monkeypatch.setattr(requests.Session, "request", request)
    return calls
