"""MCP (Model Context Protocol) Client and Dynamic Tool Adapter for cyc.
Supports stdio-based MCP servers using standard JSON-RPC 2.0 protocol.
"""

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console

from cyc.agent.tools.base import Tool

console = Console()


class StdioMCPClient:
    """Lightweight asynchronous stdio MCP client implementing JSON-RPC 2.0."""

    def __init__(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.cwd = cwd
        self.proc: Optional[asyncio.subprocess.Process] = None
        self._req_id = 0
        self._lock = asyncio.Lock()

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    async def start(self) -> bool:
        """Spawn the MCP server process and perform the initialize handshake."""
        full_env = dict(os.environ)
        full_env.update(self.env)

        # Check command exists
        cmd_path = shutil.which(self.command)
        if not cmd_path and not Path(self.command).exists():
            return False

        try:
            cmd = [self.command] + self.args
            work_dir = self.cwd or str(Path.cwd())
            self.proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=full_env,
                cwd=work_dir,
            )

            # Perform initialize request
            init_req = {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "roots": {"listChanged": True},
                        "sampling": {},
                    },
                    "clientInfo": {
                        "name": "cyc",
                        "version": "0.2.11",
                    },
                },
            }

            resp = await self._send_request(init_req)
            if not resp or "error" in resp:
                return False

            # Send initialized notification
            notif = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
            await self._send_notification(notif)
            return True

        except Exception:
            return False

    async def _send_notification(self, notif: Dict[str, Any]) -> None:
        if not self.proc or not self.proc.stdin:
            return
        payload = json.dumps(notif) + "\n"
        self.proc.stdin.write(payload.encode("utf-8"))
        await self.proc.stdin.drain()

    async def _send_request(self, req: Dict[str, Any], timeout: float = 15.0) -> Optional[Dict[str, Any]]:
        if not self.proc or not self.proc.stdin or not self.proc.stdout:
            return None

        async with self._lock:
            payload = json.dumps(req) + "\n"
            self.proc.stdin.write(payload.encode("utf-8"))
            await self.proc.stdin.drain()

            try:
                line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=timeout)
                if not line:
                    return None
                return json.loads(line.decode("utf-8", errors="replace"))
            except (asyncio.TimeoutError, Exception):
                return None

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Fetch available tools from the MCP server using tools/list."""
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
            "params": {},
        }
        resp = await self._send_request(req)
        if resp and "result" in resp:
            return resp["result"].get("tools", [])
        return []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool on the MCP server using tools/call."""
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        resp = await self._send_request(req, timeout=60.0)
        if not resp:
            return f"Error: MCP server '{self.name}' did not respond."
        if "error" in resp:
            err = resp["error"]
            return f"MCP Error ({err.get('code', 'unknown')}): {err.get('message', 'Unknown error')}"

        result = resp.get("result", {})
        content_items = result.get("content", [])
        texts = []
        for item in content_items:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    texts.append(item.get("text", ""))
                else:
                    texts.append(json.dumps(item, ensure_ascii=False))
            else:
                texts.append(str(item))

        return "\n".join(texts) if texts else json.dumps(result, ensure_ascii=False)

    async def stop(self) -> None:
        """Gracefully terminate the MCP server process."""
        if self.proc:
            try:
                self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), timeout=2.0)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None


class MCPDynamicTool(Tool):
    """Bridge adapter that wraps an MCP server tool as a native cyc Tool."""

    def __init__(
        self,
        server_name: str,
        mcp_client: StdioMCPClient,
        tool_data: Dict[str, Any],
    ):
        self.server_name = server_name
        self.mcp_client = mcp_client
        self.mcp_tool_name = tool_data.get("name", "")
        # Prefix with server name to avoid collision: e.g. mcp__github__create_issue
        self.name = f"mcp__{server_name}__{self.mcp_tool_name}"
        self.description = f"[{server_name} MCP] " + tool_data.get("description", "")
        schema = tool_data.get("inputSchema", {})
        self.parameters = schema if isinstance(schema, dict) and "type" in schema else {
            "type": "object",
            "properties": schema.get("properties", {}),
            "required": schema.get("required", []),
        }
        # Assume MCP tools can be mutations unless explicitly stated otherwise
        self.is_mutation = True

    async def execute(self, **kwargs) -> str:
        return await self.mcp_client.call_tool(self.mcp_tool_name, kwargs)
