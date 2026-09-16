from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from clichat.config import ProviderConfig
from clichat.providers import create_provider
from clichat.providers.openai import OpenAICompatibleProvider
from clichat.providers.gemini import GeminiProvider

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

    # Mock chunk response
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
