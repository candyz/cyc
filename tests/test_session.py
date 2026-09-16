from pathlib import Path
from clichat.session import Session, SessionManager, estimate_tokens

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
