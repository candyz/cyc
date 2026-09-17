from typing import Dict, List
from clichat.agent.tools.base import Tool
from clichat.agent.tools.filesystem import (
    ReadFileTool,
    WriteFileTool,
    ReplaceFileContentTool,
    ListDirTool,
)
from clichat.agent.tools.command import RunCommandTool
from clichat.agent.tools.search import GrepSearchTool

def get_default_tools() -> List[Tool]:
    """Return an instantiated list of all 6 core built-in tools."""
    return [
        ReadFileTool(),
        WriteFileTool(),
        ReplaceFileContentTool(),
        RunCommandTool(),
        ListDirTool(),
        GrepSearchTool(),
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
    "ToolRegistry",
    "get_default_tools",
    "ReadFileTool",
    "WriteFileTool",
    "ReplaceFileContentTool",
    "RunCommandTool",
    "ListDirTool",
    "GrepSearchTool",
]
