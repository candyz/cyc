"""Agent module for cyc - Autonomous coding agent capabilities."""

from cyc.agent.tools.base import Tool
from cyc.agent.tools import (
    ToolRegistry,
    get_default_tools,
    ReadFileTool,
    WriteFileTool,
    ReplaceFileContentTool,
    RunCommandTool,
    RunScriptTool,
    ListDirTool,
    GrepSearchTool,
    WebSearchTool,
    FetchUrlTool,
)
from cyc.agent.permissions import PermissionManager, PermissionMode
from cyc.agent.prompt import build_coding_agent_system_prompt
from cyc.agent.loop import AgentLoop
from cyc.agent.trust import WorkspaceTrustManager
from cyc.agent.mcp import StdioMCPClient, MCPDynamicTool
from cyc.agent.skills import SkillManager

__all__ = [
    "Tool",
    "ToolRegistry",
    "get_default_tools",
    "ReadFileTool",
    "WriteFileTool",
    "ReplaceFileContentTool",
    "RunCommandTool",
    "RunScriptTool",
    "ListDirTool",
    "GrepSearchTool",
    "WebSearchTool",
    "FetchUrlTool",
    "PermissionManager",
    "PermissionMode",
    "build_coding_agent_system_prompt",
    "AgentLoop",
    "WorkspaceTrustManager",
    "StdioMCPClient",
    "MCPDynamicTool",
    "SkillManager",
]
