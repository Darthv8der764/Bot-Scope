"""The first-run tour: served, skippable, and every step points at something that's really on the page."""
import re
from pathlib import Path
from urllib.request import urlopen

from botscope import view

WEB = Path(__file__).resolve().parent.parent / "botscope" / "web"


def test_tour_script_is_served_and_remembers_locally_only():
    js = urlopen(view.ensure_server() + "/tour.js").read().decode()
    assert "botscopeTour" in js and "localStorage" in js and "Skip tour" in js
    assert "fetch(" not in js                                  # never sends anything anywhere


def test_every_tour_step_points_at_a_real_element():
    for page in ("bot_view.html", "desk.html"):
        html = (WEB / page).read_text()
        assert '<script src="/tour.js"></script>' in html and 'id="tourbtn"' in html
        tour = html[html.index("botscopeTour("):]
        for sel in re.findall(r'el: "([^"]+)"', tour):
            if sel.startswith("#"):
                ok = f'id: "{sel[3:]}"' in html if sel.startswith("#p-") else f'id="{sel[1:]}"' in html
                assert ok, (page, sel)
            else:
                assert sel.lstrip(".") in html, (page, sel)
        assert "financial advice" in tour or "Information only" in tour


def test_tutorial_steps_tick_on_real_actions_only():
    html = (WEB / "bot_view.html").read_text()
    lesson = html[html.index("const STEPS = ["):html.index('<script src="/tour.js">')]
    for k in ("chart", "why", "teach", "veto", "label", "stop"):
        assert f'["{k}",' in lesson
    assert 'p === "/api/veto"' in lesson and "Skip this step" in lesson and "Restart" in lesson
    assert 'id="lessonbtn"' in html and 'id="lesson"' in html


def test_tour_box_uses_the_pages_own_text_and_panel_colors():
    js = (WEB / "tour.js").read_text()
    assert "var(--panel,#fff)" in js and "color:var(--ink,#111)" in js and "--fg" not in js
    for page in ("bot_view.html", "desk.html"):
        html = (WEB / page).read_text()
        assert "--panel:" in html and "--ink:" in html, page          # the tokens the tour relies on exist
