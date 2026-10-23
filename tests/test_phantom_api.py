import json
import urllib.request

from botscope import journal, view


def test_phantom_api_get_and_post(tmp_path):
    base = view.ensure_server()
    f = tmp_path / "c.py"
    f.write_text("x=1\n")
    journal.add("factory_runs", {"run": "r9", "kept": [{"id": "dip", "name": "Dip", "file": str(f)}], "dropped": []})
    req = urllib.request.Request(base + "/api/phantom", data=json.dumps({"run": "r9", "candidates": ["dip"]}).encode(),
                                 headers={"Content-Type": "application/json"})
    assert json.load(urllib.request.urlopen(req))["started"][0]["name"] == "Dip"
    got = json.load(urllib.request.urlopen(base + "/api/phantom"))
    assert got["phantoms"][0]["signals"] == 0
    assert "Phantom test" in (view.PAGE.with_name("factory.js")).read_text()      # Studio's Factory tab code
