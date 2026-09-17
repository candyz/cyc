import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from clichat.config import ProviderConfig
from clichat.providers import create_provider
from clichat.providers.openai import OpenAICompatibleProvider
from clichat.providers.gemini import GeminiProvider
from clichat.providers.agy import AntigravityProvider, DEFAULT_AGY_MODELS
from clichat.providers.opencode import OpenCodeProvider, DEFAULT_OPENCODE_ZEN_MODELS

def test_create_openai_provider():
    cfg = ProviderConfig(
        type="openai_compatible",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
    )
    provider = create_provider(cfg)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == "http://localhost:11434/v1"

def test_create_gemini_provider():
    cfg = ProviderConfig(
        type="gemini",
        api_key="fake-gemini-key",
    )
    provider = create_provider(cfg)
    assert isinstance(provider, GeminiProvider)
    assert provider.api_key == "fake-gemini-key"

def test_create_agy_provider():
    cfg = ProviderConfig(
        type="agy",
        base_url="",
        default_model="gemini-3.1-pro-high",
    )
    provider = create_provider(cfg)
    assert isinstance(provider, AntigravityProvider)

def test_unsupported_provider():
    cfg = ProviderConfig(
        type="unsupported_xyz",
        base_url="http://localhost:11434/v1",
        api_key="none",
    )
    with pytest.raises(ValueError, match="Unsupported provider type"):
        create_provider(cfg)

@pytest.mark.asyncio
async def test_openai_chat_stream_mock():
    provider = OpenAICompatibleProvider(base_url="http://test/v1", api_key="test-key")

    chunk1 = MagicMock()
    chunk1.choices = [MagicMock(delta=MagicMock(content="Hello "))]
    chunk2 = MagicMock()
    chunk2.choices = [MagicMock(delta=MagicMock(content="World!"))]

    async def mock_generator():
        yield chunk1
        yield chunk2

    provider.client.chat.completions.create = AsyncMock(return_value=mock_generator())

    chunks = []
    async for c in provider.chat_stream([{"role": "user", "content": "hi"}], model="test-model"):
        chunks.append(c)

    assert "".join(chunks) == "Hello World!"

@pytest.mark.asyncio
async def test_gemini_chat_stream_mock():
    provider = GeminiProvider(api_key="test-gemini-key")

    chunk1 = MagicMock(text="Gemini ")
    chunk2 = MagicMock(text="Response")

    async def mock_stream():
        yield chunk1
        yield chunk2

    provider.client.aio.models.generate_content_stream = AsyncMock(return_value=mock_stream())

    chunks = []
    async for c in provider.chat_stream([{"role": "user", "content": "hi"}], model="gemini-2.5-flash"):
        chunks.append(c)

    assert "".join(chunks) == "Gemini Response"

def test_agy_format_messages():
    provider = AntigravityProvider()
    # Single turn
    prompt1 = provider._format_messages_to_prompt([{"role": "user", "content": "hello"}])
    assert prompt1 == "hello"

    # Multi turn
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "How are you?"},
    ]
    formatted = provider._format_messages_to_prompt(messages)
    assert "[System Instructions]" in formatted
    assert "[User]\nHello" in formatted
    assert "[Assistant]\nHi there!" in formatted
    assert "[User]\nHow are you?" in formatted

@pytest.mark.asyncio
async def test_agy_chat_stream_mock():
    provider = AntigravityProvider(binary_path="/dummy/path/agy")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock(return_value=0)

    # Mock readline to simulate stream-json output
    lines = [
        b'{"event":"step_update","step_update":{"text_delta":"Antigravity "}}\n',
        b'{"event":"step_update","step_update":{"text_delta":"Streamed "}}\n',
        b'{"event":"step_update","step_update":{"text_delta":"Response!"}}\n',
        b'',
    ]
    line_iter = iter(lines)
    mock_proc.stdout.readline = AsyncMock(side_effect=lambda: next(line_iter))

    with patch("shutil.which", return_value="/dummy/path/agy"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        chunks = []
        async for chunk in provider.chat_stream([{"role": "user", "content": "test"}], model="gemini-3.1-pro-high"):
            chunks.append(chunk)

        assert "".join(chunks) == "Antigravity Streamed Response!"

@pytest.mark.asyncio
async def test_agy_list_models_mock():
    provider = AntigravityProvider(binary_path="/dummy/path/agy")

    mock_output = (
        b"\x1b[32m\xe2\xa0\x8b Fetching available models...\x1b[0m\n"
        b"gemini-3.1-pro-high       Gemini 3.1 Pro (High)\n"
        b"gemini-3.8-flash-low      Gemini 3.8 Flash (Low)\n"
        b"claude-sonnet-4-6         Claude Sonnet 4.6\n"
    )

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(mock_output, b""))

    with patch("shutil.which", return_value="/dummy/path/agy"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        models = await provider.list_models()
        assert "gemini-3.1-pro-high" in models
        assert "gemini-3.8-flash-low" in models
        assert "claude-sonnet-4-6" in models

def test_create_opencode_provider():
    cfg = ProviderConfig(
        type="opencode",
        default_model="opencode/nemotron-3.5-lightning-free",
    )
    provider = create_provider(cfg)
    assert isinstance(provider, OpenCodeProvider)

def test_opencode_normalize_model():
    provider = OpenCodeProvider()
    assert provider._normalize_model("nemotron-3.5-lightning-free") == "opencode/nemotron-3.5-lightning-free"
    assert provider._normalize_model("opencode/hy3-free") == "opencode/hy3-free"

@pytest.mark.asyncio
async def test_opencode_chat_stream_mock():
    provider = OpenCodeProvider(binary_path="/dummy/path/opencode")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock(return_value=0)

    # Mock JSON lines from opencode run --format json
    lines = [
        b'{"type":"step_start"}\n',
        b'{"type":"text","part":{"type":"text","text":"Hello from "}}\n',
        b'{"type":"text","part":{"type":"text","text":"OpenCode!"}}\n',
        b'{"type":"step_finish"}\n',
        b'',
    ]
    line_iter = iter(lines)
    mock_proc.stdout.readline = AsyncMock(side_effect=lambda: next(line_iter))

    with patch("shutil.which", return_value="/dummy/path/opencode"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        chunks = []
        async for chunk in provider.chat_stream([{"role": "user", "content": "hi"}], model="opencode/nemotron-3.5-lightning-free"):
            chunks.append(chunk)

        assert "".join(chunks) == "Hello from OpenCode!"

@pytest.mark.asyncio
async def test_opencode_list_models_mock():
    provider = OpenCodeProvider(binary_path="/dummy/path/opencode")

    mock_output = (
        b"opencode/nemotron-3.5-lightning-free\n"
        b"opencode/deepseek-v4-flash-free\n"
        b"opencode/paid-pro-model\n"
        b"openrouter/google/gemma-4:free\n"
    )

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(mock_output, b""))

    with patch("shutil.which", return_value="/dummy/path/opencode"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        models = await provider.list_models()
        # Should only include opencode/ models with 'free'
        assert "opencode/nemotron-3.5-lightning-free" in models
        assert "opencode/deepseek-v4-flash-free" in models
        assert "opencode/paid-pro-model" not in models
        assert "openrouter/google/gemma-4:free" not in models
