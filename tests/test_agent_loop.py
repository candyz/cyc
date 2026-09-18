import pytest
from typing import AsyncGenerator, List, Dict, Any, Optional

from cyc.agent.loop import AgentLoop
from cyc.agent.permissions import PermissionManager, PermissionMode
from cyc.agent.tools import ToolRegistry, ReadFileTool, WriteFileTool
from cyc.providers.base import BaseProvider, AgentTurnResponse, ToolCallRequest
from cyc.session import SessionManager


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


@pytest.mark.asyncio
async def test_agent_loop_graceful_cancellation():
    from cyc.agent.tools.base import Tool

    class HangingTool(Tool):
        name = "hanging_tool"
        description = "A tool that hangs or raises KeyboardInterrupt"
        parameters = {"type": "object", "properties": {}}

        async def execute(self, **kwargs) -> str:
            raise KeyboardInterrupt()

    provider = MockAgentProvider([
        AgentTurnResponse(
            content="Calling hanging tool",
            tool_calls=[
                ToolCallRequest(
                    id="call_hang_1",
                    name="hanging_tool",
                    arguments={},
                )
            ],
        ),
    ])

    registry = ToolRegistry([HangingTool()])
    session = SessionManager()
    loop = AgentLoop(
        provider=provider,
        model="mock-model",
        session=session,
        tool_registry=registry,
        permission_manager=PermissionManager(PermissionMode.AUTO),
    )

    result = await loop.run_turn("Hang now")
    assert result == "[Interrupted by user]"
    # Check that session history is valid and the tool_call was safely sanitized
    assert len(session.messages) == 3
    assert session.messages[0]["role"] == "user"
    assert session.messages[1]["role"] == "assistant"
    assert session.messages[2]["role"] == "tool"
    assert session.messages[2]["tool_call_id"] == "call_hang_1"
    assert "Tool execution cancelled" in session.messages[2]["content"]


def test_session_sanitize_cancelled_state():
    session = SessionManager()
    session.add_user_message("Do something")
    # Simulate assistant message with 2 tool calls
    session.messages.append({
        "role": "assistant",
        "content": "Running tools",
        "tool_calls": [
            {"id": "tc_1", "type": "function", "function": {"name": "tool_a", "arguments": "{}"}},
            {"id": "tc_2", "type": "function", "function": {"name": "tool_b", "arguments": "{}"}},
        ],
    })
    # Tool 1 succeeded, but Tool 2 was interrupted before it could run
    session.add_tool_message("tc_1", "tool_a", "Result of tool 1")

    # Sanitize
    session.sanitize_cancelled_state(cancellation_note="Interrupted by user")

    # Check that tc_2 was filled with a cancelled tool message
    assert len(session.messages) == 4
    assert session.messages[3]["role"] == "tool"
    assert session.messages[3]["tool_call_id"] == "tc_2"
    assert "Tool execution cancelled" in session.messages[3]["content"]


@pytest.mark.asyncio
async def test_agent_loop_enriches_tool_error(tmp_path):
    provider = MockAgentProvider([
        # Turn 1: Model tries to read non-existent file
        AgentTurnResponse(
            content="Reading nonexistent file",
            tool_calls=[
                ToolCallRequest(
                    id="call_err_1",
                    name="read_file",
                    arguments={"path": str(tmp_path / "ghost_file.txt")},
                )
            ],
        ),
        # Turn 2: Model recovers and completes
        AgentTurnResponse(
            content="Acknowledged file does not exist.",
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

    await loop.run_turn("Inspect ghost file")
    # Verify tool message contains diagnostic self-repair hint
    tool_msg = session.messages[2]
    assert tool_msg["role"] == "tool"
    assert "[Diagnostic Self-Repair Hint]" in tool_msg["content"]
    assert "Use `list_dir` to inspect the directory structure" in tool_msg["content"]
