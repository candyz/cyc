from typing import Optional
from cyc.config import Config, ProviderConfig
from cyc.providers.base import BaseProvider
from cyc.providers.openai import OpenAICompatibleProvider
from cyc.providers.gemini import GeminiProvider
from cyc.providers.agy import AntigravityProvider
from cyc.providers.opencode import OpenCodeProvider

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
    elif provider_type in ("opencode", "zen"):
        return OpenCodeProvider(
            binary_path=provider_config.base_url if provider_config.base_url else None
        )
    raise ValueError(f"Unsupported provider type: {provider_config.type}")

__all__ = [
    "BaseProvider",
    "OpenAICompatibleProvider",
    "GeminiProvider",
    "AntigravityProvider",
    "OpenCodeProvider",
    "create_provider",
]
