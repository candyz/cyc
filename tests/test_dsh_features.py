import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from cyc.agent.tools.command import RunScriptTool
from cyc.agent.loop import AgentLoop
from cyc.agent.skills import SkillManager
from cyc.session import SessionManager
from cyc.cli import CliApp
from cyc.config import Config, ProviderConfig, load_config
from cyc.agent.permissions import PermissionManager, PermissionMode


@pytest.mark.asyncio
async def test_run_script_tool_python(tmp_path):
    tool = RunScriptTool()
    code = """
import sys
print("Hello from PTC script!")
sys.stdout.write("Line 2\\n")
"""
    result = await tool.execute(language="python", code=code, timeout=10)
    assert "Exit Code: 0" in result
    assert "Hello from PTC script!" in result
    assert "Line 2" in result


@pytest.mark.asyncio
async def test_run_script_tool_bash(tmp_path):
    tool = RunScriptTool()
    code = """
echo "Bash PTC execution"
"""
    result = await tool.execute(language="bash", code=code, timeout=10)
    assert "Exit Code: 0" in result
    assert "Bash PTC execution" in result


from cyc.providers.base import AgentTurnResponse

@pytest.mark.asyncio
async def test_agent_loop_strategies(tmp_path):
    mock_provider = MagicMock()
    mock_resp = AgentTurnResponse(content="Goal accomplished.", tool_calls=[])
    mock_provider.chat_with_tools = AsyncMock(return_value=mock_resp)

    session = SessionManager(session_id="strategy_test", sessions_dir=tmp_path)
    loop = AgentLoop(
        provider=mock_provider,
        model="mock-model",
        session=session,
        strategy="plan",
    )
    assert loop.strategy == "plan"
    res = await loop.run_turn("Refactor the parser module")
    assert res == "Goal accomplished."
    # Check that in plan mode, planning instruction was added
    assert any("plan" in m["content"].lower() for m in session.messages if m["role"] == "user")

    # Test minimal strategy
    loop.strategy = "minimal"
    assert loop.strategy == "minimal"


def test_session_event_sourcing_and_forking(tmp_path):
    session = SessionManager(session_id="event_test", sessions_dir=tmp_path)
    session.add_user_message("Initial prompt")
    session.add_assistant_message("Initial answer")

    # Check events recorded
    assert len(session.events) >= 2
    event_types = [e["type"] for e in session.events]
    assert "user_message" in event_types
    assert "assistant_message" in event_types

    # Check append-only .events.jsonl exists
    events_log_file = tmp_path / "event_test.events.jsonl"
    assert events_log_file.exists()
    lines = events_log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(session.events)

    # Test Forking
    forked = session.fork_session("forked_branch_1")
    assert forked.session_id == "forked_branch_1"
    assert len(forked.messages) == 2
    assert any(e["type"] == "forked_from" for e in forked.events)
    assert (tmp_path / "forked_branch_1.json").exists()


def test_skill_manager_discovery_and_lookup(tmp_path):
    skills = SkillManager.list_skills(tmp_path)
    skill_names = [s["name"] for s in skills]
    assert "commit" in skill_names
    assert "test" in skill_names
    assert "refactor" in skill_names

    # Add a custom workspace skill
    local_skills_dir = tmp_path / ".cyc" / "skills"
    local_skills_dir.mkdir(parents=True)
    custom_skill_file = local_skills_dir / "deploy.md"
    custom_skill_file.write_text("# Production Deployment Skill\nRun deployment scripts carefully.")

    updated_skills = SkillManager.list_skills(tmp_path)
    assert any(s["name"] == "deploy" for s in updated_skills)

    deploy_skill = SkillManager.get_skill("deploy", tmp_path)
    assert deploy_skill is not None
    assert deploy_skill["description"] == "Production Deployment Skill"
    assert "Run deployment scripts" in deploy_skill["content"]

    # Test Standard Package Skill format with frontmatter and helper subdirectories in .agents/skills
    agents_skills_dir = tmp_path / ".agents" / "skills"
    standard_skill_dir = agents_skills_dir / "docker-workflow"
    standard_skill_dir.mkdir(parents=True)
    (standard_skill_dir / "scripts").mkdir()
    (standard_skill_dir / "references").mkdir()

    standard_skill_content = """---
name: docker-workflow
description: Automated Docker container building and deployment procedures.
version: 2.1.0
---

# Docker Workflow Runbook
Follow the steps in references/deploy.md and run scripts/build.sh.
"""
    (standard_skill_dir / "SKILL.md").write_text(standard_skill_content, encoding="utf-8")

    all_skills = SkillManager.list_skills(tmp_path)
    docker_skill = next((s for s in all_skills if s["name"] == "docker-workflow"), None)
    assert docker_skill is not None
    assert docker_skill["description"] == "Automated Docker container building and deployment procedures."
    assert docker_skill["frontmatter"]["version"] == "2.1.0"
    assert "scripts" in docker_skill["helpers"]
    assert "references" in docker_skill["helpers"]
    assert "workspace:agents" in docker_skill["source"]

    # Test custom skills directory from user config
    custom_external_dir = tmp_path / "custom_agent_skills"
    custom_external_dir.mkdir()
    (custom_external_dir / "ci-cd.md").write_text("---\nname: ci-cd\ndescription: CI/CD automation\n---\nRun CI", encoding="utf-8")

    custom_skills = SkillManager.list_skills(tmp_path, custom_skills_dirs=[str(custom_external_dir)])
    ci_skill = next((s for s in custom_skills if s["name"] == "ci-cd"), None)
    assert ci_skill is not None
    assert ci_skill["description"] == "CI/CD automation"
    assert ci_skill["source"] == "custom"


@pytest.mark.asyncio
async def test_slash_commands_dsh(tmp_path):
    config = Config(
        default_provider="dummy",
        default_model="dummy-model",
        providers={"dummy": ProviderConfig(api_key="test")},
    )
    session = SessionManager(session_id="cli_dsh_test", sessions_dir=tmp_path)
    app = CliApp(config=config, session=session)
    app.workspace_path = tmp_path

    # Test /loop command
    await app.handle_slash_command("/loop plan")
    assert app.agent_loop.strategy == "plan"
    await app.handle_slash_command("/loop minimal")
    assert app.agent_loop.strategy == "minimal"
    await app.handle_slash_command("/loop standard")
    assert app.agent_loop.strategy == "standard"
    await app.handle_slash_command("/loop 50")
    assert app.agent_loop.max_turns == 50
    await app.handle_slash_command("/loop plan 100")
    assert app.agent_loop.strategy == "plan"
    assert app.agent_loop.max_turns == 100

    # Test /context command
    await app.handle_slash_command("/context 200k")
    assert app.session.max_context_tokens == 200_000
    await app.handle_slash_command("/context 1m")
    assert app.session.max_context_tokens == 1_000_000
    await app.handle_slash_command("/context 64000")
    assert app.session.max_context_tokens == 64_000

    # Test /compact command
    app.session.max_context_tokens = 500
    for i in range(10):
        app.session.messages.append({"role": "user", "content": f"Historical message number {i} with substantial length text."})
        app.session.messages.append({"role": "assistant", "content": f"Historical response number {i} with additional content text."})
    initial_tokens = app.session.total_estimated_tokens()
    assert initial_tokens > 250
    compact_res = await app.handle_slash_command("/compact")
    assert compact_res is True
    assert app.session.total_estimated_tokens() < initial_tokens
    assert any("[Context compacted:" in str(m.get("content", "")) for m in app.session.messages)

    # Test /skill command
    await app.handle_slash_command("/skill commit")
    assert app.session.system_prompt is not None
    assert "Conventional Commit Skill" in app.session.system_prompt

    # Test /skills listing command
    res = await app.handle_slash_command("/skills")
    assert res is True

    # Test /fork command
    orig_id = app.session.session_id
    await app.handle_slash_command("/fork dsh_fork_branch")
    assert app.session.session_id == "dsh_fork_branch"
    assert app.agent_loop.session.session_id == "dsh_fork_branch"
    assert app.session.session_id != orig_id

    # Test /usage command
    app.session.add_user_message("Hello token count test")
    app.session.add_assistant_message("Assistant reply test")
    assert app.session.total_prompt_tokens > 0
    assert app.session.total_completion_tokens > 0
    usage_res = await app.handle_slash_command("/usage")
    assert usage_res is True


@pytest.mark.asyncio
async def test_provider_usage_info():
    from cyc.providers.gemini import GeminiProvider
    from cyc.providers.agy import AntigravityProvider
    from cyc.providers.opencode import OpenCodeProvider

    gemini_prov = GeminiProvider(api_key="mock-key")
    gemini_info = await gemini_prov.get_usage_info("gemini-2.5-flash")
    assert "rate_limit_rpm" in gemini_info

    agy_prov = AntigravityProvider()
    agy_info = await agy_prov.get_usage_info("gemini-3.1-pro-high")
    assert "Gemini AI Pro Subscription" in agy_info["tier"]

    opencode_prov = OpenCodeProvider()
    opencode_info = await opencode_prov.get_usage_info()
    assert "Zen Free" in opencode_info["provider"]


def test_fixed_status_bar_scroll_region():
    config = load_config(Path("/nonexistent"))
    app = CliApp(config, provider_name="ollama")

    # In non-interactive or interactive environment, the context manager should safely execute without crashing
    with app.fixed_status_bar_scroll_region():
        pass

    # Status line markup should produce valid markup with project name and context
    markup = app._get_status_line_markup()
    assert "Context:" in markup
    assert "ollama" in markup
    assert app.workspace_path.name in markup


