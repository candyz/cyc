import json
from typing import Any, AsyncGenerator, Dict, List, Optional
from openai import AsyncOpenAI
from clichat.providers.base import AgentTurnResponse, BaseProvider, ToolCallRequest

class OpenAICompatibleProvider(BaseProvider):
    def __init__(self, base_url: str, api_key: str):
        self.api_key = api_key if api_key else "placeholder"
        self.base_url = base_url
        self.client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
        )

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
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

    async def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: List[Any],
        **kwargs
    ) -> AgentTurnResponse:
        """Call LLM with function/tool declarations and return content or tool_calls."""
        payload_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            **kwargs,
        }
        if tools:
            payload_kwargs["tools"] = tools

        response = await self.client.chat.completions.create(**payload_kwargs)
        choice = response.choices[0]
        msg = choice.message

        parsed_tool_calls: List[ToolCallRequest] = []
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args}
                parsed_tool_calls.append(
                    ToolCallRequest(id=tc.id, name=tc.function.name, arguments=args)
                )

        return AgentTurnResponse(content=msg.content, tool_calls=parsed_tool_calls)

    async def list_models(self) -> List[str]:
        try:
            res = await self.client.models.list()
            return [m.id for m in res.data]
        except Exception:
            return []

    async def get_usage_info(self, model: Optional[str] = None) -> Optional[Dict[str, Any]]:
        # Special support for OpenRouter key and usage limits inquiry
        if "openrouter.ai" in self.base_url.lower():
            import urllib.request
            try:
                req = urllib.request.Request(
                    "https://openrouter.ai/api/v1/auth/key",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "User-Agent": "clichat",
                    }
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode("utf-8"))
                        key_data = data.get("data", {})
                        usage = key_data.get("usage", 0.0)
                        limit = key_data.get("limit")
                        limit_remaining = key_data.get("limit_remaining")
                        is_free_tier = key_data.get("is_free_tier", False)
                        rate_limit = key_data.get("rate_limit", {})
                        label = key_data.get("label", "OpenRouter API Key")

                        return {
                            "provider": "OpenRouter",
                            "label": label,
                            "usage_usd": f"${usage:.4f}" if isinstance(usage, (int, float)) else str(usage),
                            "limit_usd": f"${limit:.2f}" if limit is not None else "Unlimited",
                            "limit_remaining_usd": f"${limit_remaining:.4f}" if limit_remaining is not None else "Unlimited",
                            "is_free_tier": "Yes (Free Tier)" if is_free_tier else "No (Paid Tier)",
                            "rate_limit_requests": rate_limit.get("requests", "N/A"),
                            "rate_limit_interval": rate_limit.get("interval", "N/A"),
                        }
            except Exception:
                pass
        return None

