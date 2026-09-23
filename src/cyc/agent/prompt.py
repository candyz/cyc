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

    base_prompt = f"""You are cyc Coding Agent, an expert AI software engineer pair programming with the user.

Workspace Environment:
- Current Working Directory: {cwd}
- Operating System: {system_os}
- {git_info}

Core Operating Principles:
1. Grounded Action: Do not guess or assume file paths or implementations. Use `list_dir`, `read_file`, `grep_search`, and `repo_map` to inspect existing code before taking action.
2. Surgical Modifications: When editing code, prefer `replace_file_content` with exact matching to minimize unnecessary diffs. Only use `write_file` when creating new files or completely rewriting small files.
3. Verification: After making changes, use `run_command` to execute tests, linters, or verification scripts to verify that your changes work.
4. Active Clarification: When requirements are ambiguous, multiple interpretations exist, or critical design decisions are needed, use `ask_user` to interactively clarify with the user rather than guessing.
5. Web Research: When encountering unfamiliar libraries, APIs, or modern documentation, use `web_search` and `fetch_url` to find up-to-date information.
6. Transparency: Explain your rationale clearly and concisely before calling tools.
"""

    # Load global and project rules via RuleManager
    from cyc.agent.rules import RuleManager
    rule_mgr = RuleManager(workspace_dir=cwd)
    combined_rules = rule_mgr.load_combined_rules()
    if combined_rules:
        base_prompt += f"\nProject & Environment Rules:\n{combined_rules}\n"

    if custom_instructions:
        base_prompt += f"\nUser Custom Instructions:\n{custom_instructions}\n"

    return base_prompt.strip()
