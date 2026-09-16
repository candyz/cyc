import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from clichat.cli import parse_args, async_main

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
