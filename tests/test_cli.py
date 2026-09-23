import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from cyc.cli import parse_args, async_main, CliApp
from cyc.config import load_config
from cyc.session import SessionManager

def test_parse_args_defaults():
    with patch.object(sys, "argv", ["cyc"]):
        args = parse_args()
        assert args.prompt == []
        assert args.provider is None
        assert args.model is None
        assert not args.init

def test_parse_args_with_options():
    with patch.object(sys, "argv", ["cyc", "-p", "openrouter", "-m", "claude", "--max-turns", "50", "What is AI?"]):
        args = parse_args()
        assert args.provider == "openrouter"
        assert args.model == "claude"
        assert args.max_turns == 50
        assert args.prompt == ["What is AI?"]

def test_parse_args_init():
    with patch.object(sys, "argv", ["cyc", "init", "-f"]):
        args = parse_args()
        assert args.prompt == ["init"]
        assert args.force is True

@pytest.mark.asyncio
async def test_async_main_init_command(tmp_path: Path):
    target_config = tmp_path / "custom_config.yaml"
    with patch.object(sys, "argv", ["cyc", "init", "-c", str(target_config)]):
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
    with patch.object(sys, "argv", ["cyc", "--agent", "-y", "--read-only"]):
        args = parse_args()
        assert args.agent is True
        assert args.yes is True
        assert args.read_only is True

    with patch.object(sys, "argv", ["cyc", "--chat"]):
        args = parse_args()
        assert args.chat is True



@pytest.mark.asyncio
async def test_handle_slash_command_mode_and_tools():
    config = load_config(Path("/nonexistent"))
    app = CliApp(config, provider_name="ollama")
    assert app.mode == "agent"

    handled = await app.handle_slash_command("/mode chat")
    assert handled is True
    assert app.mode == "chat"
    assert app.session.system_prompt is None

    handled = await app.handle_slash_command("/mode agent")
    assert handled is True
    assert app.mode == "agent"
    assert app.session.system_prompt is not None

    handled = await app.handle_slash_command("/tools")
    assert handled is True

    handled = await app.handle_slash_command("/help")
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
    app.session.sessions_dir = sessions_dir

    with patch("cyc.session.DEFAULT_SESSIONS_DIR", sessions_dir):
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
    with patch.object(sys, "argv", ["cyc", "-r"]):
        args = parse_args()
        assert args.resume == "__INTERACTIVE__"

    with patch.object(sys, "argv", ["cyc", "--resume", "my_session_123"]):
        args = parse_args()
        assert args.resume == "my_session_123"

    with patch.object(sys, "argv", ["cyc", "--sessions"]):
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
    with patch.object(sys, "argv", ["cyc", "--trust"]):
        args = parse_args()
        assert args.trust is True

    with patch.object(sys, "argv", ["cyc", "--no-trust"]):
        args = parse_args()
        assert args.no_trust is True


def test_parse_args_completion():
    with patch.object(sys, "argv", ["cyc", "--completion"]):
        args = parse_args()
        assert args.completion == "bash"

    with patch.object(sys, "argv", ["cyc", "--completion", "zsh"]):
        args = parse_args()
        assert args.completion == "zsh"


def test_parse_args_bot():
    with patch.object(sys, "argv", ["cyc", "--bot", "--bot-token", "test_tok"]):
        args = parse_args()
        assert args.bot is True
        assert args.bot_token == "test_tok"


@pytest.mark.asyncio
async def test_async_main_bot_command():
    with patch.object(sys, "argv", ["cyc", "bot", "--bot-token", "dummy_token"]):
        with patch("cyc.bot.service.TelegramBotService.start", new_callable=AsyncMock) as mock_start:
            await async_main()
            assert mock_start.called



@pytest.mark.asyncio
async def test_async_main_completion(capsys):
    with patch.object(sys, "argv", ["cyc", "--completion", "bash"]):
        await async_main()
        captured = capsys.readouterr()
        assert "complete -F _cyc_completion cyc" in captured.out


@pytest.mark.asyncio
async def test_slash_command_sessions_and_resume():
    config = load_config(Path("/nonexistent"))
    app = CliApp(config, provider_name="ollama")

    # /sessions with different source filters
    for src in ("all", "cyc", "agy", "claude", "pi", "opencode"):
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

    # Verify get_known_sessions finds the session id
    known = app.get_known_sessions("cyc")
    assert "LATEST" in known
    assert sess_id in known

    # Test /resume with session id directly
    handled = await app.handle_slash_command(f"/resume {sess_id}")
    assert handled is True
    assert len(app.session.messages) == 2

    # Test /resume with explicit agent prefix 'cyc <sess_id>'
    handled = await app.handle_slash_command(f"/resume cyc {sess_id}")
    assert handled is True
    assert len(app.session.messages) == 2

    # Test /resume cyc LATEST
    handled = await app.handle_slash_command("/resume cyc LATEST")
    assert handled is True
    assert len(app.session.messages) == 2

    # Test /rename current session
    handled = await app.handle_slash_command("/rename My Great Analysis")
    assert handled is True
    assert app.session.title == "My Great Analysis"

    # Test get_known_sessions and get_known_session_items include title and metadata
    known = app.get_known_sessions("cyc")
    assert "My Great Analysis" in known
    items = app.get_known_session_items("cyc")
    item_titles = [it.get("title") for it in items]
    assert "My Great Analysis" in item_titles

    # Test /resume by title
    handled = await app.handle_slash_command("/resume My Great Analysis")
    assert handled is True
    assert app.session.session_id == sess_id
    assert app.session.title == "My Great Analysis"


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


@pytest.mark.asyncio
async def test_async_main_config_defaults(tmp_path):
    custom_config = tmp_path / "custom_config.yaml"
    custom_config.write_text("""
agent:
  default_mode: "agent"
  auto_approve: true
  default_trust: true
""", encoding="utf-8")

    with patch.object(sys, "argv", ["cyc", "-c", str(custom_config), "test query"]):
        with patch.object(sys.stdin, "isatty", return_value=True):
            with patch("cyc.cli.CliApp") as mock_cliapp_cls:
                mock_app_instance = AsyncMock()
                mock_cliapp_cls.return_value = mock_app_instance
                await async_main()
                assert mock_cliapp_cls.called
                _, kwargs = mock_cliapp_cls.call_args
                assert kwargs["mode"] == "agent"
                from cyc.agent import PermissionMode
                assert kwargs["permission_mode"] == PermissionMode.AUTO


@pytest.mark.asyncio
async def test_slash_command_sessions_subcommands(tmp_path):
    config = load_config(Path("/nonexistent"))
    app = CliApp(config, provider_name="ollama")
    app.session.sessions_dir = tmp_path / "sessions"

    # Create dummy session to delete/rename
    other_sess = SessionManager(session_id="dummy_sess_to_manage", sessions_dir=app.session.sessions_dir)
    other_sess.add_user_message("Dummy conversation")

    # 1. /sessions rename
    handled = await app.handle_slash_command("/sessions rename dummy_sess_to_manage New Title")
    assert handled is True
    reloaded = SessionManager.find_session("dummy_sess_to_manage", sessions_dir=app.session.sessions_dir)
    assert reloaded.title == "New Title"

    # 2. /sessions prune
    handled = await app.handle_slash_command("/sessions prune 5")
    assert handled is True

    # 3. /sessions delete
    handled = await app.handle_slash_command("/sessions delete dummy_sess_to_manage")
    assert handled is True
    assert SessionManager.find_session("dummy_sess_to_manage", sessions_dir=app.session.sessions_dir) is None

    # 4. /sessions delete current session should be blocked
    handled = await app.handle_slash_command(f"/sessions delete {app.session.session_id}")
    assert handled is True

    # 5. /sessions manage (interactive)
    app.ui.interactive_session_picker = AsyncMock(return_value={"action": "resume", "session": {"id": app.session.session_id, "agent": "cyc"}})
    handled_manage = await app.handle_slash_command("/sessions manage")
    assert handled_manage is True
    assert app.ui.interactive_session_picker.called


@pytest.mark.asyncio
async def test_async_main_interactive_resume(tmp_path):
    sess_dir = tmp_path / "sessions"
    sess = SessionManager(session_id="interactive_pick_target", sessions_dir=sess_dir)
    sess.add_user_message("Testing interactive picker")

    with patch.object(sys, "argv", ["cyc", "-r"]):
        with patch.object(sys.stdin, "isatty", return_value=True):
            with patch("cyc.ui.TerminalUI.interactive_session_picker", new_callable=AsyncMock) as mock_picker:
                mock_picker.return_value = {"action": "resume", "session": {"id": "interactive_pick_target", "agent": "cyc"}}
                with patch("cyc.cli.CliApp.repl", new_callable=AsyncMock) as mock_repl:
                    with patch("cyc.session.DEFAULT_SESSIONS_DIR", sess_dir):
                        await async_main()
                        assert mock_picker.called
                        assert mock_repl.called


@pytest.mark.asyncio
async def test_quick_chat_shortcuts():
    config = load_config(Path("/nonexistent"))
    app = CliApp(config, provider_name="ollama")
    app.stream_direct_chat = AsyncMock()

    # 1. /chat command
    handled = await app.handle_slash_command("/chat What is recursion?")
    assert handled is True
    app.stream_direct_chat.assert_awaited_with("What is recursion?")

    # 2. run_single_prompt with '?' prefix
    app.stream_direct_chat.reset_mock()
    await app.run_single_prompt("? Explain quantum computing")
    app.stream_direct_chat.assert_awaited_with("Explain quantum computing")

    # 3. run_single_prompt with '/chat ' prefix
    app.stream_direct_chat.reset_mock()
    await app.run_single_prompt("/chat Explain photosynthesis")
    app.stream_direct_chat.assert_awaited_with("Explain photosynthesis")


@pytest.mark.asyncio
async def test_update_command_and_slash():
    config = load_config(Path("/nonexistent"))
    app = CliApp(config, provider_name="ollama")

    # Test /update slash command
    with patch("cyc.updater.perform_update", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = True
        handled = await app.handle_slash_command("/update")
        assert handled is True
        mock_update.assert_awaited_with(force=False)

    with patch("cyc.updater.perform_update", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = True
        handled = await app.handle_slash_command("/update --force")
        assert handled is True
        mock_update.assert_awaited_with(force=True)

    # Test cli argument 'cyc update'
    with patch.object(sys, "argv", ["cyc", "update"]):
        with patch("cyc.updater.perform_update", new_callable=AsyncMock) as mock_update:
            await async_main()
            mock_update.assert_awaited_with(force=False)

    # Test cli flag 'cyc --update'
    with patch.object(sys, "argv", ["cyc", "--update", "-f"]):
        with patch("cyc.updater.perform_update", new_callable=AsyncMock) as mock_update:
            await async_main()
            mock_update.assert_awaited_with(force=True)








