import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from clichat.cli import parse_args, async_main, CliApp
from clichat.config import load_config
from clichat.session import SessionManager

def test_parse_args_defaults():
    with patch.object(sys, "argv", ["clichat"]):
        args = parse_args()
        assert args.prompt == []
        assert args.provider is None
        assert args.model is None
        assert not args.init

def test_parse_args_with_options():
    with patch.object(sys, "argv", ["clichat", "-p", "openrouter", "-m", "claude", "--max-turns", "50", "What is AI?"]):
        args = parse_args()
        assert args.provider == "openrouter"
        assert args.model == "claude"
        assert args.max_turns == 50
        assert args.prompt == ["What is AI?"]

def test_parse_args_init():
    with patch.object(sys, "argv", ["clichat", "init", "-f"]):
        args = parse_args()
        assert args.prompt == ["init"]
        assert args.force is True

@pytest.mark.asyncio
async def test_async_main_init_command(tmp_path: Path):
    target_config = tmp_path / "custom_config.yaml"
    with patch.object(sys, "argv", ["clichat", "init", "-c", str(target_config)]):
        await async_main()
        assert target_config.exists()
        content = target_config.read_text(encoding="utf-8")
        assert "default_provider" in content

@pytest.mark.asyncio
async def test_openrouter_free_model_filtering():
    config = load_config(Path("/nonexistent"))
    app = CliApp(config, provider_name="openrouter")

    sample_models = [
        "anthropic/claude-3.5-sonnet",
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemini-2.0-flash-exp:free",
        "openai/gpt-4o",
        "deepseek/deepseek-r1:free",
    ]
    app.provider.list_models = AsyncMock(return_value=sample_models)

    await app.update_cached_models()
    assert app.cached_models == [
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemini-2.0-flash-exp:free",
        "deepseek/deepseek-r1:free",
    ]
    assert app.get_known_models() == app.cached_models

@pytest.mark.asyncio
async def test_non_openrouter_keeps_all_models():
    config = load_config(Path("/nonexistent"))
    app = CliApp(config, provider_name="ollama")

    sample_models = [
        "llama3.3:latest",
        "qwen2.5:latest",
    ]
    app.provider.list_models = AsyncMock(return_value=sample_models)

    await app.update_cached_models()
    assert app.cached_models == [
        "llama3.3:latest",
        "qwen2.5:latest",
    ]


def test_parse_args_agent_flags():
    with patch.object(sys, "argv", ["clichat", "--agent", "-y", "--read-only"]):
        args = parse_args()
        assert args.agent is True
        assert args.yes is True
        assert args.read_only is True


@pytest.mark.asyncio
async def test_handle_slash_command_mode_and_tools():
    config = load_config(Path("/nonexistent"))
    app = CliApp(config, provider_name="ollama")
    assert app.mode == "chat"

    handled = await app.handle_slash_command("/mode agent")
    assert handled is True
    assert app.mode == "agent"
    assert app.session.system_prompt is not None

    handled = await app.handle_slash_command("/mode chat")
    assert handled is True
    assert app.mode == "chat"
    assert app.session.system_prompt is None

    handled = await app.handle_slash_command("/tools")
    assert handled is True


def test_status_toolbar():
    config = load_config(Path("/nonexistent"))
    app = CliApp(config, provider_name="ollama")
    toolbar_html = app._get_status_toolbar()
    assert app.workspace_path.name in toolbar_html.value
    assert "ollama" in toolbar_html.value
    assert "Context:" in toolbar_html.value
    assert "(Type /help for commands)" not in toolbar_html.value

    app.mode = "agent"
    toolbar_html_agent = app._get_status_toolbar()
    assert "AGENT" in toolbar_html_agent.value
    assert app.workspace_path.name in toolbar_html_agent.value



@pytest.mark.asyncio
async def test_sessions_and_resume_slash_commands(tmp_path: Path):
    sessions_dir = tmp_path / "sessions"
    config = load_config(Path("/nonexistent"))

    # Create dummy session
    s1 = SessionManager(
        session_id="saved_session_xyz",
        provider="ollama",
        model="llama3.3",
        mode="agent",
        sessions_dir=sessions_dir,
    )
    s1.add_user_message("Test question")
    s1.add_assistant_message("Test answer")

    app = CliApp(config, provider_name="ollama")

    with patch("clichat.session.DEFAULT_SESSIONS_DIR", sessions_dir):
        # /sessions
        handled_sessions = await app.handle_slash_command("/sessions")
        assert handled_sessions is True

        # /resume with id
        handled_resume = await app.handle_slash_command("/resume saved_session_xyz")
        assert handled_resume is True
        assert app.session.session_id == "saved_session_xyz"
        assert len(app.session.messages) == 2
        assert app.mode == "agent"


def test_parse_args_resume_and_sessions():
    with patch.object(sys, "argv", ["clichat", "-r"]):
        args = parse_args()
        assert args.resume == "LATEST"

    with patch.object(sys, "argv", ["clichat", "--resume", "my_session_123"]):
        args = parse_args()
        assert args.resume == "my_session_123"

    with patch.object(sys, "argv", ["clichat", "--sessions"]):
        args = parse_args()
        assert args.sessions is True


@pytest.mark.asyncio
async def test_slash_command_trust(tmp_path: Path):
    config = load_config(Path("/nonexistent"))
    app = CliApp(config, provider_name="ollama")

    handled = await app.handle_slash_command("/trust show")
    assert handled is True

    handled = await app.handle_slash_command("/trust allow")
    assert handled is True
    assert app.is_workspace_trusted is True

    handled = await app.handle_slash_command("/trust deny")
    assert handled is True
    assert app.is_workspace_trusted is False
    assert app.permission_manager.mode.value == "read_only"


def test_parse_args_trust_flags():
    with patch.object(sys, "argv", ["clichat", "--trust"]):
        args = parse_args()
        assert args.trust is True

    with patch.object(sys, "argv", ["clichat", "--no-trust"]):
        args = parse_args()
        assert args.no_trust is True


def test_parse_args_completion():
    with patch.object(sys, "argv", ["clichat", "--completion"]):
        args = parse_args()
        assert args.completion == "bash"

    with patch.object(sys, "argv", ["clichat", "--completion", "zsh"]):
        args = parse_args()
        assert args.completion == "zsh"


@pytest.mark.asyncio
async def test_async_main_completion(capsys):
    with patch.object(sys, "argv", ["clichat", "--completion", "bash"]):
        await async_main()
        captured = capsys.readouterr()
        assert "complete -F _clichat_completion clichat" in captured.out


@pytest.mark.asyncio
async def test_slash_command_sessions_and_resume():
    config = load_config(Path("/nonexistent"))
    app = CliApp(config, provider_name="ollama")

    # /sessions with different source filters
    for src in ("all", "clichat", "agy", "claude", "pi", "opencode"):
        handled = await app.handle_slash_command(f"/sessions {src}")
        assert handled is True

    # /resume with agent prefix when session does not exist returns True and displays message
    handled = await app.handle_slash_command("/resume agy non-existent-id")
    assert handled is True

    handled = await app.handle_slash_command("/resume opencode non-existent-id")
    assert handled is True

    # Test /resume with existing session
    app.session.add_user_message("Previous question")
    app.session.add_assistant_message("Previous response")
    app.session.auto_save()
    sess_id = app.session.session_id

    handled = await app.handle_slash_command(f"/resume {sess_id}")
    assert handled is True
    assert len(app.session.messages) == 2


@pytest.mark.asyncio
async def test_slash_command_undo():
    config = load_config(Path("/nonexistent"))
    app = CliApp(config, provider_name="ollama")

    # Undo on empty session
    handled = await app.handle_slash_command("/undo")
    assert handled is True

    # Add messages
    app.session.add_user_message("Query 1")
    app.session.add_assistant_message("Answer 1")
    assert len(app.session.messages) == 2

    # Undo
    handled = await app.handle_slash_command("/undo")
    assert handled is True
    assert len(app.session.messages) == 0


@pytest.mark.asyncio
async def test_execute_shell_command(tmp_path):
    config = load_config(Path("/nonexistent"))
    app = CliApp(config, provider_name="ollama")
    app.workspace_path = tmp_path

    # Test empty command
    await app.execute_shell_command("")

    # Test valid command execution
    test_file = tmp_path / "created_by_shell.txt"
    await app.execute_shell_command(f"echo 'hello shell' > {test_file.name}")
    assert test_file.exists()
    assert "hello shell" in test_file.read_text(encoding="utf-8")

