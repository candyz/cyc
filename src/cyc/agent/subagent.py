import asyncio
from typing import Any, Dict, List, Optional
from cyc.agent.permissions import PermissionManager, PermissionMode
from cyc.agent.prompt import build_coding_agent_system_prompt
from cyc.agent.tools.filesystem import ReadFileTool, ListDirTool
from cyc.agent.tools.search import GrepSearchTool
from cyc.agent.tools.web import WebSearchTool, FetchUrlTool
from cyc.agent.tools.repomap import RepoMapTool
from cyc.providers.base import BaseProvider
from cyc.session import SessionManager

SUBAGENT_ROLES = {
    "researcher": (
        "You are a specialized Codebase & Web Researcher Subagent.\n"
        "Your task is to explore code files, search documentation, extract relevant snippets, "
        "and return a concise, factual summary or answer. Do NOT edit files or run mutating commands."
    ),
    "tester": (
        "You are a specialized Quality Assurance & Testing Subagent.\n"
        "Your task is to analyze test files, identify edge cases, inspect test results, and formulate testing plans."
    ),
    "planner": (
        "You are a specialized Architectural Planning Subagent.\n"
        "Your task is to review requirements, assess project architecture, and produce structured, step-by-step execution plans."
    ),
}

class SubagentRunner:
    """Spawns an isolated subagent in a child session to execute focused tasks without polluting parent context."""

    def __init__(self, provider: BaseProvider, default_model: str):
        self.provider = provider
        self.default_model = default_model

    async def run(
        self,
        task: str,
        role: str = "researcher",
        model: Optional[str] = None,
        max_turns: int = 10,
    ) -> str:
        from cyc.agent.loop import AgentLoop

        role_desc = SUBAGENT_ROLES.get(role.lower(), SUBAGENT_ROLES["researcher"])
        system_prompt = (
            f"{role_desc}\n\n"
            f"Focus solely on the user's delegated task:\n"
            f"{task}\n\n"
            "Return a clear, well-structured response when done."
        )

        child_session = SessionManager()
        child_session.set_system_prompt(system_prompt)

        # Build specialized read-only tool registry for subagent
        from cyc.agent.tools import ToolRegistry
        child_registry = ToolRegistry(tools=[
            ReadFileTool(),
            ListDirTool(),
            GrepSearchTool(),
            WebSearchTool(),
            FetchUrlTool(),
            RepoMapTool(),
        ])

        # Auto permission mode for read-only tools
        child_permission = PermissionManager(mode=PermissionMode.AUTO)

        sub_loop = AgentLoop(
            provider=self.provider,
            model=model or self.default_model,
            session=child_session,
            tool_registry=child_registry,
            permission_manager=child_permission,
            max_turns=max_turns,
        )

        result = await sub_loop.run_turn(f"[Delegated Subagent Task]: {task}")
        return result
