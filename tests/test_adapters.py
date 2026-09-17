import json
from pathlib import Path
import pytest

from clichat.adapters import SessionAdapters


def test_import_agy_session(tmp_path: Path):
    brain_dir = tmp_path / "brain"
    conv_id = "test-agy-uuid-1234"
    log_dir = brain_dir / conv_id / ".system_generated" / "logs"
    log_dir.mkdir(parents=True)
    transcript_file = log_dir / "transcript.jsonl"

    records = [
        {"type": "USER_INPUT", "content": "<USER_REQUEST>\nHow to write a unit test in pytest?\n</USER_REQUEST>"},
        {"type": "PLANNER_RESPONSE", "content": "You can use the def test_... syntax.", "tool_calls": []},
        {"type": "PLANNER_RESPONSE", "content": "", "tool_calls": [{"name": "list_dir", "args": {"DirectoryPath": "/tmp"}}]},
        {"type": "GENERIC", "content": "file1.py\nfile2.py"},
    ]
    with open(transcript_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    # List agy sessions
    agy_sessions = SessionAdapters.list_agy_sessions(brain_dir=brain_dir)
    assert len(agy_sessions) == 1
    assert agy_sessions[0]["id"] == conv_id
    assert "How to write a unit test" in agy_sessions[0]["preview"]

    # Import agy session
    imported = SessionAdapters.import_agy_session("test-agy", brain_dir=brain_dir)
    assert imported is not None
    assert imported.session_id == "agy_test-agy"
    assert imported.provider == "agy"
    assert imported.mode == "agent"
    assert len(imported.messages) == 4
    assert imported.messages[0]["role"] == "user"
    assert imported.messages[0]["content"] == "How to write a unit test in pytest?"
    assert imported.messages[1]["role"] == "assistant"
    assert imported.messages[2]["role"] == "assistant"
    assert "tool_calls" in imported.messages[2]
    assert imported.messages[3]["role"] == "tool"


def test_import_claude_session(tmp_path: Path):
    projects_dir = tmp_path / "projects"
    proj_sub = projects_dir / "test-project"
    proj_sub.mkdir(parents=True)
    claude_file = proj_sub / "claude-session-abcd.jsonl"

    records = [
        {"type": "user", "message": {"role": "user", "content": "Fix the bug in main.py"}},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me examine main.py."},
                    {"type": "tool_use", "id": "call_1", "name": "Bash", "input": {"command": "cat main.py"}},
                ],
            },
        },
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "call_1", "content": "print('hello')"},
                ],
            },
        },
    ]
    with open(claude_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    # List claude sessions
    claude_sessions = SessionAdapters.list_claude_sessions(projects_dir=projects_dir)
    assert len(claude_sessions) == 1
    assert claude_sessions[0]["id"] == "claude-session-abcd"

    # Import claude session
    imported = SessionAdapters.import_claude_session("claude-session", projects_dir=projects_dir)
    assert imported is not None
    assert imported.session_id == "claude_claude-s"
    assert len(imported.messages) == 3
    assert imported.messages[0]["role"] == "user"
    assert imported.messages[0]["content"] == "Fix the bug in main.py"
    assert imported.messages[1]["role"] == "assistant"
    assert "tool_calls" in imported.messages[1]
    assert imported.messages[2]["role"] == "tool"


def test_import_pi_session(tmp_path: Path):
    sessions_dir = tmp_path / "pi_sessions"
    pi_proj = sessions_dir / "my-project"
    pi_proj.mkdir(parents=True)
    pi_file = pi_proj / "pi-session-999.jsonl"

    records = [
        {
            "type": "message",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "List the files"}],
            },
        },
        {
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Checking..."},
                    {"type": "toolCall", "id": "call_pi_1", "name": "bash", "arguments": {"command": "ls"}},
                ],
            },
        },
        {
            "type": "message",
            "message": {
                "role": "toolResult",
                "toolCallId": "call_pi_1",
                "toolName": "bash",
                "content": [{"type": "text", "text": "file.txt"}],
            },
        },
    ]
    with open(pi_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    # List pi sessions
    pi_sessions = SessionAdapters.list_pi_sessions(sessions_dir=sessions_dir)
    assert len(pi_sessions) == 1
    assert pi_sessions[0]["id"] == "pi-session-999"

    # Import pi session
    imported = SessionAdapters.import_pi_session("pi-session", sessions_dir=sessions_dir)
    assert imported is not None
    assert imported.session_id == "pi_pi-sessi"
    assert len(imported.messages) == 3
    assert imported.messages[0]["role"] == "user"
    assert imported.messages[0]["content"] == "List the files"
    assert imported.messages[1]["role"] == "assistant"
    assert imported.messages[2]["role"] == "tool"
