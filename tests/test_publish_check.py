import json
import subprocess

import pytest

from botscope import publish_check as pc
from botscope.env import ROOT

REAL_KEPT_HOME = pc.kept_home
PRIVATE_CODE = "\n".join(f"    if bar.close > level_{i} and volume_{i} > avg_volume * {i}:\n        score += weight_{i}"
                         for i in range(8))


def test_scan_finds_each_kind_and_skips_placeholders():
    # all made up, and built here so publish-check finds no key, IP, email, home path, Tailscale host or account in the repo
    fake_key, ip = "PK" + "ABCDEFGHIJKLMNOPQR", ".".join(("192", "168", "4", "20"))
    mail, home, host, acct = "bob.smith" + "@" + "gmail.com", "/Us" + "ers/bob", "mybox.tail1234" + ".ts.net", "PA" + "3XYZ12345"
    text = (f"k = '{fake_key}'\nserver {ip}\nmail {mail}\npath {home}/stuff\n"
            f"host {host}\nacct {acct}\nsafe 127.0.0.1 you@yourmail.com noreply@anthropic.com\n")
    kinds = {h["kind"] for h in pc.scan_text("botscope/x.py", text, {})}
    assert kinds == {"key", "ip address", "email", "home path", "tailscale name", "account number"}
    assert pc.scan_text("README.md", "run on 127.0.0.1, write to you@yourmail.com, see /Users/you/x", {}) == []


def test_private_rules_found_even_renamed():
    priv = {"strategy_names": ["secret_orb"], "code_hashes": [pc.code_hash(PRIVATE_CODE)],
            "rule_fingerprints": sorted(pc.fingerprints(PRIVATE_CODE)), "words": ["MYTICKER"]}
    ported = "class Generic:\n    name = 'Generic dip'\n    def decide(self, bar):\n" + PRIVATE_CODE.replace("score", "points", 0)
    kinds = {h["kind"] for h in pc.scan_text("bots/generic.py", ported, priv)}
    assert "private rules (fingerprint)" in kinds
    assert {h["kind"] for h in pc.scan_text("bots/secret_orb.py", "x = 1\n", priv)} == {"private strategy name"}
    assert pc.scan_text("docs/a.md", "I traded MYTICKER", priv)[0]["kind"] == "private word"
    assert pc.scan_text("bots/clean.py", "name = 'Clean'\nx = 1\n", priv) == []


@pytest.fixture
def repo(tmp_path, monkeypatch):
    r = tmp_path / "repo"
    (r / "bots").mkdir(parents=True)
    (r / "bots" / "clean.py").write_text("name = 'Clean'\n")
    (r / "README.md").write_text("hello\n")
    (r / "QUESTIONS.md").write_text("my own notes\n")
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    monkeypatch.setattr(pc, "ROOT", r)
    monkeypatch.setattr(pc, "PRIVATE_LIST", r / "botscope.private.json")
    monkeypatch.setattr(pc, "kept_home", lambda: set())          # not your real botscope.local.json
    (r / "botscope.private.json").write_text(json.dumps({"strategy_names": ["secret_orb"], "code_hashes": [],
                                                         "rule_fingerprints": [], "words": []}))
    return r


def test_run_passes_clean_and_leaves_out_private_files(repo, tmp_path):
    out = pc.run(str(tmp_path / "exp"))
    assert out["ok"] and out["files"] == 2 and out["left_out"] == 1
    assert not (tmp_path / "exp" / "QUESTIONS.md").exists() and (tmp_path / "exp" / "bots" / "clean.py").exists()
    assert pc.run(str(tmp_path / "exp"))["ok"]                 # re-run replaces its own earlier export


def test_run_fails_loudly_on_a_private_bot(repo, tmp_path):
    (repo / "bots" / "secret_orb.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    out = pc.run(str(tmp_path / "exp"))
    assert out["ok"] is False and out["by_kind"] == {"private strategy name": 1} and out["verdict"].startswith("FAIL")


def test_run_refuses_unsafe_folders(repo, tmp_path):
    other = tmp_path / "mine"
    other.mkdir()
    (other / "keep.txt").write_text("x")
    assert "isn't an earlier export" in pc.run(str(other))["error"] and (other / "keep.txt").exists()
    assert "outside" in pc.run(str(repo / "exp"))["error"]


def test_no_private_list_never_passes(repo, tmp_path):
    (repo / "botscope.private.json").unlink()
    out = pc.run(str(tmp_path / "exp"))
    assert out["ok"] is False and "build_private" in out["verdict"]


def test_private_list_is_git_ignored():
    got = subprocess.run(["git", "check-ignore", "botscope.private.json"], cwd=ROOT, capture_output=True, text=True)
    assert got.returncode == 0


def test_bots_private_never_go_out_and_mentions_are_hits(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "kept_home", REAL_KEPT_HOME)     # the real one this time, in the made-up repo
    (repo / ".gitignore").write_text("bots_private/\nbotscope.private.json\n")
    (repo / "bots_private").mkdir()
    (repo / "bots_private" / "secret_orb.py").write_text("name = 'Secret ORB'\nx = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    out = pc.run(str(tmp_path / "exp"))
    assert out["ok"] and out["kept_home"] == ["bots_private/secret_orb.py"]
    assert not (tmp_path / "exp" / "bots_private").exists()                # git-ignored: never exported
    (repo / "README.md").write_text("try the Secret ORB bot\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    out = pc.run(str(tmp_path / "exp"))
    assert out["ok"] is False and out["by_kind"] == {"names a kept-home bot": 1}


def test_reviewed_images_pinned_by_hash():
    path, data = "docs/screenshots/x.jpg", b"\xff\xd8 a picture"
    pc.REVIEWED_IMAGES[path] = __import__("hashlib").sha256(data).hexdigest()
    try:
        assert pc.check_image(path, data) == []
        assert pc.check_image(path, data + b"!")[0]["kind"] == "image changed since review"
        assert pc.check_image("docs/other.jpg", data)[0]["kind"] == "image changed since review"   # never reviewed
    finally:
        del pc.REVIEWED_IMAGES[path]
    exif = b"\xff\xd8Exif gps"
    pc.REVIEWED_IMAGES[path] = __import__("hashlib").sha256(exif).hexdigest()
    try:
        assert [h["kind"] for h in pc.check_image(path, exif)] == ["image metadata"]
    finally:
        del pc.REVIEWED_IMAGES[path]


def test_reviewed_images_in_the_repo_still_match():
    for path, digest in pc.REVIEWED_IMAGES.items():
        assert pc.check_image(path, (ROOT / path).read_bytes()) == [], path


def test_broken_links_in_the_export_fail(repo, tmp_path):
    (repo / "README.md").write_text("![shot](docs/gone.jpg) [notes](QUESTIONS.md) [web](https://x.org) [top](#a)\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    out = pc.run(str(tmp_path / "exp"))
    assert out["ok"] is False and out["by_kind"] == {"broken link (not exported)": 2}


def _commits(path):
    got = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=path, capture_output=True, text=True, check=True)
    return got.stdout.strip()


def test_make_repo_one_commit_no_remote(repo, tmp_path):
    exp = tmp_path / "exp"
    assert pc.run(str(exp))["ok"]
    out = pc.make_repo(str(exp))
    assert out["ok"] and out["commits"] == 1 and out["remote"] is None and _commits(exp) == "1"
    assert subprocess.run(["git", "remote"], cwd=exp, capture_output=True, text=True).stdout == ""
    tracked = subprocess.run(["git", "ls-files"], cwd=exp, capture_output=True, text=True).stdout.split()
    assert sorted(tracked) == ["README.md", "bots/clean.py"]                       # the export's stamp stays out
    log = subprocess.run(["git", "log", "--format=%an <%ae> %ad"], cwd=exp, capture_output=True, text=True).stdout
    assert log.startswith(f"{pc.PUBLISH_NAME} <{pc.PUBLISH_EMAIL}>") and "+0000" in log
    assert any("git push" in c for c in out["to_publish_later"]) and "decision" in out["decision"]
    assert "already a git repo" in pc.make_repo(str(exp))["error"]                 # only once per fresh export


def test_make_repo_refuses_unless_a_fresh_pass(repo, tmp_path):
    other = tmp_path / "mine"
    other.mkdir()
    assert "isn't a folder publish-check made" in pc.make_repo(str(other))["error"]
    assert not (other / ".git").exists()
    assert "no export" in pc.make_repo(str(tmp_path / "nothing"))["error"]
    (repo / "bots" / "secret_orb.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    exp = tmp_path / "exp"
    assert pc.run(str(exp))["ok"] is False
    assert "didn't PASS" in pc.make_repo(str(exp))["error"] and not (exp / ".git").exists()
    (repo / "bots" / "secret_orb.py").unlink()
    subprocess.run(["git", "rm", "-q", "--cached", "bots/secret_orb.py"], cwd=repo, check=True)
    assert pc.run(str(exp))["ok"]
    (exp / "README.md").write_text("edited after the scan\n")
    assert "changed after the scan" in pc.make_repo(str(exp))["error"] and not (exp / ".git").exists()
