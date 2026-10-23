"""Language switch: Spanish phrases for every page, the honesty warnings translated word for word."""
import re
from pathlib import Path
from urllib.request import urlopen

from botscope import share, view

WEB = Path(__file__).resolve().parent.parent / "botscope" / "web"


def _dict():
    js = (WEB / "i18n.js").read_text()
    return dict(re.findall(r'"([^"]+)":\s*\n?\s*"([^"]*)"', js)), js


def test_every_page_gets_the_switch_through_theme_js():
    assert '"/i18n.js"' in (WEB / "theme.js").read_text()
    assert b"botscopeT" in urlopen(view.ensure_server() + "/i18n.js").read()


def test_honesty_warnings_are_translated_and_nothing_promises():
    es, js = _dict()
    assert es["Not financial advice."] == "No es asesoría financiera."
    assert es["UNTESTED"] == "NO PROBADO" and es["TUNED"] == "AJUSTADO" and es["DEMO DATA"]
    assert "fetch(" not in js and "localStorage" in js
    bad = re.compile(r"(?i)garantiz|sin riesgo|seguro que gan|no puedes perder|% de aciertos")
    assert not [v for v in es.values() if bad.search(v)]


def test_share_page_in_spanish(monkeypatch):
    monkeypatch.setenv("BOTSCOPE_LANG", "es")
    assert share.t("Not financial advice.") == "No es asesoría financiera."
    monkeypatch.setenv("BOTSCOPE_LANG", "en")
    assert share.t("Not financial advice.") == "Not financial advice."
