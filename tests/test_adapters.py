import json
from pathlib import Path
import sqlite3
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


def test_import_opencode_session(tmp_path: Path):
    import sqlite3
    db_file = tmp_path / "opencode.db"
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE session (
        id text PRIMARY KEY,
        project_id text,
        title text,
        directory text,
        agent text,
        model text,
        time_created integer,
        time_updated integer
    );
    """)
    cursor.execute("""
    CREATE TABLE message (
        id text PRIMARY KEY,
        session_id text,
        time_created integer,
        time_updated integer,
        data text
    );
    """)
    cursor.execute("""
    CREATE TABLE part (
        id text PRIMARY KEY,
        message_id text,
        session_id text,
        time_created integer,
        time_updated integer,
        data text
    );
    """)

    # Insert sample opencode session
    cursor.execute("""
    INSERT INTO session (id, project_id, title, directory, agent, model, time_created, time_updated)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        "ses_test12345678",
        "proj_1",
        "New session - test",
        "/tmp",
        "build",
        json.dumps({"id": "nemotron-test"}),
        1700000000000,
        1700000005000,
    ))

    # Insert user message
    cursor.execute("""
    INSERT INTO message (id, session_id, time_created, time_updated, data)
    VALUES (?, ?, ?, ?, ?);
    """, ("msg_u1", "ses_test12345678", 1700000001000, 1700000001000, json.dumps({"role": "user"})))
    cursor.execute("""
    INSERT INTO part (id, message_id, session_id, time_created, time_updated, data)
    VALUES (?, ?, ?, ?, ?, ?);
    """, ("part_u1", "msg_u1", "ses_test12345678", 1700000001000, 1700000001000, json.dumps({"type": "text", "text": "Hello OpenCode"})))

    # Insert assistant message with tool call
    cursor.execute("""
    INSERT INTO message (id, session_id, time_created, time_updated, data)
    VALUES (?, ?, ?, ?, ?);
    """, ("msg_a1", "ses_test12345678", 1700000002000, 1700000002000, json.dumps({"role": "assistant"})))
    cursor.execute("""
    INSERT INTO part (id, message_id, session_id, time_created, time_updated, data)
    VALUES (?, ?, ?, ?, ?, ?);
    """, ("part_a1", "msg_a1", "ses_test12345678", 1700000002000, 1700000002000, json.dumps({"type": "text", "text": "Running tool"})))
    cursor.execute("""
    INSERT INTO part (id, message_id, session_id, time_created, time_updated, data)
    VALUES (?, ?, ?, ?, ?, ?);
    """, ("part_a2", "msg_a1", "ses_test12345678", 1700000002100, 1700000002100, json.dumps({
        "type": "tool",
        "tool": "read_file",
        "callID": "call_oc_1",
        "state": {"input": {"file": "a.txt"}, "output": "content_a"}
    })))

    conn.commit()
    conn.close()

    # List opencode sessions
    opencode_sessions = SessionAdapters.list_opencode_sessions(db_path=db_file)
    assert len(opencode_sessions) == 1
    assert opencode_sessions[0]["id"] == "ses_test12345678"
    assert opencode_sessions[0]["preview"] == "Hello OpenCode"
    assert opencode_sessions[0]["model"] == "nemotron-test"

    # Import opencode session
    imported = SessionAdapters.import_opencode_session("ses_test", db_path=db_file)
    assert imported is not None
    assert imported.session_id == "opencode_ses_test1234"
    assert imported.provider == "opencode"
    assert len(imported.messages) == 3
    assert imported.messages[0]["role"] == "user"
    assert imported.messages[0]["content"] == "Hello OpenCode"
    assert imported.messages[1]["role"] == "assistant"
    assert "tool_calls" in imported.messages[1]
    assert imported.messages[2]["role"] == "tool"
    assert imported.messages[2]["content"] == "content_a"


def test_export_and_sync_back_to_agy(tmp_path: Path):
    brain_dir = tmp_path / "brain"
    conv_id = "test-sync-agy-uuid-5678"
    log_dir = brain_dir / conv_id / ".system_generated" / "logs"
    log_dir.mkdir(parents=True)
    transcript_file = log_dir / "transcript.jsonl"

    initial_records = [
        {"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": "<USER_REQUEST>\nInitial question in agy\n</USER_REQUEST>"},
        {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "content": "Initial answer from agy"},
    ]
    with open(transcript_file, "w", encoding="utf-8") as f:
        for r in initial_records:
            f.write(json.dumps(r) + "\n")

    # 1. Import session into clichat
    imported = SessionAdapters.import_agy_session("test-sync-agy", brain_dir=brain_dir)
    assert imported is not None
    assert imported.external_metadata["source_agent"] == "agy"
    assert imported.external_metadata["source_id"] == conv_id
    assert imported.external_metadata["base_message_count"] == 2

    # 2. Add new user and assistant turns in clichat
    imported.add_user_message("New question asked in clichat")
    imported.add_assistant_message("New solution answered in clichat")

    # 3. Sync session back to AGY
    result = SessionAdapters.sync_session_back(imported)
    assert result["success"] is True
    assert result["synced_count"] == 2
    assert result["conv_id"] == conv_id

    # 4. Verify AGY transcript.jsonl was appended properly
    lines = [json.loads(line) for line in transcript_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 4
    # Check step indexes continuous
    assert lines[2]["step_index"] == 2
    assert lines[2]["type"] == "USER_INPUT"
    assert "New question asked in clichat" in lines[2]["content"]
    assert lines[3]["step_index"] == 3
    assert lines[3]["type"] == "PLANNER_RESPONSE"
    assert lines[3]["content"] == "New solution answered in clichat"

    # 5. Calling sync again without new messages should report already up to date
    res2 = SessionAdapters.sync_session_back(imported)
    assert res2["success"] is True
    assert res2["synced_count"] == 0


def test_export_and_sync_back_to_claude(tmp_path: Path):
    projects_dir = tmp_path / "claude_projects"
    proj_dir = projects_dir / "my-project"
    proj_dir.mkdir(parents=True)
    session_file = proj_dir / "claude-session-xyz.jsonl"

    initial_records = [
        {"type": "user", "message": {"role": "user", "content": "Initial question in Claude"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Initial answer from Claude"}]}},
    ]
    with open(session_file, "w", encoding="utf-8") as f:
        for r in initial_records:
            f.write(json.dumps(r) + "\n")

    # 1. Import claude session
    imported = SessionAdapters.import_claude_session("claude-session", projects_dir=projects_dir)
    assert imported is not None
    assert imported.external_metadata["source_agent"] == "claude"
    assert imported.external_metadata["source_id"] == "claude-session-xyz"
    assert imported.external_metadata["base_message_count"] == 2

    # 2. Add new user and assistant message with tool call in clichat
    imported.add_user_message("Please run tests")
    imported.messages.append({
        "role": "assistant",
        "content": "Running test suite...",
        "tool_calls": [{
            "id": "tc_1",
            "type": "function",
            "function": {"name": "run_command", "arguments": json.dumps({"command": "pytest"})},
        }],
    })
    imported.messages.append({
        "role": "tool",
        "tool_call_id": "tc_1",
        "name": "run_command",
        "content": "All tests passed",
    })

    # 3. Sync session back to Claude
    result = SessionAdapters.sync_session_back(imported, custom_path=projects_dir)
    assert result["success"] is True
    assert result["synced_count"] == 3

    # 4. Verify appended lines in claude session file
    lines = [json.loads(line) for line in session_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 5
    assert lines[2]["type"] == "user"
    assert lines[2]["message"]["content"] == "Please run tests"
    assert lines[3]["type"] == "assistant"
    assert lines[3]["message"]["content"][0]["type"] == "text"
    assert lines[3]["message"]["content"][1]["type"] == "tool_use"
    assert lines[3]["message"]["content"][1]["name"] == "run_command"
    assert lines[4]["type"] == "user"
    assert lines[4]["message"]["content"][0]["type"] == "tool_result"
    assert lines[4]["message"]["content"][0]["content"] == "All tests passed"

    # 5. Calling sync again is idempotent
    res2 = SessionAdapters.sync_session_back(imported, custom_path=projects_dir)
    assert res2["success"] is True
    assert res2["synced_count"] == 0


def test_export_and_sync_back_to_pi(tmp_path: Path):
    sessions_dir = tmp_path / "pi_sessions"
    proj_dir = sessions_dir / "my-project"
    proj_dir.mkdir(parents=True)
    session_file = proj_dir / "pi-session-abc.jsonl"

    initial_records = [
        {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "Hello Pi"}]}},
        {"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": "Hello from Pi"}]}},
    ]
    with open(session_file, "w", encoding="utf-8") as f:
        for r in initial_records:
            f.write(json.dumps(r) + "\n")

    # 1. Import Pi session
    imported = SessionAdapters.import_pi_session("pi-session", sessions_dir=sessions_dir)
    assert imported is not None
    assert imported.external_metadata["source_agent"] == "pi"
    assert imported.external_metadata["source_id"] == "pi-session-abc"
    assert imported.external_metadata["base_message_count"] == 2

    # 2. Add new user & assistant message in clichat
    imported.add_user_message("Check system status")
    imported.messages.append({
        "role": "assistant",
        "content": "Status looks normal.",
    })

    # 3. Sync back to Pi
    result = SessionAdapters.sync_session_back(imported, custom_path=sessions_dir)
    assert result["success"] is True
    assert result["synced_count"] == 2

    # 4. Verify appended lines in Pi session file
    lines = [json.loads(line) for line in session_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 4
    assert lines[2]["type"] == "message"
    assert lines[2]["message"]["role"] == "user"
    assert lines[2]["message"]["content"][0]["text"] == "Check system status"
    assert lines[3]["type"] == "message"
    assert lines[3]["message"]["role"] == "assistant"
    assert lines[3]["message"]["content"][0]["text"] == "Status looks normal."

    # 5. Idempotent check
    res2 = SessionAdapters.sync_session_back(imported, custom_path=sessions_dir)
    assert res2["success"] is True
    assert res2["synced_count"] == 0


def test_export_and_sync_back_to_opencode(tmp_path: Path):
    db_file = tmp_path / "opencode.db"
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE session (
        id text PRIMARY KEY,
        project_id text,
        title text,
        directory text,
        agent text,
        model text,
        time_created integer,
        time_updated integer
    );
    """)
    cursor.execute("""
    CREATE TABLE message (
        id text PRIMARY KEY,
        session_id text,
        time_created integer,
        time_updated integer,
        data text
    );
    """)
    cursor.execute("""
    CREATE TABLE part (
        id text PRIMARY KEY,
        message_id text,
        session_id text,
        time_created integer,
        time_updated integer,
        data text
    );
    """)

    # Populate initial session
    cursor.execute("""
    INSERT INTO session (id, project_id, title, directory, agent, model, time_created, time_updated)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, ("ses_oc_001", "proj_1", "Test Session", "/tmp", "build", json.dumps({"id": "model-x"}), 1000, 2000))
    cursor.execute("INSERT INTO message VALUES ('msg_1', 'ses_oc_001', 1000, 1000, '{\"role\": \"user\"}');")
    cursor.execute("INSERT INTO part VALUES ('part_1', 'msg_1', 'ses_oc_001', 1000, 1000, '{\"type\": \"text\", \"text\": \"Query in OpenCode\"}');")
    cursor.execute("INSERT INTO message VALUES ('msg_2', 'ses_oc_001', 1010, 1010, '{\"role\": \"assistant\"}');")
    cursor.execute("INSERT INTO part VALUES ('part_2', 'msg_2', 'ses_oc_001', 1010, 1010, '{\"type\": \"text\", \"text\": \"Response in OpenCode\"}');")
    conn.commit()
    conn.close()

    # 1. Import opencode session
    imported = SessionAdapters.import_opencode_session("ses_oc", db_path=db_file)
    assert imported is not None
    assert imported.external_metadata["source_agent"] == "opencode"
    assert imported.external_metadata["source_id"] == "ses_oc_001"
    assert imported.external_metadata["base_message_count"] == 2

    # 2. Add new user and assistant message
    imported.add_user_message("Analyze the performance")
    imported.add_assistant_message("Performance is optimal")

    # 3. Sync back to OpenCode
    result = SessionAdapters.sync_session_back(imported, custom_path=db_file)
    assert result["success"] is True
    assert result["synced_count"] == 2

    # 4. Verify SQLite rows
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM message WHERE session_id = 'ses_oc_001';")
    msg_count = cursor.fetchone()[0]
    assert msg_count == 4

    cursor.execute("SELECT count(*) FROM part WHERE session_id = 'ses_oc_001';")
    part_count = cursor.fetchone()[0]
    assert part_count == 4

    cursor.execute("SELECT data FROM part WHERE session_id = 'ses_oc_001' ORDER BY time_created ASC;")
    all_parts = [json.loads(row[0]) for row in cursor.fetchall()]
    assert all_parts[2]["text"] == "Analyze the performance"
    assert all_parts[3]["text"] == "Performance is optimal"
    conn.close()

    # 5. Idempotent check
    res2 = SessionAdapters.sync_session_back(imported, custom_path=db_file)
    assert res2["success"] is True
    assert res2["synced_count"] == 0


