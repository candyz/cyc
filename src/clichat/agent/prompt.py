import os
import platform
import subprocess
from pathlib import Path
from typing import Optional

def get_git_info() -> str:
    """Retrieve current git branch and dirty status if in a git repo."""
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain=v1", "-b"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            branch_line = lines[0] if lines else "unknown"
            modified_count = len(lines) - 1
            return f"Git Branch: {branch_line} ({modified_count} modified files)"
    except Exception:
        pass
    return "Git: Not in a git repository"

def build_coding_agent_system_prompt(custom_instructions: Optional[str] = None) -> str:
    cwd = Path.cwd().resolve()
    system_os = platform.system()
    git_info = get_git_info()

    base_prompt = f"""You are clichat Coding Agent, an expert AI software engineer pair programming with the user.

Workspace Environment:
- Current Working Directory: {cwd}
- Operating System: {system_os}
- {git_info}

Core Operating Principles:
1. Grounded Action: Do not guess or assume file paths or implementations. Use `list_dir`, `read_file`, and `grep_search` to inspect existing code before taking action.
2. Surgical Modifications: When editing code, prefer `replace_file_content` with exact matching to minimize unnecessary diffs. Only use `write_file` when creating new files or completely rewriting small files.
3. Verification: After making changes, use `run_command` to execute tests, linters, or verification scripts to verify that your changes work.
4. Transparency: Explain your rationale clearly and concisely before calling tools.
"""

    # Check for repository instruction files (CLICHAT.md, AGENTS.md, GEMINI.md, CLAUDE.md, etc.)
    rule_candidates = (
        "CLICHAT.md",
        "AGENTS.md",
        ".gemini/GEMINI.md",
        ".gemini/AGENTS.md",
        "GEMINI.md",
        "CLAUDE.md",
        ".cursorrules",
    )
    for rule_file in rule_candidates:
        rule_path = cwd / rule_file
        if rule_path.exists() and rule_path.is_file():
            try:
                rule_content = rule_path.read_text(encoding="utf-8")[:8000]
                base_prompt += f"\nProject Guidelines ({rule_file}):\n{rule_content}\n"
                break
            except Exception:
                pass

    if custom_instructions:
        base_prompt += f"\nUser Custom Instructions:\n{custom_instructions}\n"

    return base_prompt.strip()
