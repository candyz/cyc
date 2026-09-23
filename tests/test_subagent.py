import pytest
from unittest.mock import AsyncMock, MagicMock
from cyc.agent.subagent import SubagentRunner, SUBAGENT_ROLES
from cyc.agent.tools.subagent import SubagentTool
from cyc.providers.base import AgentTurnResponse

@pytest.mark.asyncio
async def test_subagent_tool_schema():
    tool = SubagentTool()
    assert tool.name == "invoke_subagent"
    assert tool.is_mutation is False
    assert "task" in tool.parameters["properties"]
    assert "role" in tool.parameters["properties"]

@pytest.mark.asyncio
async def test_subagent_tool_execution():
    mock_runner = MagicMock()
    mock_runner.run = AsyncMock(return_value="Analysis report: everything looks good.")

    tool = SubagentTool(runner=mock_runner)
    res = await tool.execute(task="Inspect project architecture", role="planner")
    assert "[Subagent (planner) Output]:" in res
    assert "Analysis report: everything looks good." in res
    mock_runner.run.assert_awaited_once_with(
        task="Inspect project architecture",
        role="planner",
        model=None,
        max_turns=10,
    )

@pytest.mark.asyncio
async def test_subagent_runner_invocation():
    mock_provider = MagicMock()
    mock_provider.chat_with_tools = AsyncMock(
        return_value=AgentTurnResponse(
            content="Summary of research findings.",
            tool_calls=[],
        )
    )

    runner = SubagentRunner(provider=mock_provider, default_model="test-model")
    res = await runner.run(task="Find all instances of Foo", role="researcher")
    assert "Summary of research findings." in res
