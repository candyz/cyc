from typing import AsyncGenerator, Dict, List
from openai import AsyncOpenAI
from clichat.providers.base import BaseProvider

class OpenAICompatibleProvider(BaseProvider):
    def __init__(self, base_url: str, api_key: str):
        # OpenAI client requires a non-empty api_key string even for local servers
        self.api_key = api_key if api_key else "placeholder"
        self.base_url = base_url
        self.client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
        )

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            **kwargs,
        )
        async for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    async def list_models(self) -> List[str]:
        try:
            res = await self.client.models.list()
            return [m.id for m in res.data]
        except Exception:
            return []
