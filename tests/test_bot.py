"""Unit tests for Telegram Bot Gateway (formatting, client, service, auth, HITL)."""

import asyncio
from unittest.mock import AsyncMock, patch
import pytest

from cyc.bot.formatter import chunk_message, escape_html, format_markdown_to_telegram_html
from cyc.bot.service import TelegramBotService
from cyc.bot.telegram import TelegramClient
from cyc.config import Config, DEFAULT_CONFIG_DICT


def test_escape_html():
    raw = "<script>alert('xss');</script> & foo"
    escaped = escape_html(raw)
    assert "&lt;script&gt;" in escaped
    assert "&amp;" in escaped


def test_format_markdown_to_telegram_html():
    md = """# Title
Hello **world** and *italic* and `code_snippet`

```python
def foo():
    return 42
```
"""
    result = format_markdown_to_telegram_html(md)
    assert "<b>Title</b>" in result
    assert "<b>world</b>" in result
    assert "<i>italic</i>" in result
    assert "<code>code_snippet</code>" in result
    assert '<pre><code class="language-python">' in result
    assert "return 42" in result


def test_chunk_message():
    short_text = "Hello world"
    assert chunk_message(short_text, max_length=100) == [short_text]

    long_text = "\n".join([f"Line {i}" for i in range(100)])
    chunks = chunk_message(long_text, max_length=150)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 150


@pytest.mark.asyncio
async def test_telegram_client_api_calls():
    client = TelegramClient(token="dummy_token")

    with patch.object(client, "_get_client") as mock_get_client:
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http

        from unittest.mock import MagicMock
        # Mock get_me
        mock_resp_get = MagicMock()
        mock_resp_get.json.return_value = {"ok": True, "result": {"id": 123, "username": "test_bot"}}
        mock_resp_get.raise_for_status.return_value = None
        mock_http.get.return_value = mock_resp_get

        info = await client.get_me()
        assert info["username"] == "test_bot"

        # Mock send_message
        mock_resp_post = MagicMock()
        mock_resp_post.json.return_value = {"ok": True, "result": {"message_id": 999}}
        mock_resp_post.raise_for_status.return_value = None
        mock_http.post.return_value = mock_resp_post

        msg = await client.send_message(chat_id=12345, text="Hello")
        assert msg["message_id"] == 999

        # Mock edit_message_text
        edited = await client.edit_message_text(chat_id=12345, message_id=999, text="Updated")
        assert edited["message_id"] == 999

        # Mock answer_callback_query
        ans = await client.answer_callback_query(callback_query_id="cb123", text="Done")
        assert ans is True

    await client.close()


@pytest.mark.asyncio
async def test_bot_service_authorization():
    cfg = Config(**DEFAULT_CONFIG_DICT)
    cfg.bot.telegram.token = "fake_token"
    cfg.bot.telegram.allowed_user_ids = [111, 222]

    service = TelegramBotService(config=cfg)
    assert service.is_authorized(111) is True
    assert service.is_authorized(222) is True
    assert service.is_authorized(333) is False


@pytest.mark.asyncio
async def test_bot_service_unauthorized_message():
    cfg = Config(**DEFAULT_CONFIG_DICT)
    cfg.bot.telegram.token = "fake_token"
    cfg.bot.telegram.allowed_user_ids = [999]

    service = TelegramBotService(config=cfg)

    with patch.object(service.client, "send_message", new_callable=AsyncMock) as mock_send:
        # Message from unauthorized user 123
        msg = {
            "message_id": 1,
            "from": {"id": 123, "username": "intruder"},
            "chat": {"id": 456},
            "text": "Hello bot",
        }
        await service.handle_message(msg)
        assert mock_send.called
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["chat_id"] == 456
        assert "Access Denied" in call_kwargs["text"]


@pytest.mark.asyncio
async def test_bot_service_commands():
    cfg = Config(**DEFAULT_CONFIG_DICT)
    cfg.bot.telegram.token = "fake_token"
    cfg.bot.telegram.allowed_user_ids = [123]

    service = TelegramBotService(config=cfg)

    with patch.object(service.client, "send_message", new_callable=AsyncMock) as mock_send:
        # /start
        await service.handle_message({
            "message_id": 1,
            "from": {"id": 123},
            "chat": {"id": 123},
            "text": "/start",
        })
        assert "Welcome to cyc Telegram Gateway" in mock_send.call_args.kwargs["text"]

        # /mode agent
        await service.handle_message({
            "message_id": 2,
            "from": {"id": 123},
            "chat": {"id": 123},
            "text": "/mode agent",
        })
        assert "Switched mode to <b>agent</b>" in mock_send.call_args.kwargs["text"]

        # /status
        await service.handle_message({
            "message_id": 3,
            "from": {"id": 123},
            "chat": {"id": 123},
            "text": "/status",
        })
        assert "cyc Status" in mock_send.call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_bot_service_hitl_approval_callback():
    cfg = Config(**DEFAULT_CONFIG_DICT)
    cfg.bot.telegram.token = "fake_token"
    cfg.bot.telegram.allowed_user_ids = [123]

    service = TelegramBotService(config=cfg)

    # Register a pending approval future
    approval_id = "test_approval_id"
    fut = asyncio.get_running_loop().create_future()
    service.pending_approvals[approval_id] = fut

    with patch.object(service.client, "answer_callback_query", new_callable=AsyncMock) as mock_ans, \
         patch.object(service.client, "edit_message_text", new_callable=AsyncMock) as mock_edit:

        cb = {
            "id": "cb_001",
            "from": {"id": 123},
            "data": f"approve:{approval_id}",
            "message": {"chat": {"id": 123}, "message_id": 10, "text": "Approval Required"},
        }
        await service.handle_callback_query(cb)
        assert fut.done()
        assert fut.result() is True
        assert mock_ans.called
        assert mock_edit.called
