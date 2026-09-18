import asyncio
import inspect
import random
import re
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional
from rich.console import Console

console = Console()

def is_retryable_error(exc: BaseException) -> bool:
    """Determine whether an exception is transient (429 rate limit or 5xx server error)."""
    if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt)):
        return False

    status_code = getattr(exc, "status_code", None) or getattr(exc, "status", None) or getattr(exc, "code", None)
    if isinstance(status_code, int):
        if status_code == 429 or 500 <= status_code <= 599:
            return True

    msg = str(exc).lower()
    # Check for HTTP status codes in message text
    if any(code in msg for code in ("429", "500", "502", "503", "504")):
        return True

    # Check for common rate limit or server error keywords
    retry_patterns = [
        "rate limit",
        "resource exhausted",
        "quota exceeded",
        "too many requests",
        "overloaded",
        "server error",
        "bad gateway",
        "service unavailable",
        "gateway timeout",
        "connection reset",
        "connection closed",
    ]
    return any(p in msg for p in retry_patterns)

async def retry_async(
    coro_func: Callable[[], Any],
    max_retries: int = 4,
    base_delay: float = 1.5,
    max_delay: float = 30.0,
    retry_label: str = "API request",
) -> Any:
    """Execute an async coroutine with exponential backoff and jitter upon 429 / 5xx errors."""
    attempt = 0
    while True:
        try:
            return await coro_func()
        except Exception as exc:
            if attempt >= max_retries or not is_retryable_error(exc):
                raise exc

            attempt += 1
            # Exponential backoff with full jitter
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            jittered_delay = delay * random.uniform(0.7, 1.3)

            # Check if exception has retry-after header / hint
            retry_after = getattr(exc, "retry_after", None)
            if isinstance(retry_after, (int, float)) and retry_after > 0:
                jittered_delay = min(max_delay, float(retry_after))

            console.print(
                f"[dim yellow]⚠️  {retry_label} failed with transient error: {exc}. "
                f"Retrying ({attempt}/{max_retries}) in {jittered_delay:.1f}s...[/dim yellow]"
            )
            await asyncio.sleep(jittered_delay)

class ToolCallRequest:
    def __init__(self, id: str, name: str, arguments: Dict[str, Any]):
        self.id = id
        self.name = name
        self.arguments = arguments

    def __repr__(self):
        return f"ToolCallRequest(id='{self.id}', name='{self.name}', args={self.arguments})"

class AgentTurnResponse:
    def __init__(
        self,
        content: Optional[str] = None,
        tool_calls: Optional[List[ToolCallRequest]] = None,
    ):
        self.content = content
        self.tool_calls = tool_calls or []

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

class BaseProvider(ABC):
    @abstractmethod
    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream chunks of response text from the model."""
        pass

    @abstractmethod
    async def list_models(self) -> List[str]:
        """List available model IDs for this provider."""
        pass

    async def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: List[Any],
        **kwargs
    ) -> AgentTurnResponse:
        """Single turn of tool calling. Default fallback uses chat_stream to accumulate content."""
        chunks = []
        async for chunk in self.chat_stream(messages, model, **kwargs):
            chunks.append(chunk)
        return AgentTurnResponse(content="".join(chunks), tool_calls=[])

    async def get_usage_info(self, model: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Optional hook to fetch provider-level usage, billing, subscription quota, or rate limits."""
        return None


