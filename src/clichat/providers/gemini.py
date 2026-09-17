import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional
from google import genai
from google.genai import types
from clichat.providers.base import AgentTurnResponse, BaseProvider, ToolCallRequest

class GeminiProvider(BaseProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key)

    def _prepare_contents_and_system(self, messages: List[Dict[str, Any]]):
        system_instruction: Optional[str] = None
        contents: List[types.Content] = []

        for msg in messages:
            role = msg.get("role", "user")
            content_text = msg.get("content") or ""

            if role == "system":
                system_instruction = content_text
            elif role in ("assistant", "model"):
                contents.append(types.Content(role="model", parts=[types.Part.from_text(text=content_text)]))
            elif role == "tool":
                # Handle tool response message in Gemini format
                tool_call_id = msg.get("tool_call_id", "call")
                tool_name = msg.get("name", "tool")
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_function_response(
                                name=tool_name,
                                response={"result": content_text},
                            )
                        ],
                    )
                )
            else:
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=content_text)]))

        return contents, system_instruction

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        contents, system_instruction = self._prepare_contents_and_system(messages)
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

    async def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: List[Any],
        **kwargs
    ) -> AgentTurnResponse:
        contents, system_instruction = self._prepare_contents_and_system(messages)

        gemini_tools = None
        if tools:
            # Check if tools are dict declarations or types.Tool
            declarations = []
            for t in tools:
                if isinstance(t, dict):
                    declarations.append(
                        types.FunctionDeclaration(
                            name=t.get("name", ""),
                            description=t.get("description", ""),
                            parameters=t.get("parameters", {}),
                        )
                    )
                else:
                    declarations.append(t)
            gemini_tools = [types.Tool(function_declarations=declarations)]

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=gemini_tools,
        )

        response = await self.client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        parsed_calls: List[ToolCallRequest] = []
        if response.function_calls:
            for fc in response.function_calls:
                call_id = f"call_{uuid.uuid4().hex[:8]}"
                parsed_calls.append(
                    ToolCallRequest(
                        id=call_id,
                        name=fc.name,
                        arguments=dict(fc.args) if fc.args else {},
                    )
                )

        text_content = response.text if not parsed_calls else None
        return AgentTurnResponse(content=text_content, tool_calls=parsed_calls)

    async def list_models(self) -> List[str]:
        try:
            model_list = []
            pager = await self.client.aio.models.list()
            async for m in pager:
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

    async def get_usage_info(self, model: Optional[str] = None) -> Optional[Dict[str, Any]]:
        target_model = model or "gemini-2.5-flash"
        info = {
            "provider": "Google Gemini (AI Studio)",
            "tier": "Free / Pay-as-you-go",
            "model": target_model,
        }
        if "flash" in target_model.lower():
            info["rate_limit_rpm"] = "15 RPM (Free Tier) / 1000 RPM (Pay-as-you-go)"
            info["rate_limit_tpm"] = "1,000,000 TPM"
            info["rate_limit_rpd"] = "1,500 RPD (Free Tier)"
        else:
            info["rate_limit_rpm"] = "2 RPM (Free Tier) / 360 RPM (Pay-as-you-go)"
            info["rate_limit_tpm"] = "32,000 TPM"
            info["rate_limit_rpd"] = "50 RPD (Free Tier)"
        return info

