from pathlib import Path
from cyc.session import Session, SessionManager, estimate_tokens

def test_session_message_flow():
    session = Session(system_prompt="You are a helpful assistant.")
    assert len(session.get_messages()) == 1
    assert session.get_messages()[0]["role"] == "system"

    session.add_user_message("Hello")
    session.add_assistant_message("Hi there!")

    msgs = session.get_messages()
    assert len(msgs) == 3
    assert msgs[1] == {"role": "user", "content": "Hello"}
    assert msgs[2] == {"role": "assistant", "content": "Hi there!"}

    session.clear()
    assert len(session.get_messages()) == 1
    assert session.get_messages()[0]["role"] == "system"

def test_session_save_markdown(tmp_path: Path):
    session = Session(system_prompt="You are helpful.")
    session.add_user_message("What is 1+1?")
    session.add_assistant_message("2")

    save_file = tmp_path / "chat_export.md"
    session.save_markdown(save_file)

    assert save_file.exists()
    content = save_file.read_text(encoding="utf-8")
    assert "You are helpful." in content
    assert "What is 1+1?" in content
    assert "2" in content

def test_estimate_tokens():
    en_tokens = estimate_tokens("Hello world this is a test")
    assert en_tokens > 0
    # CJK characters
    cjk_tokens = estimate_tokens("你好世界")
    assert cjk_tokens >= 4

def test_context_pruning():
    # Very small context limit to trigger pruning
    session = SessionManager(system_prompt="System", max_context_tokens=30)
    session.add_user_message("Message 1: This is a reasonably long user message")
    session.add_assistant_message("Reply 1: This is a reasonably long assistant reply")
    session.add_user_message("Message 2: Another long message")

    # Should prune oldest messages while preserving system prompt
    msgs = session.get_messages()
    assert msgs[0]["role"] == "system"
    assert session.total_estimated_tokens() <= session.max_context_tokens or len(session.messages) <= 2

def test_session_save_and_load_json(tmp_path: Path):
    session = SessionManager(system_prompt="Persistent system")
    session.add_user_message("Save this test")
    session.add_assistant_message("Saved reply")

    json_path = tmp_path / "session.json"
    session.save_json(json_path)
    assert json_path.exists()

    loaded = SessionManager.load_json(json_path)
    assert loaded.system_prompt == "Persistent system"
    assert len(loaded.messages) == 2
    assert loaded.messages[0]["content"] == "Save this test"
    assert loaded.messages[1]["content"] == "Saved reply"


def test_session_auto_save_and_resume(tmp_path: Path):
    sessions_dir = tmp_path / "sessions"
    session1 = SessionManager(
        session_id="test_sess_01",
        provider="ollama",
        model="llama3.3",
        mode="agent",
        sessions_dir=sessions_dir,
    )
    session1.add_user_message("First user prompt")
    session1.add_assistant_message("First agent answer")

    # Check auto-saved file
    saved_file = sessions_dir / "test_sess_01.json"
    assert saved_file.exists()

    # Check auto-title was assigned from first user prompt
    assert session1.title == "First user prompt"

    # Test rename
    session1.rename("Weather Analysis")
    assert session1.title == "Weather Analysis"

    # Test list_sessions
    all_sessions = SessionManager.list_sessions(sessions_dir=sessions_dir)
    assert len(all_sessions) == 1
    assert all_sessions[0]["session_id"] == "test_sess_01"
    assert all_sessions[0]["title"] == "Weather Analysis"
    assert all_sessions[0]["mode"] == "agent"
    assert all_sessions[0]["message_count"] == 2

    # Test get_latest_session
    latest = SessionManager.get_latest_session(sessions_dir=sessions_dir)
    assert latest is not None
    assert latest.session_id == "test_sess_01"
    assert latest.title == "Weather Analysis"
    assert len(latest.messages) == 2

    # Test find_session by prefix
    found = SessionManager.find_session("test_sess", sessions_dir=sessions_dir)
    assert found is not None
    assert found.session_id == "test_sess_01"

    # Test find_session by title
    found_by_title = SessionManager.find_session("Weather Analysis", sessions_dir=sessions_dir)
    assert found_by_title is not None
    assert found_by_title.session_id == "test_sess_01"

    # Test find_session by partial title
    found_by_partial = SessionManager.find_session("weather", sessions_dir=sessions_dir)
    assert found_by_partial is not None
    assert found_by_partial.session_id == "test_sess_01"

def test_session_undo():
    session = SessionManager()
    assert session.undo_turn() is False

    # Turn 1
    session.add_user_message("Hello")
    session.add_assistant_message("Hi there!")
    assert len(session.messages) == 2

    # Turn 2
    session.add_user_message("Write a script")
    session.add_assistant_message("Here is the script...")
    assert len(session.messages) == 4

    # Undo Turn 2
    res = session.undo_turn()
    assert res is True
    assert len(session.messages) == 2
    assert session.messages[-1]["content"] == "Hi there!"

    # Undo Turn 1
    res = session.undo_turn()
    assert res is True
    assert len(session.messages) == 0

    # Undo again when empty
    assert session.undo_turn() is False


def test_dynamic_context_limits():
    from cyc.session import get_default_context_limit

    # Gemini / Agy models
    assert get_default_context_limit("gemini", "gemini-2.5-flash") == 1_000_000
    assert get_default_context_limit("agy", "gemini-3.8-flash-low") == 1_000_000

    # Claude
    assert get_default_context_limit("anthropic", "claude-3-7-sonnet") == 200_000

    # DeepSeek / GPT-4o / Nvidia NIM
    assert get_default_context_limit("nvidia", "nemotron") == 32_768
    assert get_default_context_limit("openrouter", "deepseek-v3") == 128_000

    # SessionManager default
    s_gemini = SessionManager(provider="agy", model="gemini-3.8-flash-low")
    assert s_gemini.max_context_tokens == 1_000_000

    s_custom = SessionManager(provider="agy", model="gemini-3.8-flash-low", max_context_tokens=50_000)
    assert s_custom.max_context_tokens == 50_000


def test_session_auto_compact():
    session = SessionManager(max_context_tokens=200, compact_threshold=0.80)
    # 80% of 200 is 160 tokens
    # Add messages gradually
    for i in range(8):
        session.add_user_message(f"User message number {i} discussing context compression with extra words")
        session.add_assistant_message(f"Assistant response {i} explaining token efficiency and compaction")

    # It should have triggered auto compaction
    assert any("[Context compacted:" in str(m.get("content", "")) for m in session.messages)
    assert session.total_estimated_tokens() <= 200


