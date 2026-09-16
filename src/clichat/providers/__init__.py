from typing import Optional
from clichat.config import Config, ProviderConfig
from clichat.providers.base import BaseProvider
from clichat.providers.openai import OpenAICompatibleProvider
from clichat.providers.gemini import GeminiProvider

def create_provider(provider_config: ProviderConfig) -> BaseProvider:
    provider_type = provider_config.type.lower()
    if provider_type in ("openai_compatible", "openai"):
        return OpenAICompatibleProvider(
            base_url=provider_config.base_url,
            api_key=provider_config.api_key,
        )
    elif provider_type in ("gemini", "gemini_native"):
        return GeminiProvider(
            api_key=provider_config.api_key,
        )
    raise ValueError(f"Unsupported provider type: {provider_config.type}")

__all__ = ["BaseProvider", "OpenAICompatibleProvider", "GeminiProvider", "create_provider"]
