import asyncio
import pytest
from cyc.agent.tasks import TaskManager
from cyc.agent.tools.tasks import TaskTool

@pytest.mark.asyncio
async def test_task_manager_lifecycle():
    mgr = TaskManager()
    # 1. Start task
    tid = await mgr.start_task("python3 -c \"import time; print('hello from task'); time.sleep(0.1); print('task done')\"")
    assert tid.startswith("task-")

    # 2. List tasks
    tasks = mgr.list_tasks()
    assert len(tasks) == 1
    assert tasks[0]["task_id"] == tid

    # 3. Wait a moment for output
    await asyncio.sleep(0.3)
    out = mgr.get_task_output(tid)
    assert out is not None
    assert "hello from task" in out
    assert "task done" in out

@pytest.mark.asyncio
async def test_task_manager_stop():
    mgr = TaskManager()
    tid = await mgr.start_task("python3 -c \"import time; time.sleep(10)\"")
    tasks = mgr.list_tasks()
    assert any(t["task_id"] == tid for t in tasks)

    stopped = await mgr.stop_task(tid)
    assert stopped is True

@pytest.mark.asyncio
async def test_task_tool_actions():
    mgr = TaskManager()
    tool = TaskTool(task_manager=mgr)

    # Start
    res_start = await tool.execute(action="start", command="echo 'tool task execution'")
    assert "Background task started successfully with ID:" in res_start
    tid = res_start.split("ID: ")[1].split("\n")[0].strip()

    await asyncio.sleep(0.2)

    # Output
    res_out = await tool.execute(action="output", task_id=tid)
    assert "tool task execution" in res_out

    # List
    res_list = await tool.execute(action="list")
    assert tid in res_list

    # Stop invalid or completed
    res_stop = await tool.execute(action="stop", task_id="nonexistent-id")
    assert "Error: Could not terminate" in res_stop
