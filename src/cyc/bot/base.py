"""Base Chatbot Gateway Abstract Class for multi-platform bots (Telegram, Discord, Slack)."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Set
from cyc.config import Config


class BaseChatGateway(ABC):
    """Abstract base class defining interface for chat platform gateways."""

    def __init__(self, config: Config, platform_name: str, workspace_path: Optional[Path] = None):
        self.config = config
        self.platform_name = platform_name
        self.workspace_path = workspace_path or Path.cwd()
        self._running = False

    @abstractmethod
    def is_authorized(self, user_id: Any) -> bool:
        """Check if incoming user/actor is authorized to command the bot."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Start listening for events / messages on the chat platform."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop the gateway service."""
        pass

    @abstractmethod
    async def handle_command(self, chat_id: Any, command_text: str) -> None:
        """Process slash or platform command."""
        pass

    @abstractmethod
    async def run_agent_prompt(self, chat_id: Any, prompt: str) -> None:
        """Dispatch query to AgentLoop and deliver response to chat."""
        pass
