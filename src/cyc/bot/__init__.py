"""Cyc Chatbot Gateway Package (Telegram, Discord, Slack)."""

from cyc.bot.base import BaseChatGateway
from cyc.bot.service import TelegramBotService
from cyc.bot.telegram import TelegramClient
from cyc.bot.formatter import format_markdown_to_telegram_html, chunk_message, escape_html

__all__ = [
    "BaseChatGateway",
    "TelegramBotService",
    "TelegramClient",
    "format_markdown_to_telegram_html",
    "chunk_message",
    "escape_html",
]

