from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

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
