from pathlib import Path
import pytest
from cyc.agent.prompt import build_coding_agent_system_prompt
from cyc.agent.diff import generate_unified_diff, render_diff_panel

def test_build_coding_agent_system_prompt_default():
    prompt = build_coding_agent_system_prompt()
    assert "You are cyc Coding Agent" in prompt
    assert "Workspace Environment:" in prompt
    assert "Core Operating Principles:" in prompt

def test_build_coding_agent_system_prompt_with_cyc_md(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cyc_md = tmp_path / "CYC.md"
    cyc_md.write_text("Always use TypeScript and adhere to ESLint rules.", encoding="utf-8")

    prompt = build_coding_agent_system_prompt()
    assert "Project Guidelines (CYC.md):" in prompt
    assert "Always use TypeScript and adhere to ESLint rules." in prompt

def test_build_coding_agent_system_prompt_with_agents_md(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("Follow Clean Architecture guidelines.", encoding="utf-8")

    prompt = build_coding_agent_system_prompt()
    assert "Project Guidelines (AGENTS.md):" in prompt
    assert "Follow Clean Architecture guidelines." in prompt

def test_generate_unified_diff():
    orig = "line1\nline2\nline3\n"
    new = "line1\nline2_modified\nline3\n"
    diff = generate_unified_diff("test.txt", orig, new)
    assert "-line2" in diff
    assert "+line2_modified" in diff

def test_render_diff_panel_truncation():
    orig = "line\n" * 300
    new = "new_line\n" * 300
    # Ensure render_diff_panel handles truncation cleanly without exception
    render_diff_panel("test.txt", orig, new, max_diff_lines=50)
