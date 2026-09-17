import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from clichat.cli import parse_args, async_main, CliApp
from clichat.config import load_config

def test_parse_args_defaults():
    with patch.object(sys, "argv", ["clichat"]):
        args = parse_args()
        assert args.prompt == []
        assert args.provider is None
        assert args.model is None
        assert not args.init

def test_parse_args_with_options():
    with patch.object(sys, "argv", ["clichat", "-p", "openrouter", "-m", "claude", "What is AI?"]):
        args = parse_args()
        assert args.provider == "openrouter"
        assert args.model == "claude"
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
