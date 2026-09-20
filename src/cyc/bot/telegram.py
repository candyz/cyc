"""Telegram API Client for Cyc Bot Gateway."""

import asyncio
from typing import Any, Dict, List, Optional
import httpx


class TelegramClient:
    """Async Telegram Bot API Client supporting long polling, message sending, and inline keyboards."""

    def __init__(self, token: str, base_url: str = "https://api.telegram.org"):
        self.token = token.strip()
        self.api_url = f"{base_url.rstrip('/')}/bot{self.token}"
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def get_me(self) -> Dict[str, Any]:
        """Fetch bot info to verify credentials."""
        client = await self._get_client()
        resp = await client.get(f"{self.api_url}/getMe")
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise ValueError(f"Telegram getMe failed: {data.get('description')}")
        return data.get("result", {})

    async def get_updates(
        self,
        offset: Optional[int] = None,
        timeout: int = 30,
        allowed_updates: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Long poll Telegram Bot API for incoming updates."""
        client = await self._get_client()
        params: Dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        if allowed_updates is not None:
            params["allowed_updates"] = allowed_updates

        resp = await client.get(f"{self.api_url}/getUpdates", params=params, timeout=timeout + 10)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise ValueError(f"Telegram getUpdates failed: {data.get('description')}")
        return data.get("result", [])

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: Optional[str] = "HTML",
        reply_markup: Optional[Dict[str, Any]] = None,
        disable_web_page_preview: bool = True,
    ) -> Dict[str, Any]:
        """Send text message to chat."""
        client = await self._get_client()
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup

        resp = await client.post(f"{self.api_url}/sendMessage", json=payload)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise ValueError(f"Telegram sendMessage failed: {data.get('description')}")
        return data.get("result", {})

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: Optional[str] = "HTML",
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Edit previously sent message (for stream updates)."""
        client = await self._get_client()
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup

        resp = await client.post(f"{self.api_url}/editMessageText", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", {})

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """Acknowledge button click / callback query."""
        client = await self._get_client()
        payload: Dict[str, Any] = {"callback_query_id": callback_query_id, "show_alert": show_alert}
        if text:
            payload["text"] = text

        resp = await client.post(f"{self.api_url}/answerCallbackQuery", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return bool(data.get("ok"))

    async def send_document(
        self,
        chat_id: int,
        filename: str,
        file_bytes: bytes,
        caption: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send file attachment (e.g. diff patch or long output)."""
        client = await self._get_client()
        data: Dict[str, Any] = {"chat_id": str(chat_id)}
        if caption:
            data["caption"] = caption

        files = {"document": (filename, file_bytes, "text/plain")}
        resp = await client.post(f"{self.api_url}/sendDocument", data=data, files=files)
        resp.raise_for_status()
        res_json = resp.json()
        return res_json.get("result", {})
