from pathlib import Path
from typing import List, Optional, Tuple

# Supported project rule filenames in priority order
PROJECT_RULE_CANDIDATES = [
    "CYC.md",
    "AGENTS.md",
    ".gemini/GEMINI.md",
    ".gemini/AGENTS.md",
    "GEMINI.md",
    "CLAUDE.md",
    ".cursorrules",
]

class RuleManager:
    """Discovers and merges global (~/.config/cyc/rules/) and project-level rule files."""

    def __init__(self, workspace_dir: Optional[Path] = None, global_rules_dir: Optional[Path] = None):
        self.workspace_dir = (workspace_dir or Path.cwd()).resolve()
        self.global_rules_dir = (
            global_rules_dir or (Path.home() / ".config" / "cyc" / "rules")
        ).resolve()

    def discover_global_rules(self) -> List[Tuple[str, str]]:
        """Return list of (rule_name, content) from global rules directory."""
        rules = []
        if self.global_rules_dir.exists() and self.global_rules_dir.is_dir():
            for p in sorted(self.global_rules_dir.glob("*.md")):
                if p.is_file():
                    try:
                        content = p.read_text(encoding="utf-8", errors="replace").strip()
                        if content:
                            rules.append((f"Global Rule: {p.name}", content))
                    except Exception:
                        pass
        return rules

    def discover_project_rules(self) -> List[Tuple[str, str]]:
        """Return list of (rule_name, content) from workspace directory."""
        rules = []
        for candidate in PROJECT_RULE_CANDIDATES:
            target_path = self.workspace_dir / candidate
            if target_path.exists() and target_path.is_file():
                try:
                    content = target_path.read_text(encoding="utf-8", errors="replace").strip()
                    if content:
                        rules.append((f"Project Guideline: {candidate}", content))
                except Exception:
                    pass
        return rules

    def load_combined_rules(self, max_total_chars: int = 16000) -> str:
        """Combine global and project rules into a formatted Markdown block with truncation."""
        all_rules = self.discover_global_rules() + self.discover_project_rules()
        if not all_rules:
            return ""

        sections = []
        current_len = 0

        for title, content in all_rules:
            # Per-rule safeguard (limit single rule to 8000 chars)
            if len(content) > 8000:
                content = content[:8000] + "\n... [truncated]"

            rule_block = f"### {title}\n{content}\n"
            if current_len + len(rule_block) > max_total_chars:
                remaining = max_total_chars - current_len
                if remaining > 100:
                    sections.append(rule_block[:remaining] + "\n... [rules truncated to fit budget]")
                break

            sections.append(rule_block)
            current_len += len(rule_block)

        return "\n".join(sections)
