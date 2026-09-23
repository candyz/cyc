from typing import Any, Dict, Optional
from cyc.agent.tasks import TaskManager
from cyc.agent.tools.base import Tool

class TaskTool(Tool):
    """Tool to manage background asynchronous tasks (start, list, output, stop)."""
    name: str = "manage_task"
    description: str = (
        "Manage asynchronous background tasks for long-running processes (e.g. servers, long test suites, builds). "
        "Actions: 'start' (launch command in background), 'list' (list all background tasks), "
        "'output' (view recent logs of a task), 'stop' (terminate a task)."
    )
    is_mutation: bool = True
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["start", "list", "output", "stop"],
                "description": "Action to perform: 'start', 'list', 'output', or 'stop'.",
            },
            "command": {
                "type": "string",
                "description": "Shell command to run in background (required for action='start').",
            },
            "task_id": {
                "type": "string",
                "description": "Target task identifier (required for action='output' or 'stop').",
            },
            "cwd": {
                "type": "string",
                "description": "Optional working directory for the background task.",
            },
            "tail_lines": {
                "type": "integer",
                "description": "Number of log lines to retrieve (default: 50, for action='output').",
            },
        },
        "required": ["action"],
    }

    def __init__(self, task_manager: Optional[TaskManager] = None):
        self.task_manager = task_manager or TaskManager.get_instance()

    async def execute(
        self,
        action: str,
        command: Optional[str] = None,
        task_id: Optional[str] = None,
        cwd: Optional[str] = None,
        tail_lines: int = 50,
        **kwargs,
    ) -> str:
        action = action.lower().strip()

        if action == "start":
            if not command:
                return "Error: 'command' argument is required for action='start'."
            tid = await self.task_manager.start_task(command=command, cwd=cwd)
            return (
                f"Background task started successfully with ID: {tid}\n"
                f"Command: {command}\n"
                f"Use `manage_task(action='output', task_id='{tid}')` to view output or `manage_task(action='list')` to check status."
            )

        elif action == "list":
            tasks = self.task_manager.list_tasks()
            if not tasks:
                return "No background tasks currently active or recorded."
            lines = ["Current Background Tasks:"]
            for t in tasks:
                lines.append(f"- ID: {t['task_id']} | Status: {t['status']} | Started: {t['started']} | Command: {t['command']}")
            return "\n".join(lines)

        elif action == "output":
            if not task_id:
                return "Error: 'task_id' argument is required for action='output'."
            out = self.task_manager.get_task_output(task_id=task_id, tail_lines=tail_lines)
            if out is None:
                return f"Error: Task '{task_id}' not found."
            return out

        elif action == "stop":
            if not task_id:
                return "Error: 'task_id' argument is required for action='stop'."
            stopped = await self.task_manager.stop_task(task_id=task_id)
            if stopped:
                return f"Task '{task_id}' was successfully terminated."
            return f"Error: Could not terminate task '{task_id}'. It may not exist or has already completed."

        else:
            return f"Error: Unknown action '{action}'. Supported actions: 'start', 'list', 'output', 'stop'."
