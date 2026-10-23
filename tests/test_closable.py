"""Every panel and popup can be closed: an x, Esc, and a click outside, and closed panels stay closed until reopened."""
from botscope import view

WEB = view.PAGE.parent


def test_theme_has_the_shared_close_rules():
    js = (WEB / "theme.js").read_text()
    assert 'e.key !== "Escape"' in js and "pointerdown" in js            # Esc + click outside for popups
    assert "botscope-closed:" in js and "data-open" in js                 # remembered per page, reopen strip
    assert 'dataset.outside !== "no"' in js


def test_every_page_loads_theme_js():
    for page in WEB.glob("*.html"):
        assert "theme.js" in page.read_text(), page.name


def test_bot_view_panels_and_popups():
    html = view.PAGE.read_text()
    assert html.count("data-closable") >= 9 and html.count("data-title=") >= 9
    assert '<div id="modal" data-popup' in html and '$("modal").bsClose' in html
    assert 'class="bs-x"' in html                                          # the modal's x
    assert 'id="lesson" hidden data-popup' in html and '$("lesson").bsClose' in html


def test_other_pages():
    assert "data-popup" in (WEB / "label.html").read_text()
    studio = (WEB / "studio.html").read_text()
    assert 'id="welcome"' in studio and "w.bsClose" in studio
    assert 'aria-label="Close the info box"' in (WEB / "map.html").read_text()
    assert 'class="hbtn"' in (WEB / "desk.html").read_text()               # desk panels already close + reopen
