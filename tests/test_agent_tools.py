import pytest
from pathlib import Path
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

@pytest.mark.asyncio
async def test_read_and_write_file(tmp_path: Path):
    write_tool = WriteFileTool()
    read_tool = ReadFileTool()

    target_file = tmp_path / "sub" / "test.txt"
    content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"

    # Test writing file
    write_res = await write_tool.execute(str(target_file), content)
    assert "Successfully wrote" in write_res
    assert target_file.exists()

    # Test reading full file
    read_full = await read_tool.execute(str(target_file))
    assert "Line 1" in read_full
    assert "Line 5" in read_full

    # Test reading line range (lines 2 to 4)
    read_slice = await read_tool.execute(str(target_file), start_line=2, end_line=4)
    assert "Line 2" in read_slice
    assert "Line 4" in read_slice
    assert "Line 1" not in read_slice
    assert "Line 5" not in read_slice

    # Test non-existent file
    error_res = await read_tool.execute(str(tmp_path / "nonexistent.txt"))
    assert "Error:" in error_res

@pytest.mark.asyncio
async def test_replace_file_content(tmp_path: Path):
    replace_tool = ReplaceFileContentTool()
    target_file = tmp_path / "replace_test.py"
    target_file.write_text("def hello():\n    return 'old'\n", encoding="utf-8")

    # Successful replacement
    res = await replace_tool.execute(str(target_file), target="return 'old'", replacement="return 'new'")
    assert "Successfully replaced" in res
    assert "return 'new'" in target_file.read_text(encoding="utf-8")

    # Target not found
    err_not_found = await replace_tool.execute(str(target_file), target="not_there", replacement="foo")
    assert "Error: Target text not found" in err_not_found

    # Multiple occurrences
    target_file.write_text("dup dup", encoding="utf-8")
    err_dup = await replace_tool.execute(str(target_file), target="dup", replacement="bar")
    assert "Error: Target text found 2 times" in err_dup

@pytest.mark.asyncio
async def test_run_command(tmp_path: Path):
    cmd_tool = RunCommandTool()

    res = await cmd_tool.execute("echo 'Hello Agent'", cwd=str(tmp_path))
    assert "Exit Code: 0" in res
    assert "Hello Agent" in res

    # Timeout test
    timeout_res = await cmd_tool.execute("sleep 2", timeout=1)
    assert "timed out after 1 seconds" in timeout_res

    # Truncation test
    trunc_res = await cmd_tool.execute("python3 -c \"for i in range(350): print(f'Line {i}')\"", cwd=str(tmp_path))
    assert "truncated to first 250 lines" in trunc_res

@pytest.mark.asyncio
async def test_list_dir(tmp_path: Path):
    list_tool = ListDirTool()

    (tmp_path / "folder_a").mkdir()
    (tmp_path / "folder_a" / "file1.txt").write_text("a")
    (tmp_path / ".git").mkdir()  # Ignored dir
    (tmp_path / ".git" / "ignored.txt").write_text("git")

    res = await list_tool.execute(str(tmp_path), max_depth=2)
    assert "folder_a/" in res
    assert "file1.txt" in res
    assert ".git" not in res

@pytest.mark.asyncio
async def test_grep_search(tmp_path: Path):
    grep_tool = GrepSearchTool()

    f1 = tmp_path / "test1.py"
    f1.write_text("def special_function_foo():\n    pass\n")

    f2 = tmp_path / "test2.txt"
    f2.write_text("nothing here\n")

    res = await grep_tool.execute(pattern="special_function_foo", path=str(tmp_path))
    assert "special_function_foo" in res
    assert "test1.py" in res

def test_tool_registry():
    registry = ToolRegistry()
    assert len(registry.all_tools()) == 6

    openai_tools = registry.to_openai_tools()
    assert len(openai_tools) == 6
    names = [t["function"]["name"] for t in openai_tools]
    assert "read_file" in names
    assert "write_file" in names
    assert "run_command" in names

    gemini_tools = registry.to_gemini_tools()
    assert len(gemini_tools) == 6
    gemini_names = [t["name"] for t in gemini_tools]
    assert "replace_file_content" in gemini_names
