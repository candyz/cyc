"""Agent module for clichat - Autonomous coding agent capabilities."""

from clichat.agent.tools.base import Tool
from clichat.agent.tools import (
    ToolRegistry,
    get_default_tools,
    ReadFileTool,
    WriteFileTool,
    ReplaceFileContentTool,
    RunCommandTool,
    RunScriptTool,
    ListDirTool,
    GrepSearchTool,
)
from clichat.agent.permissions import PermissionManager, PermissionMode
from clichat.agent.prompt import build_coding_agent_system_prompt
from clichat.agent.loop import AgentLoop
from clichat.agent.trust import WorkspaceTrustManager
from clichat.agent.mcp import StdioMCPClient, MCPDynamicTool
from clichat.agent.skills import SkillManager

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
    "PermissionManager",
    "PermissionMode",
    "build_coding_agent_system_prompt",
    "AgentLoop",
    "WorkspaceTrustManager",
    "StdioMCPClient",
    "MCPDynamicTool",
    "SkillManager",
]
