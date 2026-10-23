import re

from botscope import view


def _lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def test_dark_links_are_soft_and_readable():
    js = view.PAGE.with_name("theme.js").read_text()
    colors = set(re.findall(r":where\(a:link, a:visited\) \{ color: (#[0-9a-f]{6})", js))
    assert colors == {"#9fb7e0", "#cdbfe9"}
    for c in colors:                                   # WCAG AA (4.5:1) on the darkest and lightest dark panels
        for bg in ("#121212", "#1b1b1a"):
            assert (_lum(c) + 0.05) / (_lum(bg) + 0.05) >= 4.5
