from typing import Optional
from clichat.config import Config, ProviderConfig
from clichat.providers.base import BaseProvider
from clichat.providers.openai import OpenAICompatibleProvider
from clichat.providers.gemini import GeminiProvider
from clichat.providers.agy import AntigravityProvider

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
    elif provider_type in ("agy", "antigravity"):
        return AntigravityProvider(
            binary_path=provider_config.base_url if provider_config.base_url else None
        )
    raise ValueError(f"Unsupported provider type: {provider_config.type}")

__all__ = ["BaseProvider", "OpenAICompatibleProvider", "GeminiProvider", "AntigravityProvider", "create_provider"]
