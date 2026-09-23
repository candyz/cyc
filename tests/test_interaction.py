import pytest
from cyc.agent.tools.interaction import AskUserTool

@pytest.mark.asyncio
async def test_ask_user_tool_schema():
    tool = AskUserTool()
    assert tool.name == "ask_user"
    assert tool.is_mutation is False
    assert "question" in tool.parameters["properties"]
    assert "options" in tool.parameters["properties"]
    assert "multi_select" in tool.parameters["properties"]

@pytest.mark.asyncio
async def test_ask_user_tool_with_handler():
    # Sync handler
    def mock_sync_handler(question, options=None, multi_select=False):
        return f"Handler handled: {question}"

    tool = AskUserTool(interaction_handler=mock_sync_handler)
    res = await tool.execute(question="Which database?")
    assert res == "Handler handled: Which database?"

    # Async handler
    async def mock_async_handler(question, options=None, multi_select=False):
        return f"Async answered: {options[0] if options else 'none'}"

    tool_async = AskUserTool(interaction_handler=mock_async_handler)
    res_async = await tool_async.execute(question="Pick one", options=["PostgreSQL", "SQLite"])
    assert res_async == "Async answered: PostgreSQL"

@pytest.mark.asyncio
async def test_ask_user_non_interactive_fallback(monkeypatch):
    import sys
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    tool = AskUserTool()
    res = await tool.execute(question="Select approach", options=["Option A", "Option B"])
    assert "Selected default option: Option A" in res

    res_no_opts = await tool.execute(question="Why?")
    assert "User interaction not available" in res_no_opts
