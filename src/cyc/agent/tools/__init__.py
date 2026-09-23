from typing import Dict, List, Optional
from cyc.agent.tools.base import Tool, truncate_tool_output, enrich_tool_error_observation
from cyc.agent.tools.filesystem import (
    ReadFileTool,
    WriteFileTool,
    ReplaceFileContentTool,
    ListDirTool,
)
from cyc.agent.tools.command import RunCommandTool, RunScriptTool
from cyc.agent.tools.search import GrepSearchTool
from cyc.agent.tools.web import WebSearchTool, FetchUrlTool
from cyc.agent.tools.interaction import AskUserTool
from cyc.agent.tools.repomap import RepoMapTool
from cyc.agent.tools.tasks import TaskTool
from cyc.agent.tools.subagent import SubagentTool

def get_default_tools(searxng_url: Optional[str] = None) -> List[Tool]:
    """Return an instantiated list of all 13 core built-in tools."""
    return [
        ReadFileTool(),
        WriteFileTool(),
        ReplaceFileContentTool(),
        RunCommandTool(),
        RunScriptTool(),
        ListDirTool(),
        GrepSearchTool(),
        WebSearchTool(searxng_url=searxng_url),
        FetchUrlTool(),
        AskUserTool(),
        RepoMapTool(),
        TaskTool(),
        SubagentTool(),
    ]

class ToolRegistry:
    """Registry to manage available tools, lookup by name, and export to API schemas."""
    def __init__(self, tools: List[Tool] = None):
        self._tools: Dict[str, Tool] = {}
        for t in (tools or get_default_tools()):
            self.register(t)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered.")
        return self._tools[name]

    def all_tools(self) -> List[Tool]:
        return list(self._tools.values())

    def to_openai_tools(self) -> List[dict]:
        return [t.to_openai_tool() for t in self._tools.values()]

    def to_gemini_tools(self) -> List[dict]:
        return [t.to_gemini_tool() for t in self._tools.values()]

__all__ = [
    "Tool",
    "truncate_tool_output",
    "enrich_tool_error_observation",
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
    "AskUserTool",
    "RepoMapTool",
    "TaskTool",
    "SubagentTool",
]
