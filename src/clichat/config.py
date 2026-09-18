import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field

ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}|\$(\w+)")

def expand_env_vars(data: Any) -> Any:
    """Recursively expand environment variables like ${VAR} or $VAR."""
    if isinstance(data, str):
        def replace(match: re.Match) -> str:
            var_name = match.group(1) or match.group(2)
            return os.environ.get(var_name, "")
        return ENV_VAR_PATTERN.sub(replace, data)
    elif isinstance(data, dict):
        return {k: expand_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [expand_env_vars(item) for item in data]
    return data

class ProviderConfig(BaseModel):
    type: str = "openai_compatible"
    base_url: str = ""
    api_key: str = "placeholder"
    default_model: str = ""
    max_context_tokens: Optional[int] = None

class MCPServerConfig(BaseModel):
    command: str
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    cwd: Optional[str] = None

class UIConfig(BaseModel):
    theme: str = "monokai"
    stream: bool = True
    markdown_render: bool = True

class AgentConfig(BaseModel):
    max_turns: int = 100
    compact_threshold: float = 0.80
    searxng_url: str = "https://searx.be"

class Config(BaseModel):
    default_provider: str = "ollama"
    default_model: str = ""
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)
    mcp_servers: Dict[str, MCPServerConfig] = Field(default_factory=dict)
    skills_dirs: List[str] = Field(default_factory=list)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    ui: UIConfig = Field(default_factory=UIConfig)

    def get_provider(self, name: Optional[str] = None) -> ProviderConfig:
        provider_name = name or self.default_provider
        if provider_name not in self.providers:
            raise KeyError(f"Provider '{provider_name}' not configured in providers list: {list(self.providers.keys())}")
        return self.providers[provider_name]

DEFAULT_CONFIG_DICT = {
    "default_provider": "ollama",
    "default_model": "",
    "providers": {
        "ollama": {
            "type": "openai_compatible",
            "base_url": "http://localhost:11434/v1",
            "api_key": "ollama",
            "default_model": "llama3.3:latest",
        },
        "openrouter": {
            "type": "openai_compatible",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "${OPENROUTER_API_KEY}",
            "default_model": "anthropic/claude-3.5-sonnet",
        },
        "omlx": {
            "type": "openai_compatible",
            "base_url": "http://localhost:8000/v1",
            "api_key": "omlx",
            "default_model": "default",
        },
        "nvidia": {
            "type": "openai_compatible",
            "base_url": "https://integrate.api.nvidia.com/v1",
            "api_key": "${NVIDIA_API_KEY}",
            "default_model": "meta/llama-3.3-70b-instruct",
        },
        "gemini": {
            "type": "gemini",
            "api_key": "${GEMINI_API_KEY}",
            "default_model": "gemini-2.5-flash",
        },
        "agy": {
            "type": "agy",
            "default_model": "gemini-3.1-pro-high",
        },
        "opencode": {
            "type": "opencode",
            "default_model": "opencode/nemotron-3.5-lightning-free",
        },
    },
    "agent": {
        "max_turns": 100,
        "compact_threshold": 0.80,
        "searxng_url": "https://searx.be",
    },
    "ui": {
        "theme": "monokai",
        "stream": True,
        "markdown_render": True,
    }
}

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "clichat" / "config.yaml"

def load_config(config_path: Optional[Path] = None) -> Config:
    path = config_path or DEFAULT_CONFIG_PATH
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            user_data = yaml.safe_load(f) or {}

        # Merge defaults so newly introduced providers are automatically accessible
        raw_data = dict(DEFAULT_CONFIG_DICT)
        raw_data.update(user_data)
        merged_providers = dict(DEFAULT_CONFIG_DICT["providers"])
        merged_providers.update(user_data.get("providers", {}))
        raw_data["providers"] = merged_providers
    else:
        raw_data = DEFAULT_CONFIG_DICT

    expanded_data = expand_env_vars(raw_data)
    return Config.model_validate(expanded_data)

DEFAULT_CONFIG_TEMPLATE = """# clichat configuration file
# Default provider and model to use on startup
default_provider: ollama
default_model: llama3.3:latest

# Provider configurations
providers:
  # 1. Local Ollama (default port 11434)
  ollama:
    type: openai_compatible
    base_url: "http://localhost:11434/v1"
    api_key: "ollama"
    default_model: "llama3.3:latest"

  # 2. Local OMLX / Apple Silicon MLX Server
  omlx:
    type: openai_compatible
    base_url: "http://localhost:8000/v1"
    api_key: "omlx"
    default_model: "default"

  # 3. OpenRouter (Cloud Multi-provider Gateway)
  openrouter:
    type: openai_compatible
    base_url: "https://openrouter.ai/api/v1"
    api_key: "${OPENROUTER_API_KEY}"
    default_model: "anthropic/claude-3.5-sonnet"

  # 4. NVIDIA NIM
  nvidia:
    type: openai_compatible
    base_url: "https://integrate.api.nvidia.com/v1"
    api_key: "${NVIDIA_API_KEY}"
    default_model: "meta/llama-3.3-70b-instruct"

  # 5. Google Gemini (Native SDK)
  gemini:
    type: gemini
    api_key: "${GEMINI_API_KEY}"
    default_model: "gemini-2.5-flash"

  # 6. Google Antigravity (Uses local agy CLI with Gemini AI Pro subscription quota, no API key needed)
  agy:
    type: agy
    default_model: "gemini-3.1-pro-high"

  # 7. OpenCode (Uses local opencode CLI with Zen free models, no API key needed)
  opencode:
    type: opencode
    default_model: "opencode/nemotron-3.5-lightning-free"

# MCP (Model Context Protocol) Servers (Optional)
# Configure external tools via stdio-based MCP servers
# mcp_servers:
#   memory:
#     command: "npx"
#     args: ["-y", "@modelcontextprotocol/server-memory"]
#   fetch:
#     command: "uvx"
#     args: ["mcp-server-fetch"]

# Agent configuration
agent:
  max_turns: 100
  compact_threshold: 0.80

# Terminal UI configuration
ui:
  theme: "monokai"
  stream: true
  markdown_render: true
"""

def init_config_file(dest_path: Optional[Path] = None, force: bool = False) -> Path:
    target = dest_path or DEFAULT_CONFIG_PATH
    if target.exists() and not force:
        raise FileExistsError(f"Config file already exists at: {target}. Use --force to overwrite.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
    return target
