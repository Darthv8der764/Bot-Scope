"""The README's tool and skill counts keep up with the code."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_readme_tool_and_skill_counts_match():
    readme = (ROOT / "README.md").read_text()
    tools = (ROOT / "botscope" / "server.py").read_text().count("@mcp.tool(")
    about = int(re.search(r"about (\d+) tools", readme).group(1))
    assert abs(about - tools) <= 10, f"README says about {about} tools, server has {tools}"
    skills = sorted(p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md"))
    assert f"+ {len(skills)} skills" in readme
    for name in skills:
        assert f"`{name}`" in readme, f"{name} missing from the README's skill list"
