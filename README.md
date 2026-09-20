# cyc

現代化終端 CLI 對話工具，支援本地端模型（Ollama、OMLX）與雲端模型（OpenRouter、NVIDIA NIM、Google Gemini）。

## 功能特性

- **多後端無縫切換**：支援本地 Ollama、OMLX (Apple Silicon MLX)、Google Antigravity (`agy`，直連 Gemini AI Pro 訂閱額度)、OpenCode (`opencode`，直連 Zen free 免費模型) 及各大雲端 API (Gemini, OpenRouter, NVIDIA NIM)。
- **即時 Markdown 串流渲染**：結合 `rich.live.Live`，文字隨生成即時渲染 Markdown 格式、程式碼區塊高亮與排版。
- **互動式 REPL 與智慧補全**：
  - 輸入歷史自動跨終端持久化保存 (`~/.local/share/cyc/history`)。
  - Tab 智慧自動補全 Slash 指令、動態拉取之模型名稱 (`/model `)、提供者名稱 (`/provider `) 及本地檔案路徑 (`/save `, `/load `)。
  - 支援單行與多行編輯模式切換 (`/multiline`)、`Alt+Enter` 隨時插入換行。
  - `Ctrl+C` 訊號優雅中斷當前生成，不崩潰、不中斷對話。
- **會話與 Token 管理**：
  - Context Token 自動估算與超長自動滑動窗口裁切（保障 System Prompt 永遠留存）。
  - 會話支援匯出為 Markdown 或完整結構化 JSON，並可隨時載入續聊。
- **Pipeline 管線模式**：支援 Unix 管道輸入，例如 `cat error.log | cyc "分析此日誌"`。
- **彈性配置**：支援 `~/.config/cyc/config.yaml` 並自動解析環境變數 `${API_KEY}`。

## 安裝與執行

### 快速開始

```bash
# 1. 初始化預設設定檔 (~/.config/cyc/config.yaml)
uv run cyc init

# 2. 啟動互動式聊天 (預設使用本地 Ollama)
uv run cyc

# 3. 指定 Provider 與 Model
uv run cyc -p agy -m "gemini-3.1-pro-high"                             # 使用本機 agy，直連 Gemini Pro 訂閱額度
uv run cyc -p opencode -m "opencode/nemotron-3.5-lightning-free"      # 使用本機 opencode，直連 Zen free 免費模型
uv run cyc -p gemini -m "gemini-2.5-flash"                              # 使用 Google AI Studio API Key
uv run cyc -p ollama -m "llama3.3:latest"

# 4. 單次問答 / Pipeline 模式
uv run cyc "什麼是量子計算？"
cat main.py | uv run cyc "請幫我 code review 這段程式碼"
```

### 全域 CLI 安裝

您可以將 `cyc` 安裝為系統全域命令，在任何終端機目錄下直接呼叫：

```bash
# 方法 A: 透過 uv tool 全域安裝 (推薦)
uv tool install .

# 方法 B: 透過 pipx 全域安裝
pipx install .

# 安裝完成後直接呼叫
cyc
```


- **Autonomous Coding Agent (自主編程代理)**：
  - 核心工具：`read_file`, `write_file`, `replace_file_content`, `run_command`, `list_dir`, `grep_search`, `web_search`, `fetch_url`。
  - **原生 Web Search & Fetch**：內建 `web_search`（支援 SearXNG 隱私搜尋引擎）與 `fetch_url`（智慧抽取網頁乾淨內文與 Markdown，並自動截斷防爆）。
  - **PTC (Programmatic Tool-Calling)**：透過 `run_script` 支援以單一 Turn 執行 Python / Bash 多步驟腳本與管線運算，顯著節省推論輪次。
  - **可插拔 Loop 策略**：支援 `/loop` 動態切換 `standard` (15 輪 ReAct)、`plan` (先規劃後執行)、`minimal` (3 輪評測/快跑)。
  - **強韌性與自我修復**：
    - **工具輸出超大防爆 (Auto Truncate Big Output)**：保留首尾關鍵內容，防止巨大輸出衝垮上下文視窗。
    - **Ctrl+C 優雅中斷 (Graceful Cancel)**：子進程即時清理、自動消毒 session 狀態符合 API schema，REPL 不會崩潰中斷。
    - **API 指數退避重試 (Retry on 429/5xx)**：面對 Rate limit 與伺服器短暫異常，自動以 Jitter 演算法重試。
    - **Tool Error 智能自我修復提示**：工具發生錯誤時自動注入診斷修復建議，引導模型自我更正。
  - **Event-Sourced 與 Session 分支**：全面支援 Append-only `.events.jsonl` 事件源追蹤，並可使用 `/fork` 即時分岔會話實驗分支。
  - **標準 Agent Skills 支援**：支援標準 `<skill_name>/SKILL.md`（YAML frontmatter 與 scripts/references 等子目錄）及單檔 `.md`。自動跨工具探索 Google Antigravity、Claude Code、OpenCode、全域及專案工作區技能。
  - **多代理對話相容**：無縫列出與接續 agy (`gemini`), claude code, pi, opencode 等代理之歷史會話 (`/sessions`, `/resume`)。
- **本地 Shell 快捷執行**：
  - 在 REPL 中隨時輸入 `!<command>`（如 `!git status`、`!ls -la`）即可直接非同步執行本地終端指令，並支援 `Ctrl+C` 即時中止。
- **安全與信任機制**：
  - 專案工作區信任管理 (`/trust [show|allow|deny]`)，首次執行提示授權，限制未信任目錄為唯讀模式。
  - 差異比對預覽：修改檔案時自動生成彩色 Unified Diff 並可互動確認。
  - 支援一鍵還原回退 (`/undo`)，連帶可還原 git uncommitted 修改。

## Slash Commands 與快捷鍵 (在 REPL 模式下)

| 指令 / 快捷鍵 | 說明 |
| :--- | :--- |
| `!<command>` | 本地終端快速執行指令（例如 `!git status`、`!uv run pytest`） |
| :--- | :--- |
| `/help` | 顯示所有指令說明 |
| `/mode <mode>` | 切換交談模式 (chat) 或自主代理模式 (agent) |
| `/loop <strategy> <turns>` | 切換或檢視 Agent Loop 執行策略與回合上限（預設 100 turns） |
| `/tools` | 表格化列出所有已註冊的內建與 MCP 工具及其型態 |
| `/skills` | 列出所有可用技能（內建 commit, test, refactor，全域或專案專屬） |
| `/skill <name>` | 動態載入技能工作流程指引至 Agent 指令集中 |
| `/trust <action>` | 檢視或切換當前專案工作區的信任授權狀態（show, allow, deny） |
| `/sessions <source>` | 列出所有已儲存會話（支援 all, cyc, agy, claude, pi, opencode） |
| `/resume <id>` | 接續或跨代理匯入歷史會話 |
| `/fork <id>` | 將目前會話分岔出獨立分支並立即切換 |
| `/sync <agent>` | 雙向寫回外部代理（支援 agy, claude, pi, opencode，原工具可接續開發） |
| `/models` | 表格化列出當前 Provider 所有可用模型清單 |
| `/model <name>` | 動態切換模型（支援 Tab 自動補全） |
| `/provider <name>` | 動態切換提供者（支援 Tab 自動補全） |
| `/system <prompt>` | 設定或檢視當前 System Prompt |
| `/context <limit>` | 檢視或動態設定 Context Token 上限（支援 200k, 1m, 自適應模型規格） |
| `/compact <ratio>` | 手動壓縮對話上下文（摘要過往歷程、精簡工具輸出） |
| `/usage` | 檢視 Token 累積用量、模型訂閱狀態與 Rate Limit 限額資訊 |
| `/multiline` | 切換多行 / 單行輸入模式 |
| `/save <filepath>` | 儲存會話（`.md` 儲存為 Markdown，`.json` 儲存為結構化會話） |
| `/load <filepath>` | 載入過往的 JSON 會話檔案並接續對話 |
| `/undo` | 回退上一輪對話，並可選擇撤銷工作區未提交之 git 變更 |
| `/clear` | 清空當前對話歷史 |
| `/exit` 或 `/quit` | 退出對話 |

## 完整文件

- 📖 **[使用手冊 (User Manual)](docs/USER_MANUAL.md)**：完整說明對話模式、自主編程代理、PTC 腳本呼叫、Loop 策略、技能庫與 Slash 指令。
- 🚀 **[部署與配置指南 (Deployment Guide)](docs/DEPLOYMENT_GUIDE.md)**：包含全域安裝、設定檔配置、Provider 認證、MCP 工具擴充與 Shell 自動補全設置。
- 📋 **[架構與規劃書](docs/CLI_CHAT_SPEC_AND_PLAN.md)**：設計背景、技術架構與規格演進歷程。
- 🤖 **[Coding Agent 規格書](docs/CODING_AGENT_SPEC_AND_PLAN.md)**：自主編程代理、安全權限審批與架構演進規劃。
- 💬 **[Telegram 與通訊軟體串接計劃](docs/TELEGRAM_INTEGRATION_SPEC_AND_PLAN.md)**：跨裝置行動端遠端控制、非同步任務推播與 HITL 按鈕審批。
- 🌐 **[Web 遠端操控介面實作計劃](docs/WEB_INTERFACE_SPEC_AND_PLAN.md)**：現代化 Web SPA、多欄位即時 Diff 預覽與嵌入式 Web Terminal。

