import pytest
from typing import AsyncGenerator, List, Dict, Any, Optional

from clichat.agent.loop import AgentLoop
from clichat.agent.permissions import PermissionManager, PermissionMode
from clichat.agent.tools import ToolRegistry, ReadFileTool, WriteFileTool
from clichat.providers.base import BaseProvider, AgentTurnResponse, ToolCallRequest
from clichat.session import SessionManager


class MockAgentProvider(BaseProvider):
    def __init__(self, responses: List[AgentTurnResponse]):
        self.responses = list(responses)
        self.call_count = 0

    async def chat(self, messages: List[Dict[str, str]], model: str, **kwargs) -> str:
        return "mock chat"

    async def chat_stream(self, messages: List[Dict[str, str]], model: str, **kwargs) -> AsyncGenerator[str, None]:
        yield "mock stream"

    async def list_models(self) -> List[str]:
        return ["mock-model"]

    async def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> AgentTurnResponse:
        resp = self.responses[self.call_count]
        self.call_count += 1
        return resp


@pytest.mark.asyncio
async def test_agent_loop_direct_answer():
    provider = MockAgentProvider([
        AgentTurnResponse(content="Hello! How can I help you today?", tool_calls=[]),
    ])
    session = SessionManager()
    loop = AgentLoop(
        provider=provider,
        model="mock-model",
        session=session,
        permission_manager=PermissionManager(PermissionMode.AUTO),
    )

    final_ans = await loop.run_turn("Hi")
    assert final_ans == "Hello! How can I help you today!" or "help you today" in final_ans
    assert provider.call_count == 1
    # Check messages
    assert len(session.messages) == 2
    assert session.messages[0]["role"] == "user"
    assert session.messages[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_agent_loop_tool_execution(tmp_path):
    test_file = tmp_path / "hello.txt"
    test_file.write_text("file content hello world", encoding="utf-8")

    provider = MockAgentProvider([
        # Turn 1: Model calls read_file
        AgentTurnResponse(
            content="Let me read the file.",
            tool_calls=[
                ToolCallRequest(
                    id="call_123",
                    name="read_file",
                    arguments={"path": str(test_file)},
                )
            ],
        ),
        # Turn 2: Model answers based on observation
        AgentTurnResponse(
            content="The file contains: file content hello world",
            tool_calls=[],
        ),
    ])

    registry = ToolRegistry([ReadFileTool(), WriteFileTool()])
    session = SessionManager()
    loop = AgentLoop(
        provider=provider,
        model="mock-model",
        session=session,
        tool_registry=registry,
        permission_manager=PermissionManager(PermissionMode.AUTO),
    )

    final_ans = await loop.run_turn("What is in hello.txt?")
    assert "file content hello world" in final_ans
    assert provider.call_count == 2
    # Check session messages: user -> assistant (tool_calls) -> tool observation -> assistant final
    roles = [m["role"] for m in session.messages]
    assert roles == ["user", "assistant", "tool", "assistant"]
    assert "file content hello world" in session.messages[2]["content"]


@pytest.mark.asyncio
async def test_agent_loop_truncates_oversized_tool_output(tmp_path):
    # Create an oversized file with 500 lines
    huge_file = tmp_path / "huge.txt"
    huge_file.write_text("\n".join(f"ROW_{i}" for i in range(500)), encoding="utf-8")

    provider = MockAgentProvider([
        AgentTurnResponse(
            content="Reading huge file",
            tool_calls=[
                ToolCallRequest(
                    id="call_huge",
                    name="read_file",
                    arguments={"path": str(huge_file), "end_line": 500},
                )
            ],
        ),
        AgentTurnResponse(
            content="Finished inspecting.",
            tool_calls=[],
        ),
    ])

    registry = ToolRegistry([ReadFileTool()])
    session = SessionManager()
    loop = AgentLoop(
        provider=provider,
        model="mock-model",
        session=session,
        tool_registry=registry,
        permission_manager=PermissionManager(PermissionMode.AUTO),
    )

    await loop.run_turn("Inspect huge file")
    # Tool output in session should be truncated
    tool_msg = session.messages[2]
    assert tool_msg["role"] == "tool"
    assert "... [Output truncated:" in tool_msg["content"] or "[Note: Output truncated" in tool_msg["content"]
