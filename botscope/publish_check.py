"""publish-check: before BotScope ever goes public, build a clean export from an allowlist and scan it.

Only the outline goes out: the framework, the bot format, tools, pages, skills, docs and neutral example bots. Never
the user's own data (journals, vetoes, imports, shadow/phantom logs, factory results, the local adapter config, .env,
caches) and never a strategy that is the user's own or was ported from one.

The export is copied from git-tracked files that match ALLOW and not DENY into a separate folder, then scanned for
personal info (keys, IPs, emails, home paths, Tailscale names, account numbers) and compared with a git-ignored
private list (`botscope.private.json`): strategy names, code hashes and rule fingerprints of the user's own
strategies. The private list holds only names and hashes, never code. Any hit fails loudly. Nothing is published:
going public still needs the user's (and a parent's) go-ahead.

Your own bots belong in bots_private/ (git-ignored; the loader reads it like bots/, so your Studio keeps working). They
are never tracked, so never exported, and any exported file that still names one of them (its file name or its
display name) is a hit.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .env import ROOT
from .userdata import place

PRIVATE_LIST = place(ROOT / "botscope.private.json", "botscope.private.json")
DEFAULT_OUT = Path("~/.botscope/publish-export").expanduser()
MARKER = ".botscope-export"
ALLOW = ("botscope/*.py", "botscope/web/*", "botscope/costs.json", "botscope/market_data/*.py", "bots/*.py",
         "skills/*", "skills/*/*", ".claude-plugin/*", "docs/*.md", "tests/*.py", "README.md", "CONTRIBUTING.md",
         "pyproject.toml", ".env.example", ".gitignore", "LICENSE")
DENY = ("QUESTIONS.md", "ROADMAP.md", "EXPERIMENTS.md", "factory/*", "reports/*", "data/*", "botscope.local.json",
        "botscope.private.json", ".env", ".env.*", "uv.lock", "LICENSE.draft")
SHINGLE = 6                        # consecutive meaningful code lines that make one rule fingerprint
# Images can't be scanned like text, so only these go out: each was looked at by a person (demo data, example bots
# only, no account, no names, no metadata beyond a colour profile) and is pinned by its sha256. A changed image no
# longer matches and fails the check until someone looks at it again and updates its hash here. docs/bot_view.jpg and
# docs/replay.jpg are left out on purpose: they show a private strategy.
REVIEWED_IMAGES = {
    "docs/screenshots/studio-bot-view.jpg": "e5fef55e3e2cefb7e1199e69944b0ec21996ce9761d9ef884045734cb0726342",
    "docs/screenshots/studio-desk.jpg": "378ecff97de217951056c1c073996ca7e1b0e7c82488f4797ca4561ac735e72c",
    "docs/screenshots/studio-factory.jpg": "c782b5048898c6c256e286b204ff7eaa891a79257a4990881ba94b14e8dd2fb8",
    "docs/screenshots/studio-factory-phone.jpg": "a374701c41a7a65cb32e72b2a55c6c9cad3ddd3324a1b2924567410f2b183c78",
}
_IMAGE_META = (b"Exif", b"xmpmeta", b"tEXt", b"iTXt", b"zTXt")    # camera/GPS/author blocks: none allowed
_LINK = re.compile(r"""\]\(([^)\s]+)[^)]*\)|\bsrc=["']([^"']+)["']""")
PUBLISH_NAME = "BotScope contributors"                            # the one commit's author: never your own name
PUBLISH_EMAIL = "noreply@example.com"

_PATTERNS = [
    ("key", re.compile(r"\b(?:AK|PK|CK)[A-Z0-9]{16,}\b")),                                   # Alpaca key ids
    ("key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("key", re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[=:]\s*['\"]?[A-Za-z0-9/+_-]{20,}")),
    ("ip address", re.compile(r"\b(?!127\.0\.0\.1\b)(?!0\.0\.0\.0\b)(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("email", re.compile(r"\b(?!(?:you|your|name|user|someone|noreply)@)[A-Za-z0-9._%+-]+@(?!example\.(?:com|org)\b)(?!anthropic\.com\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("home path", re.compile(r"(?:/Users/|/home/)(?!you\b|me\b|name\b|USER\b|\$)[A-Za-z0-9._-]+|C:\\Users\\[A-Za-z0-9._-]+")),
    ("tailscale name", re.compile(r"\b[a-z0-9-]+\.[a-z0-9-]+\.ts\.net\b|\btailnet\b", re.I)),
    ("account number", re.compile(r"\bPA[0-9A-Z]{8,12}\b")),
]


def _norm(line: str) -> str:
    line = line.split("#", 1)[0].strip()
    return re.sub(r"\s+", " ", line)


def _meaningful(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        n = _norm(raw)
        if len(n) >= 12 and not n.startswith(("import ", "from ", '"""', "return ", "def __init__")):
            out.append(n)
    return out


def fingerprints(text: str) -> set[str]:
    lines = _meaningful(text)
    return {hashlib.sha256("\n".join(lines[i:i + SHINGLE]).encode()).hexdigest()[:24]
            for i in range(max(0, len(lines) - SHINGLE + 1))}


def code_hash(text: str) -> str:
    return hashlib.sha256("\n".join(_meaningful(text)).encode()).hexdigest()[:24]


# ---------- the private list (git-ignored) ----------
def build_private(sources: list[str] | None = None, names: list[str] | None = None,
                  words: list[str] | None = None) -> dict:
    """Make botscope.private.json from your own strategy code: names, whole-file hashes and rule fingerprints only.
    `sources` = files or folders of your strategies (default: botscope.local.json "private": {"sources": [...]})."""
    from .imports import local_config
    cfg = local_config().get("private") or {}
    sources = sources or cfg.get("sources") or []
    if not sources:
        return {"error": 'no sources: add "private": {"sources": ["~/path/to/your/strategies"]} to botscope.local.json'}
    files = []
    for s in sources:
        p = Path(s).expanduser()
        files += sorted(p.rglob("*.py")) if p.is_dir() else [p] if p.is_file() else []
    files = [f for f in files if "__pycache__" not in f.parts and f.name != "__init__.py"]
    fps, hashes, stems = set(), set(), set()
    for f in files:
        t = f.read_text(errors="replace")
        fps |= fingerprints(t)
        hashes.add(code_hash(t))
        stems.add(f.stem.lower())
    out = {"strategy_names": sorted(stems | {n.lower() for n in (names or cfg.get("names") or [])}),
           "words": sorted(set(words or cfg.get("words") or [])), "code_hashes": sorted(hashes),
           "rule_fingerprints": sorted(fps)}
    PRIVATE_LIST.write_text(json.dumps(out, indent=1))
    return {"saved": str(PRIVATE_LIST.name), "files": len(files), "names": len(out["strategy_names"]),
            "fingerprints": len(fps), "note": "git-ignored; holds names and hashes only, never your code"}


def _private() -> dict:
    try:
        return json.loads(PRIVATE_LIST.read_text())
    except (OSError, ValueError):
        return {}


# ---------- export + scan ----------
def _tracked() -> list[str]:
    got = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [x for x in got.stdout.splitlines() if x]


def kept_home() -> set[str]:
    """Your own bots in bots_private/ (git-ignored): never exported, and never named by anything that is."""
    folder = ROOT / "bots_private"
    return {f"bots_private/{f.name}" for f in sorted(folder.glob("*.py"))} if folder.is_dir() else set()


def allowed(path: str) -> bool:
    match = lambda pats: any(fnmatch.fnmatchcase(path, p) for p in pats)
    return match(ALLOW) and not match(DENY)


def _home_names(home: set[str]) -> set[str]:
    """Each kept-home bot's file name and its display name (name = "...")."""
    out = set()
    for h in home:
        out.add(Path(h).stem)
        try:
            out |= set(re.findall(r"""^\s*name\s*=\s*['"]([^'"]+)['"]""", (ROOT / h).read_text(), re.M))
        except OSError:
            pass
    return out


def scan_text(path: str, text: str, priv: dict, home: set[str] = frozenset()) -> list[dict]:
    hits = []
    home_names = _home_names(home) if home else set()
    for i, line in enumerate(text.splitlines(), 1):
        for n in home_names:
            if re.search(rf"(?i)\b{re.escape(n)}\b", line):
                hits.append({"file": path, "line": i, "kind": "names a kept-home bot", "text": n})
        for kind, rx in _PATTERNS:
            for m in rx.finditer(line):
                if kind == "ip address" and any(int(x) > 255 for x in m.group().split(".")):
                    continue
                hits.append({"file": path, "line": i, "kind": kind, "text": m.group()[:60]})
        for w in priv.get("words") or []:
            if w and re.search(rf"(?i)\b{re.escape(w)}\b", line):
                hits.append({"file": path, "line": i, "kind": "private word", "text": w})
    if path.endswith(".py"):
        names = set(priv.get("strategy_names") or [])
        stem = Path(path).stem.lower()
        if path.startswith("bots/") and stem in names:
            hits.append({"file": path, "line": 0, "kind": "private strategy name", "text": stem})
        for m in re.finditer(r"""^\s*name\s*=\s*['"]([^'"]+)['"]""", text, re.M):
            if m.group(1).lower().replace(" ", "_") in names:
                hits.append({"file": path, "line": 0, "kind": "private strategy name", "text": m.group(1)})
        if code_hash(text) in set(priv.get("code_hashes") or []):
            hits.append({"file": path, "line": 0, "kind": "private code (whole file)", "text": "same code"})
        shared = fingerprints(text) & set(priv.get("rule_fingerprints") or [])
        if shared:
            hits.append({"file": path, "line": 0, "kind": "private rules (fingerprint)",
                         "text": f"{len(shared)} matching blocks of {SHINGLE} lines"})
    return hits


def check_image(path: str, data: bytes) -> list[dict]:
    """A reviewed image must be byte-for-byte the one a person looked at, with no metadata blocks."""
    if hashlib.sha256(data).hexdigest() != REVIEWED_IMAGES.get(path):
        return [{"file": path, "line": 0, "kind": "image changed since review",
                 "text": "look at it again, then update its hash in REVIEWED_IMAGES"}]
    return [{"file": path, "line": 0, "kind": "image metadata", "text": m.decode()} for m in _IMAGE_META if m in data]


def broken_links(dest: Path, md_files: list[str]) -> list[dict]:
    """Links and images in the exported docs that point at a file the export left out (it would be broken)."""
    hits = []
    for f in md_files:
        for i, line in enumerate((dest / f).read_text().splitlines(), 1):
            for m in _LINK.finditer(line):
                target = (m.group(1) or m.group(2)).split("#", 1)[0]
                if not target or re.match(r"[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("/"):
                    continue                                   # web links, mailto:, anchors on the same page
                if not (dest / f).parent.joinpath(target).exists():
                    hits.append({"file": f, "line": i, "kind": "broken link (not exported)", "text": target[:60]})
    return hits


def tree_hash(dest: Path) -> str:
    """One hash of every file in the export (names and bytes), so make_repo can tell nothing changed after the scan."""
    h = hashlib.sha256()
    for p in sorted(p for p in dest.rglob("*") if p.is_file() and p.name != MARKER and ".git" not in
                    p.relative_to(dest).parts):
        h.update(p.relative_to(dest).as_posix().encode() + b"\0" + hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def run(out: str | None = None, keep: bool = True) -> dict:
    """Build the clean export in a separate folder and scan it. ok=False on any hit (fails loudly)."""
    dest = Path(out).expanduser() if out else DEFAULT_OUT
    if dest.resolve() == ROOT.resolve() or ROOT.resolve() in dest.resolve().parents:
        return {"ok": False, "error": "the export folder must be outside the BotScope folder"}
    if dest.exists():
        if not (dest / MARKER).exists():
            return {"ok": False, "error": f"{dest} exists and isn't an earlier export; pick an empty folder"}
        shutil.rmtree(dest)
    home = kept_home()                               # bots_private/: the user's own bots, never exported
    tracked = _tracked()
    files = [f for f in tracked if (allowed(f) or f in REVIEWED_IMAGES) and f not in home and (ROOT / f).is_file()]
    dest.mkdir(parents=True)
    (dest / MARKER).write_text(json.dumps({"made_by": "botscope publish-check; safe to delete", "ok": False}))
    priv, hits, binary = _private(), [], []
    for f in files:
        (dest / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, dest / f)
        if f in REVIEWED_IMAGES:
            hits += check_image(f, (ROOT / f).read_bytes())
            continue
        try:
            text = (ROOT / f).read_text()
        except UnicodeDecodeError:
            binary.append(f)                         # images etc.: can't be scanned, so they need a human look
            continue
        hits += scan_text(f, text, priv, home)
    hits += broken_links(dest, [f for f in files if f.endswith(".md")])
    left_out = sorted(f for f in tracked if f not in files)
    ok = not hits and not binary and bool(priv)
    (dest / MARKER).write_text(json.dumps({"made_by": "botscope publish-check; safe to delete", "ok": ok,
                                           "tree": tree_hash(dest)}))
    if not keep:
        shutil.rmtree(dest)
    by_kind: dict[str, int] = {}
    for h in hits:
        by_kind[h["kind"]] = by_kind.get(h["kind"], 0) + 1
    verdict = ("PASS: nothing personal found in the export. Going public still needs your (and a parent's) go-ahead. "
               "Next: publish-check --make-repo turns the export into a fresh one-commit repo (nothing is pushed)."
               if ok else "FAIL: do not publish. Fix every hit (or replace the file with a generic example) and run again.")
    if not priv:
        verdict += " No private list yet: run publish_check(how=\"build_private\") so your own strategies are checked too."
    return {"ok": ok, "verdict": verdict, "export": str(dest) if keep else None, "files": len(files),
            "left_out": len(left_out), "hits": len(hits), "by_kind": by_kind, "first_hits": hits[:40],
            "unscanned_binary_files": binary, "private_list": bool(priv), "kept_home": sorted(home),
            "note": "Nothing was published or pushed. The export is a local folder only."}


# ---------- a brand-new repo from the export (never this repo's history) ----------
def _git(dest: Path, *args: str) -> str:
    cmd = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "init.templateDir=", *args]
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",   # no aliases, hooks, signing
           "GIT_AUTHOR_NAME": PUBLISH_NAME, "GIT_AUTHOR_EMAIL": PUBLISH_EMAIL, "GIT_AUTHOR_DATE": _today_utc(),
           "GIT_COMMITTER_NAME": PUBLISH_NAME, "GIT_COMMITTER_EMAIL": PUBLISH_EMAIL, "GIT_COMMITTER_DATE": _today_utc()}
    return subprocess.run(cmd, cwd=dest, env=env, capture_output=True, text=True, check=True).stdout.strip()


def _today_utc() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00+0000")     # the day only, no time or time zone


def make_repo(out: str | None = None) -> dict:
    """Turn a PASSed export into a brand-new git repo with exactly one commit: no history from this repo, no remote,
    nothing pushed. Refuses unless the folder is one publish-check made, its scan passed, and nothing in it changed
    since. Prints the commands to publish it later, which is the user's (and a parent's) decision."""
    dest = Path(out).expanduser() if out else DEFAULT_OUT
    if not dest.is_dir():
        return {"ok": False, "error": f"no export at {dest}: run publish-check first"}
    if dest.resolve() == ROOT.resolve() or ROOT.resolve() in dest.resolve().parents:
        return {"ok": False, "error": "the export folder must be outside the BotScope folder"}
    try:
        stamp = json.loads((dest / MARKER).read_text())
    except (OSError, ValueError):
        return {"ok": False, "error": f"{dest} isn't a folder publish-check made (or is from an older version): "
                                      "run publish-check again"}
    if stamp.get("ok") is not True:
        return {"ok": False, "error": "its publish-check didn't PASS: fix every hit, run publish-check again"}
    if (dest / ".git").exists():
        return {"ok": False, "error": f"{dest} is already a git repo: run publish-check again for a fresh copy"}
    if stamp.get("tree") != tree_hash(dest):
        return {"ok": False, "error": "files in the export changed after the scan: run publish-check again"}
    _git(dest, "init", "-q", "-b", "main")
    (dest / ".git" / "info").mkdir(exist_ok=True)
    (dest / ".git" / "info" / "exclude").write_text(MARKER + "\n")       # the export's stamp stays out of the commit
    _git(dest, "add", "-A")
    _git(dest, "commit", "-q", "-m", "BotScope: first public version")
    commits, remotes = _git(dest, "rev-list", "--count", "HEAD"), _git(dest, "remote")
    files = len(_git(dest, "ls-files").splitlines())
    if commits != "1" or remotes:                                       # can't happen; stop loudly if it ever does
        return {"ok": False, "error": f"unexpected repo state: {commits} commits, remotes {remotes!r}"}
    q = lambda p: f'"{p}"' if " " in str(p) else str(p)
    return {"ok": True, "repo": str(dest), "commits": 1, "files": files, "remote": None,
            "author": f"{PUBLISH_NAME} <{PUBLISH_EMAIL}>",
            "verdict": "Made a brand-new git repo from the clean export: one commit, no history from your own repo, "
                       "no remote. Nothing was pushed or published.",
            "decision": "Publishing is your (and a parent's) decision. Nothing here does it for you.",
            "to_publish_later": [
                "1. On github.com, make a new EMPTY public repo (no README, no license, no .gitignore), "
                "named BotScope under your GitHub account",
                f"2. cd {q(dest)}",
                "3. git remote add origin https://github.com/YOUR-GITHUB-NAME/BotScope.git",
                "4. git push -u origin main"],
            "never": "Never push your own BotScope folder, and never make a GitHub repo public that it was pushed to: "
                     "their history has your notes and strategies. If that private repo already has the name you "
                     "want (BotScope), rename it first (e.g. BotScope-private), then make the new empty one."}
