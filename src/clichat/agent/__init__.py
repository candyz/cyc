"""Agent module for clichat - Autonomous coding agent capabilities."""

from clichat.agent.tools.base import Tool
from clichat.agent.tools import (
    ToolRegistry,
    get_default_tools,
    ReadFileTool,
    WriteFileTool,
    ReplaceFileContentTool,
    RunCommandTool,
    ListDirTool,
    GrepSearchTool,
)
from clichat.agent.permissions import PermissionManager, PermissionMode
from clichat.agent.prompt import build_coding_agent_system_prompt
from clichat.agent.loop import AgentLoop
from clichat.agent.trust import WorkspaceTrustManager

__all__ = [
    "Tool",
    "ToolRegistry",
    "get_default_tools",
    "ReadFileTool",
    "WriteFileTool",
    "ReplaceFileContentTool",
    "RunCommandTool",
    "ListDirTool",
    "GrepSearchTool",
    "PermissionManager",
    "PermissionMode",
    "build_coding_agent_system_prompt",
    "AgentLoop",
    "WorkspaceTrustManager",
]
