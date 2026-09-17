"""Skills management system inspired by DeepSeek Harness (DSH).
Skills represent reusable methods, workflows, or instructions for the agent to follow.
Discovered from:
- System builtin default skills
- Global user skills: ~/.config/clichat/skills/<name>.md (or <name>/SKILL.md)
- Workspace local skills: .clichat/skills/<name>.md (or <name>/SKILL.md)
"""

from pathlib import Path
from typing import Dict, List, Optional
import yaml

GLOBAL_SKILLS_DIR = Path.home() / ".config" / "clichat" / "skills"
LOCAL_SKILLS_DIR_NAME = ".clichat/skills"

BUILTIN_SKILLS: Dict[str, Dict[str, str]] = {
    "commit": {
        "name": "commit",
        "description": "Generate high-quality Conventional Commit messages following Angular specification.",
        "content": """### Conventional Commit Skill
When preparing or committing changes:
1. Run `git status` and `git diff --cached` (or inspect changed files) to review changes.
2. Formulate commit messages following: `<type>(<scope>): <short description>`
   - Types: feat, fix, docs, style, refactor, perf, test, chore, build, ci
3. Keep the subject line concise (<= 72 chars), imperative mood, no ending period.
4. If breaking changes exist, add `BREAKING CHANGE:` in footer.
""",
    },
    "test": {
        "name": "test",
        "description": "Systematic testing workflow: locate test runner, execute tests, and analyze failures.",
        "content": """### Test Execution & Debugging Skill
1. Identify the project test framework (e.g. pytest for Python, jest/vitest for JS, cargo test for Rust, go test for Go).
2. Execute tests using `run_command` with relevant filters (avoid running massive unrelated suites initially).
3. If tests fail, read the failure traceback carefully, inspect the offending source code, make surgical fixes, and re-run.
4. Verify all tests pass cleanly before completing the turn.
""",
    },
    "refactor": {
        "name": "refactor",
        "description": "Safe code refactoring workflow: verify tests pass before and after changes.",
        "content": """### Safe Refactoring Skill
1. Baseline Check: Run existing unit tests first to ensure the code is currently in a working state.
2. Single-responsibility edits: Touch only targeted classes or functions without breaking public signatures.
3. Cleanliness: Remove dead imports or unused helper functions introduced during changes.
4. Verification: Run tests again to verify identical external behavior.
""",
    },
}


class SkillManager:
    """Manages skill discovery, loading, and application."""

    @classmethod
    def list_skills(cls, workspace_path: Optional[Path] = None) -> List[Dict[str, str]]:
        """List all available skills merged from builtin, global, and workspace sources."""
        skills: Dict[str, Dict[str, str]] = dict(BUILTIN_SKILLS)

        # 1. Global user skills
        if GLOBAL_SKILLS_DIR.exists():
            cls._scan_skill_dir(GLOBAL_SKILLS_DIR, skills)

        # 2. Local workspace skills
        if workspace_path:
            local_dir = workspace_path / LOCAL_SKILLS_DIR_NAME
            if local_dir.exists():
                cls._scan_skill_dir(local_dir, skills)

        return sorted(list(skills.values()), key=lambda s: s["name"])

    @classmethod
    def _scan_skill_dir(cls, dir_path: Path, output_dict: Dict[str, Dict[str, str]]) -> None:
        for p in dir_path.glob("*"):
            skill_name = None
            content = None
            description = "Custom user-defined skill."

            if p.is_file() and p.suffix.lower() == ".md":
                skill_name = p.stem.lower()
                content = p.read_text(encoding="utf-8")
            elif p.is_dir() and (p / "SKILL.md").exists():
                skill_name = p.name.lower()
                content = (p / "SKILL.md").read_text(encoding="utf-8")

            if skill_name and content:
                # Extract first line or frontmatter as description if available
                lines = content.strip().splitlines()
                if lines and lines[0].startswith("#"):
                    description = lines[0].lstrip("#").strip()
                output_dict[skill_name] = {
                    "name": skill_name,
                    "description": description,
                    "content": content,
                }

    @classmethod
    def get_skill(cls, name: str, workspace_path: Optional[Path] = None) -> Optional[Dict[str, str]]:
        skills = {s["name"]: s for s in cls.list_skills(workspace_path)}
        return skills.get(name.lower().strip())
