"""Every plugin skill has frontmatter whose name matches its folder and a description that says when to use it."""
from pathlib import Path

SKILLS = Path(__file__).parent.parent / "skills"


def test_skill_frontmatter():
    folders = sorted(p for p in SKILLS.iterdir() if p.is_dir())
    assert {"botscope-fact-check", "botscope-new-bot"} <= {p.name for p in folders}
    for d in folders:
        text = (d / "SKILL.md").read_text()
        head = text.split("---")[1]
        meta = dict(line.split(": ", 1) for line in head.strip().splitlines())
        assert meta["name"] == d.name and "Use when" in meta["description"]
        assert "Not financial advice" in text or "not financial advice" in text.lower() or d.name == "botscope-safety"
