# clichat 部署與配置指南 (Deployment Guide)

本文件說明 `clichat` 的環境相依性、安裝方式、設定檔配置、多 Provider 認證設定、MCP 外部工具擴充及 Shell 自動補全設置。

---

## 1. 系統需求 (Prerequisites)

- **作業系統**：macOS (支援 Apple Silicon 與 Intel)、Linux、Windows (WSL2)。
- **Python 環境**：Python 3.10 以上（建議使用 Python 3.12+）。
- **套件管理器**：建議使用現代化的 [`uv`](https://github.com/astral-sh/uv) 或 `pipx`。

---

## 2. 安裝方式 (Installation)

### 2.1 透過 `uv tool` 全域安裝 (強烈推薦)
`uv` 提供了獨立沙盒隔離的全域 CLI 安裝方式，快速且不污染系統 Python 環境：

```bash
# 從原始碼專案目錄安裝為全域指令
cd clichat
uv tool install .

# 安裝完成後，直接在任何目錄執行：
clichat --version
```

若欲更新至最新版程式碼：
```bash
uv tool install --force .
```

### 2.2 透過 `pipx` 安裝
```bash
pipx install .
```

### 2.3 開發環境安裝 (Development Mode)
若是開發者需要直接修改程式碼並執行：
```bash
git clone https://github.com/your-repo/clichat.git
cd clichat
uv sync
uv run clichat
```

---

## 3. 設定檔配置 (Configuration)

`clichat` 的全域配置檔位於 `~/.config/clichat/config.yaml`。

### 3.1 自動產生設定檔
```bash
# 初始化產生預設配置檔
clichat init

# 若已有設定檔，使用 -f 強制覆寫重設
clichat init -f
```

### 3.2 設定檔結構解析

```yaml
# 預設啟動的 Provider
default_provider: "ollama"

# 全域預設模型 (若特定 Provider 未指定 default_model 時使用)
default_model: ""

# 各 Provider 連線設定 (支援 ${ENV_VAR} 自動讀取環境變數)
providers:
  # 1. 本地 Ollama (預設)
  ollama:
    type: "openai_compatible"
    base_url: "http://localhost:11434/v1"
    api_key: "ollama"
    default_model: "llama3.3:latest"

  # 2. Google Antigravity (直連本機 agy CLI，享 Gemini Pro 訂閱額度)
  agy:
    type: "agy"
    default_model: "gemini-3.1-pro-high"

  # 3. OpenCode (直連本機 opencode CLI，享 Zen Free 免費社群模型)
  opencode:
    type: "opencode"
    default_model: "opencode/nemotron-3.5-lightning-free"

  # 4. Google Gemini 官方 API
  gemini:
    type: "gemini"
    api_key: "${GEMINI_API_KEY}"
    default_model: "gemini-2.5-flash"

  # 5. OpenRouter (可動態過濾大量免費與付費模型)
  openrouter:
    type: "openai_compatible"
    base_url: "https://openrouter.ai/api/v1"
    api_key: "${OPENROUTER_API_KEY}"
    default_model: "anthropic/claude-3.5-sonnet"

  # 6. Apple Silicon 本地 MLX (OMLX)
  omlx:
    type: "openai_compatible"
    base_url: "http://localhost:8000/v1"
    api_key: "omlx"
    default_model: "default"

  # 7. NVIDIA NIM API
  nvidia:
    type: "openai_compatible"
    base_url: "https://integrate.api.nvidia.com/v1"
    api_key: "${NVIDIA_API_KEY}"
    default_model: "meta/llama-3.3-70b-instruct"

# MCP 外部工具伺服器掛載 (Model Context Protocol)
mcp_servers:
  filesystem:
    command: "npx"
    args:
      - "-y"
      - "@modelcontextprotocol/server-filesystem"
      - "/Users/candyz/AI"

# 介面偏好設定
ui:
  theme: "monokai"
  stream: true
  markdown_render: true
```

---

## 4. 各 Provider 認證與環境變數設置

為保護金鑰安全，建議在 `~/.zshrc` 或 `~/.bashrc` 中匯出環境變數：

### 4.1 Google Gemini
```bash
export GEMINI_API_KEY="AIzaSyYourGeminiApiKeyHere"
```
可在 [Google AI Studio](https://aistudio.google.com/) 免費取得 API 金鑰。

### 4.2 OpenRouter
```bash
export OPENROUTER_API_KEY="sk-or-v1-YourOpenRouterKeyHere"
```

### 4.3 Google Antigravity (`agy`)
- 確保本機已安裝 Google Antigravity CLI：
  ```bash
  which agy
  ```
- `clichat` 會自動透過子進程調用本機登入憑證，完全無需重複配置 API Key。

### 4.4 OpenCode (`opencode`)
- 確保本機已安裝 `opencode`：
  ```bash
  which opencode
  ```
- 免費享受 Zen Pool 中的免費模型（如 `opencode/nemotron-3.5-lightning-free`）。

---

## 5. Model Context Protocol (MCP) 伺服器整合

`clichat` 完整支援 Anthropic 發起之開放協定 **MCP (Model Context Protocol)**，可輕鬆擴充外部資料庫、瀏覽器或專用工具：

在 `~/.config/clichat/config.yaml` 中增加 `mcp_servers` 區塊：

```yaml
mcp_servers:
  # 掛載記憶體工具
  memory:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-memory"]

  # 掛載特定本機腳本
  custom_tools:
    command: "python"
    args: ["/path/to/mcp_server.py"]
    env:
      DEBUG: "1"
    cwd: "/path/to/workdir"
```

啟動 `clichat --agent` 時，系統會自動啟動子進程連線，並透過 `/tools` 呈現外部掛載的 MCP 工具。

---

## 6. Shell Tab 自動補全配置 (Auto-completion)

`clichat` 內建完整的 Shell 補全生成器，支援 Bash 與 Zsh。

### 6.1 Bash 配置

執行以下指令將補全腳本載入至 `~/.bashrc`：

```bash
# 產生並儲存補全腳本
mkdir -p ~/.local/share/bash-completion/completions
clichat --completion bash > ~/.local/share/bash-completion/completions/clichat

# 或直接於 ~/.bashrc 中 eval
echo 'eval "$(clichat --completion bash)"' >> ~/.bashrc
source ~/.bashrc
```

### 6.2 Zsh 配置

在 `~/.zshrc` 中加入：

```zsh
eval "$(clichat --completion zsh)"
```

重新載入終端後，輸入 `clichat -` 或 `clichat --` 並按下 `Tab` 鍵，即可自動補全所有參數與 Provider 名稱！

---

## 7. 檔案與目錄結構

`clichat` 運行時會自動在使用者家目錄建立以下目錄：

| 目錄路徑 | 用途 |
| :--- | :--- |
| `~/.config/clichat/config.yaml` | 全域主要設定檔 |
| `~/.config/clichat/skills/` | 全域使用者自訂技能目錄（放入 `.md` 即可擴充） |
| `~/.config/clichat/trusted_workspaces.json` | 專案目錄安全信任白名單記錄 |
| `~/.local/share/clichat/history` | REPL 互動歷史紀錄（跨終端保留） |
| `~/.local/share/clichat/sessions/` | 結構化會話 JSON 與 Append-only `.events.jsonl` 事件日誌 |
| `.clichat/skills/` | 特定專案本地專屬技能（依各 repo 自訂） |
