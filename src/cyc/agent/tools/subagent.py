from typing import Any, Dict, Optional
from cyc.agent.subagent import SubagentRunner, SUBAGENT_ROLES
from cyc.agent.tools.base import Tool

class SubagentTool(Tool):
    """Tool that allows the agent to delegate subtasks to an isolated child agent."""
    name: str = "invoke_subagent"
    description: str = (
        "Invoke a specialized subagent to perform an isolated subtask (such as deep codebase research, "
        "documentation lookup, architecture planning, or test case analysis) in a separate context window. "
        "Keeps the main conversation context clean while delegating multi-step exploration."
    )
    is_mutation: bool = False
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Specific task or question for the subagent to research and resolve.",
            },
            "role": {
                "type": "string",
                "enum": list(SUBAGENT_ROLES.keys()),
                "description": "Role of the subagent: 'researcher', 'tester', or 'planner' (default: 'researcher').",
            },
            "model": {
                "type": "string",
                "description": "Optional model override for the subagent (e.g. a faster or cheaper model).",
            },
            "max_turns": {
                "type": "integer",
                "description": "Maximum turns for the subagent to run (default: 10).",
            },
        },
        "required": ["task"],
    }

    def __init__(self, runner: Optional[SubagentRunner] = None):
        self.runner = runner

    def set_runner(self, runner: SubagentRunner) -> None:
        self.runner = runner

    async def execute(
        self,
        task: str,
        role: str = "researcher",
        model: Optional[str] = None,
        max_turns: int = 10,
        **kwargs,
    ) -> str:
        if not self.runner:
            return "Error: SubagentRunner is not configured for invoke_subagent tool."

        try:
            result = await self.runner.run(
                task=task,
                role=role,
                model=model,
                max_turns=max_turns,
            )
            return f"[Subagent ({role}) Output]:\n{result}"
        except Exception as e:
            return f"Error executing subagent ({role}): {e}"
