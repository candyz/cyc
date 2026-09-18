import pytest
from pathlib import Path
from cyc.agent.tools import (
    ToolRegistry,
    get_default_tools,
    ReadFileTool,
    WriteFileTool,
    ReplaceFileContentTool,
    RunCommandTool,
    ListDirTool,
    GrepSearchTool,
    WebSearchTool,
    FetchUrlTool,
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
    assert len(registry.all_tools()) == 9

    openai_tools = registry.to_openai_tools()
    assert len(openai_tools) == 9
    names = [t["function"]["name"] for t in openai_tools]
    assert "read_file" in names
    assert "write_file" in names
    assert "run_command" in names
    assert "run_script" in names
    assert "web_search" in names
    assert "fetch_url" in names

    gemini_tools = registry.to_gemini_tools()
    assert len(gemini_tools) == 9
    gemini_names = [t["name"] for t in gemini_tools]
    assert "replace_file_content" in gemini_names
    assert "web_search" in gemini_names
    assert "fetch_url" in gemini_names

@pytest.mark.asyncio
async def test_fetch_url_tool():
    tool = FetchUrlTool()

    # Invalid URL
    res_err = await tool.execute(url="ftp://invalid.com")
    assert "Error: Invalid URL" in res_err

    # Mock fetching valid URL
    sample_html = """
    <html>
        <head><title>Test Page</title><style>body { color: red; }</style></head>
        <body>
            <h1>Documentation Header</h1>
            <p>This is a paragraph with <a href="#">link</a>.</p>
            <script>console.log("ignore me");</script>
        </body>
    </html>
    """
    from unittest.mock import patch, MagicMock

    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
    mock_resp.read = MagicMock(return_value=sample_html.encode("utf-8"))
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = await tool.execute(url="https://example.com/docs")
        assert "Documentation Header" in res
        assert "This is a paragraph" in res
        assert "console.log" not in res
        assert "color: red" not in res

@pytest.mark.asyncio
async def test_web_search_tool():
    tool = WebSearchTool(searxng_url="https://mock.searx.test")

    # Empty query
    empty_res = await tool.execute(query="")
    assert "Error: Search query cannot be empty" in empty_res

    # Mock SearXNG JSON response
    mock_json = """{
        "query": "python async",
        "results": [
            {"title": "Async IO in Python", "url": "https://python.org/async", "content": "Comprehensive asyncio guide."},
            {"title": "Python Async Tutorial", "url": "https://tutorial.org", "content": "Learn async programming."}
        ]
    }"""

    from unittest.mock import patch, MagicMock
    mock_resp = MagicMock()
    mock_resp.read = MagicMock(return_value=mock_json.encode("utf-8"))
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = await tool.execute(query="python async", num_results=2)
        assert "Async IO in Python" in res
        assert "https://python.org/async" in res
        assert "Comprehensive asyncio guide." in res

def test_truncate_tool_output():
    from cyc.agent.tools.base import truncate_tool_output

    # 1. Normal small output remains untouched
    small = "Normal output line 1\nLine 2\nLine 3"
    assert truncate_tool_output(small) == small

    # 2. Line-level truncation (1000 lines -> preserves head & tail)
    many_lines = "\n".join(f"Line {i}: data payload content" for i in range(1000))
    truncated_lines = truncate_tool_output(many_lines, max_lines=250, head_lines=150, tail_lines=60)
    assert len(truncated_lines.splitlines()) < 300
    assert "Line 0: data payload content" in truncated_lines
    assert "Line 149: data payload content" in truncated_lines
    assert "Line 999: data payload content" in truncated_lines
    assert "Line 500: data payload content" not in truncated_lines
    assert "... [Output truncated: omitted" in truncated_lines
    assert "(150 head / 60 tail preserved)" in truncated_lines

    # 3. Char-level truncation (huge single line string)
    huge_text = "A" * 50_000
    truncated_chars = truncate_tool_output(huge_text, max_chars=30_000, head_chars=20_000, tail_chars=8_000)
    assert len(truncated_chars) <= 32_000
    assert "... [Output truncated: omitted" in truncated_chars
    assert "(20000 head / 8000 tail preserved)" in truncated_chars
    assert truncated_chars.startswith("A" * 20_000)
    assert truncated_chars.endswith("A" * 8_000)

def test_enrich_tool_error_observation():
    from cyc.agent.tools.base import enrich_tool_error_observation

    # 1. Success observation is not modified
    success = "Successfully wrote 120 bytes to file.txt"
    assert enrich_tool_error_observation("write_file", success) == success

    # 2. Unrecognized tool hint
    unrecognized = "Error: Tool 'magic_wand' is not recognized."
    enriched_unrec = enrich_tool_error_observation("magic_wand", unrecognized)
    assert "[Diagnostic Self-Repair Hint]" in enriched_unrec
    assert "Do not invent unregistered tool names" in enriched_unrec

    # 3. File not found hint
    not_found = "Error: File 'missing.py' does not exist."
    enriched_nf = enrich_tool_error_observation("read_file", not_found, {"path": "missing.py"})
    assert "[Diagnostic Self-Repair Hint]" in enriched_nf
    assert "Use `list_dir` to inspect the directory structure" in enriched_nf
    assert "missing.py" in enriched_nf

    # 4. replace_file_content target not found
    target_nf = "Error: Target text not found in 'foo.py'."
    enriched_tnf = enrich_tool_error_observation("replace_file_content", target_nf, {"path": "foo.py"})
    assert "Call `read_file` to view the latest lines" in enriched_tnf

    # 5. replace_file_content multiple matches
    dup_target = "Error: Target text found 3 times in 'foo.py'."
    enriched_dup = enrich_tool_error_observation("replace_file_content", dup_target, {"path": "foo.py"})
    assert "Include 2-3 additional lines of surrounding context" in enriched_dup

    # 6. Command non-zero exit code
    exit_err = "Exit Code: 127\n\n[stderr]\ncommand not found"
    enriched_cmd = enrich_tool_error_observation("run_command", exit_err, {"command": "foobar"})
    assert "The command failed with exit code 127" in enriched_cmd
