from typing import AsyncGenerator, Dict, List, Optional
from google import genai
from google.genai import types
from clichat.providers.base import BaseProvider

class GeminiProvider(BaseProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key)

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        # Filter system messages and format multi-turn contents
        system_instruction: Optional[str] = None
        contents: List[types.Content] = []

        for msg in messages:
            role = msg.get("role", "user")
            content_text = msg.get("content", "")
            if role == "system":
                system_instruction = content_text
            elif role in ("assistant", "model"):
                contents.append(types.Content(role="model", parts=[types.Part.from_text(text=content_text)]))
            else:
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=content_text)]))

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
        )

        response = await self.client.aio.models.generate_content_stream(
            model=model,
            contents=contents,
            config=config,
        )

        async for chunk in response:
            if chunk.text:
                yield chunk.text

    async def list_models(self) -> List[str]:
        try:
            model_list = []
            pager = await self.client.aio.models.list()
            async for m in pager:
                # Name usually looks like 'models/gemini-2.5-flash'
                name = m.name or ""
                if name.startswith("models/"):
                    name = name[len("models/"):]
                if "gemini" in name:
                    model_list.append(name)
            return sorted(model_list)
        except Exception:
            return [
                "gemini-2.5-flash",
                "gemini-2.5-pro",
                "gemini-2.0-flash",
            ]
