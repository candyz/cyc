from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, List

class BaseProvider(ABC):
    @abstractmethod
    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream chunks of response text from the model."""
        pass

    @abstractmethod
    async def list_models(self) -> List[str]:
        """List available model IDs for this provider."""
        pass
