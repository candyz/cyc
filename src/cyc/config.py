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
    default_mode: str = "chat"  # "chat" or "agent"
    auto_approve: bool = False  # If True, equivalent to --yes
    default_trust: Optional[bool] = None  # True (trust), False (no-trust), or None (interactive prompt)

class WebConfig(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8888
    auth_token: str = ""
    cors_origins: List[str] = Field(default_factory=lambda: ["*"])
    ssl_cert: Optional[str] = None
    ssl_key: Optional[str] = None
    enable_terminal: bool = True

class TelegramConfig(BaseModel):
    token: str = ""
    allowed_user_ids: List[int] = Field(default_factory=list)
    workspace_path: Optional[str] = None
    streaming_throttle_seconds: float = 1.2
    auto_approve: bool = False

class BotConfig(BaseModel):
    enabled: bool = False
    platform: str = "telegram"  # "telegram", "discord", "slack"
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)

class Config(BaseModel):
    default_provider: str = "ollama"
    default_model: str = ""
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)
    mcp_servers: Dict[str, MCPServerConfig] = Field(default_factory=dict)
    skills_dirs: List[str] = Field(default_factory=list)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    bot: BotConfig = Field(default_factory=BotConfig)

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
    },
    "web": {
        "enabled": False,
        "host": "127.0.0.1",
        "port": 8888,
        "auth_token": "",
        "cors_origins": ["*"],
        "ssl_cert": None,
        "ssl_key": None,
        "enable_terminal": True,
    },
    "bot": {
        "enabled": False,
        "platform": "telegram",
        "telegram": {
            "token": "",
            "allowed_user_ids": [],
            "workspace_path": None,
            "streaming_throttle_seconds": 1.2,
            "auto_approve": False,
        },
    },
}

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "cyc" / "config.yaml"


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

        # Merge agent section defaults
        merged_agent = dict(DEFAULT_CONFIG_DICT.get("agent", {}))
        merged_agent.update(user_data.get("agent", {}))
        raw_data["agent"] = merged_agent

        # Merge web section defaults
        merged_web = dict(DEFAULT_CONFIG_DICT.get("web", {}))
        merged_web.update(user_data.get("web", {}))
        raw_data["web"] = merged_web
    else:
        raw_data = DEFAULT_CONFIG_DICT

    expanded_data = expand_env_vars(raw_data)
    return Config.model_validate(expanded_data)

DEFAULT_CONFIG_TEMPLATE = """# cyc configuration file
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
  default_mode: "chat"            # "chat" or "agent" (set to "agent" to default to --agent)
  auto_approve: false             # true to auto-approve mutation tools (equivalent to --yes)
  default_trust: null             # true (trust), false (no-trust/read-only), or null (prompt when entering workspace)
  max_turns: 100
  compact_threshold: 0.80
  searxng_url: "http://localhost:8080"

# Terminal UI configuration
ui:
  theme: "monokai"
  stream: true
  markdown_render: true

# Web remote interface configuration
web:
  enabled: false
  host: "127.0.0.1"
  port: 8888
  auth_token: ""                  # Leave empty to generate a random 32-char token on launch
  cors_origins:
    - "*"
  enable_terminal: true           # Enable embedded xterm terminal

# Chatbot Gateway configuration (Telegram, Discord, Slack)
bot:
  enabled: false
  platform: "telegram"               # telegram | discord | slack
  telegram:
    token: "${TELEGRAM_BOT_TOKEN}"    # Bot token from @BotFather
    allowed_user_ids: []              # Whitelisted Telegram user IDs (e.g. [123456789])
    workspace_path: null              # Default workspace path (null = current working directory)
    streaming_throttle_seconds: 1.2  # Interval between message updates to prevent 429
    auto_approve: false              # Auto-approve mutation tools without interactive inline buttons
"""

def init_config_file(dest_path: Optional[Path] = None, force: bool = False) -> Path:
    target = dest_path or DEFAULT_CONFIG_PATH
    if target.exists() and not force:
        raise FileExistsError(f"Config file already exists at: {target}. Use --force to overwrite.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
    return target
