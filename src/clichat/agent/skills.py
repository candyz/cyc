"""Skills management system for standard Agent Skills.
Supports:
- Industry Standard Skills format: directory containing SKILL.md with YAML frontmatter (name, description, version, etc.)
- Helper subdirectories: scripts/, examples/, resources/, references/
- Single-file Markdown skills: <name>.md
- Multi-agent / multi-tool discovery paths:
  1. Builtin default skills (commit, test, refactor)
  2. Google Antigravity / Gemini CLI:
     - ~/.gemini/antigravity-cli/builtin/skills/
     - ~/.gemini/skills/
  3. Claude Code / OpenClaude:
     - ~/.claude/skills/
  4. OpenCode:
     - ~/.config/opencode/skills/
  5. Codex / Hermes:
     - ~/.codex/skills/
     - ~/.hermes/skills/
  6. Standard Clichat Global directory:
     - ~/.config/clichat/skills/
  7. User-configured custom paths via config.yaml (`skills_dirs`)
  8. Workspace-level project skills:
     - <workspace>/.agents/skills/ (Standard Antigravity / Agent workspace layout)
     - <workspace>/.claude/skills/
     - <workspace>/.clichat/skills/
     - <workspace>/skills/
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

# Standard Built-in Skills
BUILTIN_SKILLS: Dict[str, Dict[str, Any]] = {
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
        "source": "builtin",
        "path": "",
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
        "source": "builtin",
        "path": "",
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
        "source": "builtin",
        "path": "",
    },
}

# Standard Global / Tool Skills Directories
GLOBAL_SKILL_SEARCH_PATHS = [
    ("clichat", Path.home() / ".config" / "clichat" / "skills"),
    ("antigravity", Path.home() / ".gemini" / "antigravity-cli" / "builtin" / "skills"),
    ("gemini", Path.home() / ".gemini" / "skills"),
    ("claude", Path.home() / ".claude" / "skills"),
    ("opencode", Path.home() / ".config" / "opencode" / "skills"),
    ("codex", Path.home() / ".codex" / "skills"),
    ("hermes", Path.home() / ".hermes" / "skills"),
]

# Standard Project Workspace Skills Subdirectories
WORKSPACE_SKILL_SUBDIRS = [
    ("workspace:agents", Path(".agents") / "skills"),
    ("workspace:claude", Path(".claude") / "skills"),
    ("workspace:clichat", Path(".clichat") / "skills"),
    ("workspace", Path("skills")),
]


class SkillManager:
    """Manages skill discovery, loading, and application across standard agent formats."""

    @classmethod
    def parse_skill_file(cls, path: Path) -> Optional[Dict[str, Any]]:
        """Parse a SKILL.md or <name>.md file with optional YAML frontmatter.
        Returns dictionary with keys: name, description, content, frontmatter, path.
        """
        try:
            raw_text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

        frontmatter: Dict[str, Any] = {}
        content = raw_text

        # Parse YAML frontmatter if delimited by '---'
        if raw_text.startswith("---"):
            parts = raw_text.split("---", 2)
            if len(parts) >= 3:
                try:
                    parsed_yaml = yaml.safe_load(parts[1])
                    if isinstance(parsed_yaml, dict):
                        frontmatter = parsed_yaml
                        content = parts[2].strip()
                except Exception:
                    pass

        # Determine skill name
        skill_name = frontmatter.get("name")
        if not skill_name:
            if path.name.lower() == "skill.md":
                skill_name = path.parent.name.lower()
            else:
                skill_name = path.stem.lower()
        else:
            skill_name = str(skill_name).lower().strip()

        # Determine description
        description = frontmatter.get("description")
        if not description:
            lines = content.strip().splitlines()
            if lines and lines[0].startswith("#"):
                description = lines[0].lstrip("#").strip()
            else:
                description = "Custom agent skill."
        else:
            description = str(description).strip()

        # Check for helper subdirectories in standard skill packages
        parent_dir = path.parent
        has_scripts = (parent_dir / "scripts").is_dir()
        has_references = (parent_dir / "references").is_dir()
        has_resources = (parent_dir / "resources").is_dir()
        has_examples = (parent_dir / "examples").is_dir()

        metadata_notes = []
        if has_scripts:
            metadata_notes.append("scripts")
        if has_references:
            metadata_notes.append("references")
        if has_resources:
            metadata_notes.append("resources")
        if has_examples:
            metadata_notes.append("examples")

        return {
            "name": skill_name,
            "description": description,
            "content": content,
            "frontmatter": frontmatter,
            "path": str(path),
            "directory": str(parent_dir),
            "helpers": metadata_notes,
        }

    @classmethod
    def _scan_directory(
        cls,
        dir_path: Path,
        source_label: str,
        output_dict: Dict[str, Dict[str, Any]],
    ) -> None:
        """Scan a directory for both package-style skills (<skill>/SKILL.md) and single-file skills (<skill>.md)."""
        if not dir_path.exists() or not dir_path.is_dir():
            return

        try:
            for item in dir_path.glob("*"):
                skill_data = None
                if item.is_dir():
                    skill_file = item / "SKILL.md"
                    if not skill_file.exists():
                        skill_file = item / "skill.md"
                    if skill_file.is_file():
                        skill_data = cls.parse_skill_file(skill_file)
                elif item.is_file() and item.suffix.lower() == ".md":
                    skill_data = cls.parse_skill_file(item)

                if skill_data and skill_data["name"]:
                    skill_data["source"] = source_label
                    output_dict[skill_data["name"]] = skill_data
        except Exception:
            pass

    @classmethod
    def list_skills(
        cls,
        workspace_path: Optional[Path] = None,
        custom_skills_dirs: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """List all available skills merged from builtin, global tools, custom config, and workspace sources.
        Later sources override earlier ones with the same skill name.
        """
        skills: Dict[str, Dict[str, Any]] = dict(BUILTIN_SKILLS)

        # 1. Global tools and agents
        for label, search_path in GLOBAL_SKILL_SEARCH_PATHS:
            cls._scan_directory(search_path, label, skills)

        # 2. User-configured custom skill directories
        if custom_skills_dirs:
            for c_dir in custom_skills_dirs:
                p = Path(c_dir).expanduser()
                cls._scan_directory(p, "custom", skills)

        # 3. Workspace / Project skills (hierarchical precedence)
        if workspace_path:
            for label, sub_path in WORKSPACE_SKILL_SUBDIRS:
                w_path = workspace_path / sub_path
                cls._scan_directory(w_path, label, skills)

        return sorted(list(skills.values()), key=lambda s: s["name"])

    @classmethod
    def get_skill(
        cls,
        name: str,
        workspace_path: Optional[Path] = None,
        custom_skills_dirs: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a specific skill by name."""
        skills = {s["name"]: s for s in cls.list_skills(workspace_path, custom_skills_dirs)}
        return skills.get(name.lower().strip())
