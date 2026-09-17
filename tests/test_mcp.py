import asyncio
import json
import pytest
from pathlib import Path
from clichat.agent.mcp import StdioMCPClient, MCPDynamicTool
from clichat.agent.tools import ToolRegistry
from clichat.config import Config, MCPServerConfig

@pytest.mark.asyncio
async def test_mcp_stdio_client_and_dynamic_tool(tmp_path: Path):
    # Create a small mock MCP server script using python
    mock_server_script = tmp_path / "mock_mcp_server.py"
    mock_server_script.write_text("""import sys, json

def main():
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        req = json.loads(line)
        method = req.get("method")
        msg_id = req.get("id")

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "mock-mcp", "version": "1.0.0"},
                    "capabilities": {"tools": {}}
                }
            }
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": [
                        {
                            "name": "calc_add",
                            "description": "Add two numbers",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "a": {"type": "integer"},
                                    "b": {"type": "integer"}
                                },
                                "required": ["a", "b"]
                            }
                        }
                    ]
                }
            }
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
        elif method == "tools/call":
            params = req.get("params", {})
            t_name = params.get("name")
            args = params.get("arguments", {})
            if t_name == "calc_add":
                total = args.get("a", 0) + args.get("b", 0)
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": f"Result: {total}"}
                        ]
                    }
                }
                sys.stdout.write(json.dumps(resp) + "\\n")
                sys.stdout.flush()

if __name__ == "__main__":
    main()
""")

    client = StdioMCPClient(
        name="test_calc",
        command="python3",
        args=[str(mock_server_script)],
    )

    started = await client.start()
    assert started is True

    # Test list_tools
    tools = await client.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "calc_add"

    # Wrap into MCPDynamicTool
    dynamic_tool = MCPDynamicTool(
        server_name="test_calc",
        mcp_client=client,
        tool_data=tools[0],
    )
    assert dynamic_tool.name == "mcp__test_calc__calc_add"
    assert "[test_calc MCP]" in dynamic_tool.description

    # Test execution
    res = await dynamic_tool.execute(a=12, b=8)
    assert "Result: 20" in res

    # Register into ToolRegistry
    registry = ToolRegistry()
    registry.register(dynamic_tool)
    assert registry.get("mcp__test_calc__calc_add") is dynamic_tool
    openai_schemas = registry.to_openai_tools()
    assert any(s["function"]["name"] == "mcp__test_calc__calc_add" for s in openai_schemas)

    await client.stop()

def test_mcp_config_parsing():
    raw = {
        "default_provider": "ollama",
        "mcp_servers": {
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "env": {"DEBUG": "1"},
            }
        }
    }
    cfg = Config.model_validate(raw)
    assert "fetch" in cfg.mcp_servers
    assert cfg.mcp_servers["fetch"].command == "uvx"
    assert cfg.mcp_servers["fetch"].args == ["mcp-server-fetch"]
    assert cfg.mcp_servers["fetch"].env["DEBUG"] == "1"
