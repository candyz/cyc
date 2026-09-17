import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from clichat.agent.tools.command import RunScriptTool
from clichat.agent.loop import AgentLoop
from clichat.agent.skills import SkillManager
from clichat.session import SessionManager
from clichat.cli import CliApp
from clichat.config import Config, ProviderConfig
from clichat.agent.permissions import PermissionManager, PermissionMode


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


from clichat.providers.base import AgentTurnResponse

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
    local_skills_dir = tmp_path / ".clichat" / "skills"
    local_skills_dir.mkdir(parents=True)
    custom_skill_file = local_skills_dir / "deploy.md"
    custom_skill_file.write_text("# Production Deployment Skill\nRun deployment scripts carefully.")

    updated_skills = SkillManager.list_skills(tmp_path)
    assert any(s["name"] == "deploy" for s in updated_skills)

    deploy_skill = SkillManager.get_skill("deploy", tmp_path)
    assert deploy_skill is not None
    assert deploy_skill["description"] == "Production Deployment Skill"
    assert "Run deployment scripts" in deploy_skill["content"]


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
    from clichat.providers.gemini import GeminiProvider
    from clichat.providers.agy import AntigravityProvider
    from clichat.providers.opencode import OpenCodeProvider

    gemini_prov = GeminiProvider(api_key="mock-key")
    gemini_info = await gemini_prov.get_usage_info("gemini-2.5-flash")
    assert "rate_limit_rpm" in gemini_info

    agy_prov = AntigravityProvider()
    agy_info = await agy_prov.get_usage_info("gemini-3.1-pro-high")
    assert "Gemini AI Pro Subscription" in agy_info["tier"]

    opencode_prov = OpenCodeProvider()
    opencode_info = await opencode_prov.get_usage_info()
    assert "Zen Free" in opencode_info["provider"]

