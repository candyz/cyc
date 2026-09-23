import pytest
from pathlib import Path
from cyc.agent.rules import RuleManager, PROJECT_RULE_CANDIDATES

def test_rule_manager_empty(tmp_path):
    mgr = RuleManager(workspace_dir=tmp_path, global_rules_dir=tmp_path / "global_rules")
    assert mgr.discover_global_rules() == []
    assert mgr.discover_project_rules() == []
    assert mgr.load_combined_rules() == ""

def test_rule_manager_discovers_project_rules(tmp_path):
    (tmp_path / "CYC.md").write_text("# Project Rules\nRule 1: Be fast.", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# Claude Rules\nBe precise.", encoding="utf-8")

    mgr = RuleManager(workspace_dir=tmp_path, global_rules_dir=tmp_path / "non_existent")
    rules = mgr.discover_project_rules()
    assert len(rules) == 2
    titles = [r[0] for r in rules]
    assert "Project Guideline: CYC.md" in titles
    assert "Project Guideline: CLAUDE.md" in titles

    combined = mgr.load_combined_rules()
    assert "Rule 1: Be fast." in combined
    assert "Be precise." in combined

def test_rule_manager_discovers_global_rules(tmp_path):
    g_dir = tmp_path / "global"
    g_dir.mkdir()
    (g_dir / "01_security.md").write_text("No hardcoded secrets.", encoding="utf-8")
    (g_dir / "02_style.md").write_text("Use black formatting.", encoding="utf-8")

    mgr = RuleManager(workspace_dir=tmp_path, global_rules_dir=g_dir)
    g_rules = mgr.discover_global_rules()
    assert len(g_rules) == 2
    assert "Global Rule: 01_security.md" in g_rules[0][0]
    assert "No hardcoded secrets." in g_rules[0][1]

    combined = mgr.load_combined_rules()
    assert "Global Rule: 01_security.md" in combined
    assert "Global Rule: 02_style.md" in combined

def test_rule_manager_truncation(tmp_path):
    (tmp_path / "CYC.md").write_text("A" * 20000, encoding="utf-8")
    mgr = RuleManager(workspace_dir=tmp_path, global_rules_dir=tmp_path / "empty")
    combined = mgr.load_combined_rules(max_total_chars=1000)
    assert len(combined) <= 1200
    assert "truncated" in combined
