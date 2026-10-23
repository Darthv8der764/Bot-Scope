"""Themes + phone layout: every page loads the shared theme script early, and it never sends anything."""
from pathlib import Path
from urllib.request import urlopen

from botscope import view

WEB = Path(__file__).resolve().parent.parent / "botscope" / "web"


def test_every_page_loads_the_theme_script_in_its_head():
    for page in WEB.glob("*.html"):
        html = page.read_text()
        assert html.index('<script src="/theme.js"></script>') < html.index("</head>"), page.name
        assert 'name="viewport"' in html, page.name


def test_theme_script_served_with_color_blind_palette_and_local_only():
    js = urlopen(view.ensure_server() + "/theme.js").read().decode()
    assert "data-cb" in js and "#0072b2" in js and "localStorage" in js and "fetch(" not in js


def test_chart_page_stacks_on_a_phone():
    assert "@media (max-width: 760px)" in (WEB / "bot_view.html").read_text()


def test_accent_and_stop_buttons_use_the_readable_text_tokens():
    """White on the dark-mode accent (#6d97ee) or the color-blind orange is under 3:1 (QA pass 2026-10-22)."""
    import re
    from pathlib import Path
    web = Path(__file__).resolve().parent.parent / "botscope" / "web"
    bad = []
    for p in web.glob("*.html"):
        for rule in re.findall(r"[^{}]*\{[^}]*\}", p.read_text()):
            if re.search(r"background:\s*var\(--(accent|down)\)", rule) and re.search(r"(?<!-)color:\s*#fff\b", rule):
                bad.append(f"{p.name}: {rule.strip()[:80]}")
    assert not bad, bad
    assert "--on-accent" in (web / "theme.js").read_text() and "botscopeReadable" in (web / "theme.js").read_text()
