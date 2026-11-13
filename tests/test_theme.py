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


def _contrast(a: str, b: str) -> float:
    def lum(h):
        f = lambda v: v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4      # noqa: E731
        r, g, b_ = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        return .2126 * f(r) + .7152 * f(g) + .0722 * f(b_)
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + .05) / (lo + .05)


def test_light_mode_gain_and_loss_text_is_readable():
    """Gains, losses and warnings are small text: 4.5:1 on white (light green #1a9e6a was 3.4:1, QA pass 2026-11-12)."""
    import re
    bad, seen = [], 0
    for p in list(WEB.glob("*.html")) + [WEB / "theme.js"]:
        for rule in re.findall(r":root(?:\[data-cb\])?\s*\{([^}]*)\}", p.read_text()):     # the light :root blocks
            for name, hexv in re.findall(r"--(up|down|mid|warn-ink):\s*(#[0-9a-fA-F]{6})", rule):
                seen += 1
                if _contrast(hexv, "#ffffff") < 4.5:
                    bad.append(f"{p.name} --{name} {hexv} {_contrast(hexv, '#ffffff'):.2f}")
    assert seen > 15 and not bad, bad


def test_pages_get_an_icon_not_a_404():
    """Every page's browser asked for /favicon.ico and logged a 404 in the console."""
    r = urlopen(view.ensure_server() + "/favicon.ico")
    assert r.status in (200, 204) and r.headers["Content-Type"] == "image/png"


def test_chart_fits_the_window_on_desktop():
    """The chart stretched to the side panel's height (1700+ px), so the newest candles sat below the window and the
    price scale fit candles nobody could see (QA pass 2026-11-12). On desktop it is one window tall and sticky."""
    import re
    page = (WEB / "bot_view.html").read_text()
    block = re.search(r"@media \(min-width: 761px\) \{[^}]*#chartwrap \{([^}]*)\}", page)
    assert block and "sticky" in block.group(1) and "height: calc(100vh" in block.group(1) and "align-self: start" in block.group(1)


def test_weather_calendar_has_a_color_blind_palette():
    """The weather calendar kept green "trending up" next to red "panic" in color-blind mode (QA pass 2026-11-12)."""
    page = (WEB / "weather.html").read_text()
    assert ":root[data-cb] { --w-up: #0072b2;" in page and "--w-panic: #cc79a7" in page


def test_daily_charts_show_days_not_clock_times():
    """A daily bot's candle read "09-30" (like 9:30 AM) and the crosshair said 00:00 (QA pass 2026-11-12)."""
    page = (WEB / "bot_view.html").read_text()
    assert 'month: "short", day: "numeric"' in page and 'timeVisible: S.bot.timeframe !== "1Day"' in page


def test_clicking_a_candle_brings_the_answer_into_view():
    """On an 800 px window the "Why not here?" answer landed below the fold, so a click looked like nothing happened."""
    page = (WEB / "bot_view.html").read_text()
    body = page.split("function onClick(p) {")[1].split("\n}")[0]
    assert "revealWhy();" in body and 'scrollIntoView({ block: "nearest"' in page.split("function revealWhy()")[1].split("\n}")[0]
    assert "quizAsk(); revealWhy();" in page                  # "Quiz me" asks its questions in that same card


def test_undoing_the_last_veto_clears_the_veto_card():
    """After "Undo veto" on the only veto, the card kept "1 total, 1.88R missed" (QA pass 2026-11-12)."""
    page = (WEB / "bot_view.html").read_text()
    body = page.split("async function loadVetoCard() {")[1].split("\n}")[0]
    assert "if (!v.vetoes) return;" not in body and 'No vetoes yet' in body


def test_demo_badge_never_covers_the_disclaimer_and_phone_dates_fit():
    """On a phone the DEMO DATA badge sat on the end of "...isn't financial advice", and the chart's date box was cut
    to "11/11/2(" (QA pass 2026-11-12)."""
    js = (WEB / "theme.js").read_text()
    assert ".has-demo-badge footer { padding-right: var(--demo-badge-w" in js and 'classList.add("has-demo-badge")' in js
    assert "new ResizeObserver(fit).observe(b)" in js        # Spanish "DATOS DE DEMOSTRACIÓN" is wider than English
    assert "padding-bottom: 44px" in js                       # phones: the badge sits under the text, not beside it
    assert 'header form input[type="date"] { min-width: 9.5em; }' in (WEB / "bot_view.html").read_text()


def test_a_day_without_candles_says_why_over_the_chart():
    """A Saturday or holiday left the chart blank, with the reason only in a small header pill (QA pass 2026-11-12)."""
    page = (WEB / "bot_view.html").read_text()
    assert '$("chartmsg").textContent = S.empty_reason || ""; $("chartmsg").hidden = !S.empty_reason;' in page
