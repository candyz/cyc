import asyncio
import os
import signal
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

@dataclass
class BackgroundTask:
    task_id: str
    command: str
    cwd: str
    process: asyncio.subprocess.Process
    start_time: datetime = field(default_factory=datetime.now)
    output_buffer: List[str] = field(default_factory=list)
    exit_code: Optional[int] = None
    is_done: bool = False

    def get_status_str(self) -> str:
        if not self.is_done:
            return "running"
        return f"exited ({self.exit_code})"

class TaskManager:
    """Manages asynchronous long-running background tasks."""
    _instance: Optional["TaskManager"] = None

    def __init__(self):
        self._tasks: Dict[str, BackgroundTask] = {}
        self._counter: int = 1

    @classmethod
    def get_instance(cls) -> "TaskManager":
        if cls._instance is None:
            cls._instance = TaskManager()
        return cls._instance

    async def start_task(self, command: str, cwd: Optional[str] = None) -> str:
        """Start a shell command in the background and return task_id."""
        work_dir = Path(cwd).expanduser().resolve() if cwd else Path.cwd()
        task_id = f"task-{self._counter}"
        self._counter += 1

        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        task = BackgroundTask(
            task_id=task_id,
            command=command,
            cwd=str(work_dir),
            process=proc,
        )
        self._tasks[task_id] = task

        # Launch async reader loop in background
        asyncio.create_task(self._monitor_task(task))
        return task_id

    async def _monitor_task(self, task: BackgroundTask):
        """Asynchronously read stdout/stderr lines from process into output_buffer."""
        async def read_stream(stream, prefix=""):
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                task.output_buffer.append(f"{prefix}{decoded}" if prefix else decoded)
                if len(task.output_buffer) > 1000:
                    task.output_buffer.pop(0)

        await asyncio.gather(
            read_stream(task.process.stdout),
            read_stream(task.process.stderr, prefix="[stderr] "),
        )
        await task.process.wait()
        task.exit_code = task.process.returncode
        task.is_done = True

    def list_tasks(self) -> List[Dict[str, str]]:
        """Return list of summary info for all tasks."""
        results = []
        for t in self._tasks.values():
            results.append({
                "task_id": t.task_id,
                "command": t.command,
                "status": t.get_status_str(),
                "started": t.start_time.strftime("%H:%M:%S"),
                "lines_buffered": str(len(t.output_buffer)),
            })
        return results

    def get_task_output(self, task_id: str, tail_lines: int = 50) -> Optional[str]:
        """Get the recent stdout/stderr output lines from the task."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        recent_lines = task.output_buffer[-tail_lines:] if task.output_buffer else ["[No output yet]"]
        header = f"Task: {task.task_id} | Status: {task.get_status_str()} | Command: {task.command}"
        return f"{header}\n\n" + "\n".join(recent_lines)

    async def stop_task(self, task_id: str) -> bool:
        """Kill or terminate a running task."""
        task = self._tasks.get(task_id)
        if not task or task.is_done:
            return False
        try:
            task.process.terminate()
            try:
                await asyncio.wait_for(task.process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                task.process.kill()
                await task.process.wait()
            task.is_done = True
            task.exit_code = -1
            return True
        except Exception:
            return False
