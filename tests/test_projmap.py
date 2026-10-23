"""The project map reads the code, git history and the journal; nothing else."""
import json
from pathlib import Path
from urllib.request import urlopen

from botscope import projmap, view


def test_modules_graph():
    m = projmap.modules()
    ids = {n["id"] for n in m["nodes"]}
    assert {"server", "backtest", "projmap", "cli"} <= ids and "__init__" not in ids
    assert {"source": "arena", "target": "backtest"} in m["links"]
    tools = {t for n in m["nodes"] for t in n["tools"]}
    assert {"run_backtest", "bot_arena", "project_map", "stop_everything"} <= tools
    by = {n["id"]: n for n in m["nodes"]}
    assert "luck_meter" in by["luck"]["tools"] and "stop_everything" in by["guard"]["tools"]


def test_bot_family_has_versions_and_latest_results():
    fam = {b["id"]: b for b in projmap.bot_family()}
    v = fam["first_hour_breakout"]["versions"]
    assert v and v[0]["version"] == "1.0" and "confidence" in v[-1] and "confidence" not in v[0] or len(v) == 1


def test_page_and_route():
    html = (Path(view.__file__).parent / "web" / "map.html").read_text()
    for bit in ('id="t-bots"', 'id="play"', 'id="shape"', 'id="edges"', "/api/map", "botscope-map-look-v1"):
        assert bit in html
    out = json.loads(urlopen(view.ensure_server() + "/api/map").read())
    assert out["project"]["nodes"] and out["bots"]


def test_family_tree_is_a_live_draggable_graph():
    from botscope import view
    html = view.PAGE.with_name("map.html").read_text()
    assert "pointerdown" in html and "requestAnimationFrame" in html and "n.pinned = true" in html   # drag, live, stays put
    assert ".node:focus { outline: none; }" in html                      # no browser focus ring on click
    assert "pick(null)" in html and 'e.key === "Escape"' in html          # click empty space / Esc closes the info
