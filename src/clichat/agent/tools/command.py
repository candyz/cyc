import asyncio
from pathlib import Path
from typing import Optional
from clichat.agent.tools.base import Tool

MAX_OUTPUT_CHARS = 25000

class RunCommandTool(Tool):
    name = "run_command"
    description = "Execute a shell command in the local environment and return its stdout, stderr, and exit code."
    is_mutation = True
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command line to execute.",
            },
            "cwd": {
                "type": "string",
                "description": "Optional working directory in which to execute the command.",
            },
            "timeout": {
                "type": "integer",
                "description": "Maximum execution time in seconds (default: 60).",
            },
        },
        "required": ["command"],
    }

    async def execute(self, command: str, cwd: Optional[str] = None, timeout: int = 60, **kwargs) -> str:
        work_dir = Path(cwd).expanduser().resolve() if cwd else Path.cwd()
        if not work_dir.exists() or not work_dir.is_dir():
            return f"Error: Working directory '{work_dir}' does not exist."

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(work_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_data, stderr_data = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
                return f"Error: Command '{command}' timed out after {timeout} seconds."

            stdout_str = stdout_data.decode("utf-8", errors="replace").strip()
            stderr_str = stderr_data.decode("utf-8", errors="replace").strip()

            combined = []
            if stdout_str:
                combined.append(stdout_str)
            if stderr_str:
                combined.append(f"[stderr]\n{stderr_str}")

            full_output = "\n\n".join(combined) if combined else "[No output]"

            if len(full_output) > MAX_OUTPUT_CHARS:
                full_output = full_output[:MAX_OUTPUT_CHARS] + f"\n\n[Note: Output truncated at {MAX_OUTPUT_CHARS} characters]"

            return f"Exit Code: {proc.returncode}\n\n{full_output}"

        except Exception as e:
            return f"Error executing command '{command}': {e}"
