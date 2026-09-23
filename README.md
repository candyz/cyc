# cyc

現代化終端自主編程代理（Autonomous Coding Agent）與多模型 CLI 工具，專為終端極客、研發工程師打造。

以 **Agent-First** 為核心設計架構，支援全自動多步驟程式碼編寫、重構、診斷修復、PTC 腳本運算，並無縫整合本地開源大模型（Ollama、OMLX）與主流雲端旗艦模型（Google Gemini、OpenRouter、NVIDIA NIM、Google Antigravity、OpenCode）。

---

## 🌟 核心特色 (Core Highlights)

- 🤖 **Agent-First 自主編程架構 (Autonomous Coding Agent)**：
  - **預設 Agent 模式**：開箱即具備自我驅動能力，支援閱讀專案、編輯代碼、執行測試與診斷除錯。
  - **純問答免工具快顯捷徑**：輸入以 `?` 開頭（如 `? list 與 tuple 差異`）或 `/chat <prompt>`，即可直接進行極速單輪問答，完全跳過 Agent 工具載入與推論輪次，省時省 Token。
  - **核心工具集**：內建 `read_file`, `write_file`, `replace_file_content`（精準置換＋紅綠 Unified Diff 審批）、`run_command`, `list_dir`, `grep_search`。
  - **互動澄清與決策工具 (`ask_user`)**：Agent 在需求模糊或架構選型時可主動發起單選/多選/自由輸入澄清問答，終端互動選單渲染，避免臆測需求。
  - **代碼庫拓撲地圖 (`repo_map`)**：基於 AST 與通用符號分析，自動抽取專案中 classes、functions、methods 結構地圖，精準掌握工程拓撲。
  - **多層級專案規則體系 (Project Rules)**：自動探索與合併全域規則（`~/.config/cyc/rules/*.md`）與專案規則（`CYC.md`, `AGENTS.md`, `CLAUDE.md`, `.cursorrules` 等），支援防爆預算截斷。
  - **PTC 程式化工具呼叫 (Programmatic Tool-Calling)**：透過 `run_script` 支援以單一 Turn 執行 Python / Bash 多步驟管線運算，顯著節省多輪 API 呼叫。
  - **可插拔 Loop 決策策略 (`/loop`)**：支援動態切換 `standard` (多回合 ReAct)、`plan` (先規劃後執行)、`minimal` (3 輪評測/快跑)，預設 100 turns。
  - **原生聯網與網頁擷取**：內建 `web_search`（整合 SearXNG 隱私搜尋）與 `fetch_url`（智慧抽取網頁乾淨 Markdown 內文並自動截斷防爆）。

- 🛡️ **工業級強韌性與自我修復 (Industrial Resilience)**：
  - **工具輸出超大防爆 (Auto Truncate)**：海量終端日誌自動套用 Head + Tail 截斷，保障 Context Window 安全。
  - **Ctrl+C 優雅中斷 (Graceful Cancel)**：子進程即時中止並自動修復會話狀態符合 API Schema，終端永不崩潰。
  - **API 指數退避重試 (Exponential Backoff with Jitter)**：自動應對 429 Rate Limit 與暫態 5xx 錯誤。
  - **智能診斷自我修復提示 (Self-Repair Hints)**：工具失敗時自動向模型提供修正指引，提升除錯成功率。
  - **專案信任管理 (`/trust`)**：首次進入工作區提示授權，未受信任目錄強制鎖定為唯讀模式 (Read-Only)。

- 🧠 **上下文自適應與事件溯源 (Context & Memory)**：
  - **動態上下文容量與自動壓縮 (`/context`, `/compact`)**：支援指定 200k、1m 或隨模型規格自適應；達 80% 水位時自動摘要過往歷史。
  - **事件溯源與分岔 (`/fork`)**：Append-only `.events.jsonl` 記錄所有決策，支援隨時分岔新會話實驗分支。
  - **一鍵撤銷 (`/undo`)**：復原上一輪對話，並可選擇同步執行 `git restore .` 還原工作區修改。

- 🗂️ **Claude Code 風格互動會話管理器 & 跨代理雙向同步**：
  - **全方位 Session Browser (`cyc -r` / `/sessions manage`)**：具備搜尋欄（即時過濾）、上下鍵切換、空白鍵即時預覽歷史、`Ctrl+R` 重新命名、`Ctrl+D` 刪除、`Ctrl+A` 顯示所有專案、`Ctrl+B` 僅限當前 Git 分支。
  - **多代理無縫匯入 (`/sessions`, `/resume`)**：支援直接列出與接續 Google Antigravity (`agy`), Claude Code (`claude`), Pi Agent (`pi`), OpenCode (`opencode`) 之歷史會話。
  - **雙向寫回橋接 (`/sync <agent>`)**：將 `cyc` 中的開發進度增量寫回外部原生儲存，隨時在原工具接續開發。

- 🔌 **擴充性：標準 Skills 系統與 MCP 支援**：
  - **標準 Agent Skills 規範**：支援標準 `<skill>/SKILL.md` 目錄結構及單檔 `.md`。自動探索 `agy`, `claude`, `opencode`, 全域及專案工作區 Skills。
  - **MCP (Model Context Protocol)**：透過 `config.yaml` 輕鬆掛載外部 Stdio MCP 服務，擴充無限自訂工具。

- 💻 **本地快捷 Shell (`!<cmd>`)**：
  - 在 REPL 中隨時輸入 `!<command>`（如 `!git status`、`!ls -la`）即可直接執行本地終端指令。

- 🌐 **多元使用形態：CLI + Web 介面 + Telegram 機器人**：
  - **終端 CLI**：富文本 Markdown 串流渲染、狀態列顯示、多行編輯切換 (`/multiline`)、Tab 智慧自動補全。
  - **Web 介面 (`cyc --web`)**：現代化三欄 SPA、Monaco 雙欄 Diff 比對審批、xterm.js 嵌入式終端、WebSocket/SSE 雙通道、Token 儀表板。
  - **Telegram 常駐 Bot (`cyc --bot`)**：白名單身分驗證、Inline Keyboard HITL 審批卡片、超長 Patch 檔案附件發送、全天候行動端遠端控制。

---

## 🚀 快速開始 (Quick Start)

### 1. 安裝

您可以透過 `uv` 或 `pipx` 將 `cyc` 安裝為系統全域工具：

```bash
# 透過 uv tool 全域安裝 (推薦)
uv tool install --force .

# 或是本機開發除錯
uv sync
```

### 2. 初始化設定

```bash
# 產生預設設定檔 (~/.config/cyc/config.yaml)
cyc init
```

### 3. 啟動使用

```bash
# 1. 啟動互動終端 (預設為 Agent 模式，連線本地 Ollama)
cyc

# 2. 指定 Provider 與 Model 啟動
cyc -p agy -m "gemini-3.1-pro-high"                             # 使用本地 Google Antigravity 配額
cyc -p opencode -m "opencode/nemotron-3.5-lightning-free"      # 使用本地 OpenCode 免費模型
cyc -p gemini -m "gemini-2.5-flash"                              # 使用 Google Gemini 官方 API
cyc -p openrouter -m "anthropic/claude-3.5-sonnet"              # 使用 OpenRouter
cyc -p ollama -m "llama3.3:latest"                               # 使用本地 Ollama

# 3. 互動式工作會話管理 (Claude Code 風格)
cyc -r                                                           # 開啟互動瀏覽器挑選/搜尋 Session

# 4. 單次問答 / Pipeline 模式
cyc "請檢查專案中的單元測試覆蓋率"
cat main.py | cyc "請為這段代碼編寫型別註解"

# 5. 一鍵檢查更新並自動升級 (如同 pi update / agy update / claude update)
cyc update                                                       # 檢查新版本並自動安裝升級
cyc update --force                                               # 強制重新安裝最新版
```

---

## 💬 運作模式與快速問答語法

`cyc` 預設以 **Agent 模式** 啟動，讓您隨時擁有自主編程助理；同時提供輕量問答捷徑：

| 模式 / 捷徑 | 輸入方式 | 行為說明 |
| :--- | :--- | :--- |
| **Agent Mode (預設)** | 直接輸入需求，提示字元為 `you > ` | 具備完整自主決策循環，主動調用工具讀寫檔案、執行指令與測試。 |
| **快速問答捷徑** | 輸入以 `?` 開頭（如 `? Python GIL 是什麼`） | **跳過工具載入**，直接進行單輪高速串流回應，極速且省 Token。 |
| **`/chat` 指令捷徑** | `/chat <query>` | 同樣直接觸發單輪對話串流問答。 |
| **純交談模式 (Chat)** | `/mode chat` 或啟動帶 `--chat` | 提示字元為 `[chat] you > `，整場會話維持純交談問答模式。 |

---

## ⌨️ Slash Commands 指令一覽表

在 REPL 互動環境中，輸入 `/` 即會彈出自動補全選單，輸入 `!` 可直接執行本地 Shell 指令：

| 指令 / 快捷鍵 | 說明 |
| :--- | :--- |
| `!<command>` | 本地 Shell 快捷執行（例如 `!git status`、`!uv run pytest`） |
| `/help` | 顯示所有指令清單與格式說明 |
| `/mode <mode>` | 切換或檢視互動模式 (`agent` 或 `chat`) |
| `/chat <query>` | 快速純問答（亦可直接以 `? <query>` 為前綴），繞過工具調用 |
| `/loop <strategy> <turns>` | 切換或檢視 Agent Loop 策略與回合上限 (`standard`, `plan`, `minimal`) |
| `/tools` | 表格化列出目前已註冊之內建工具與 MCP 外部工具 |
| `/skills` | 列出所有可用技能（內建 commit, test, refactor，全域或專案專屬） |
| `/skill <name>` | 動態載入特定技能工作指引至 Agent 系統提示詞中 |
| `/trust <action>` | 檢視或切換專案工作區信任狀態 (`show`, `allow`, `deny`) |
| `/sessions <source>` | 列出所有已儲存會話（支援 `all`, `cyc`, `agy`, `claude`, `pi`, `opencode`） |
| `/sessions manage` | 開啟互動式會話管理器（支援搜尋、預覽、改名、刪除與接續） |
| `/sessions prune [n]` | 清理訊息數小於等於 n 的空會話或測試會話 |
| `/resume <id>` | 接續現有會話或跨工具匯入歷史對話 |
| `/rename <title>` | 為目前會話設定語意化標題 |
| `/fork <id>` | 將目前會話分岔出獨立分支並立即切換 |
| `/sync <agent>` | 雙向寫回外部代理（支援 `agy`, `claude`, `pi`, `opencode`，原工具可接續開發） |
| `/models` | 表格化列出當前 Provider 所有可用模型清單 |
| `/model <name>` | 動態切換模型（支援 Tab 自動補全） |
| `/provider <name>` | 動態切換提供者（支援 Tab 自動補全） |
| `/system <prompt>` | 設定或檢視當前 System Prompt |
| `/context <limit>` | 顯示或動態設定當前上下文視窗的 Token 上限（支援 200k, 1m） |
| `/compact <ratio>` | 手動壓縮對話上下文（摘要過往歷程、精簡工具輸出） |
| `/usage` | 檢視 Token 累積消耗、模型訂閱狀態與 Rate Limit 限額資訊 |
| `/multiline` | 切換單行 / 多行輸入模式（多行模式按 `Esc+Enter` 送出） |
| `/save <filepath>` | 儲存會話（`.md` 存為 Markdown，`.json` 存為結構化會話） |
| `/load <filepath>` | 載入 JSON 會話檔案並接續對話 |
| `/undo` | 回退上一輪對話，並可選擇復原工作區未提交的檔案修改 |
| `/update [force]` | 檢查遠端 GitHub 版本並自動執行一鍵在線更新升級 |
| `/clear` | 清空當前對話歷史 |
| `/exit` 或 `/quit` | 退出對話終端 |

---

## 🌐 Web 與 Bot 服務模式

### Web 遠端控制控制台 (`cyc --web`)
```bash
# 啟動 Web 服務並自動開啟瀏覽器 (預設連接 http://127.0.0.1:8888)
cyc --web

# 自訂連接埠與 Token
cyc --web --port 9000 --token "your-secret-token" --no-open
```
- 內建工作區檔案樹、Monaco 差異審批編輯器、xterm.js 嵌入式終端機、雙向 WebSocket 即時串流。

### Telegram 遠端通訊機器人 (`cyc --bot`)
```bash
# 啟動 Telegram Bot 常駐閘道
cyc --bot --bot-token "your-telegram-bot-token"
```
- 支援手機端 Inline Keyboard 互動按鈕審批、長補丁自動轉發 `.patch` 檔案、白名單安全存取控制。

---

## 📖 完整文件導引

- 📘 **[使用手冊 (User Manual)](docs/USER_MANUAL.md)**：完整說明對話模式、自主編程代理、PTC 腳本呼叫、Loop 策略、技能庫與 Slash 指令。
- 🚀 **[部署與配置指南 (Deployment Guide)](docs/DEPLOYMENT_GUIDE.md)**：包含全域安裝、設定檔配置、Provider 認證、MCP 工具擴充與 Shell 自動補全設置。
- 📋 **[架構與規劃書](docs/CLI_CHAT_SPEC_AND_PLAN.md)**：設計背景、技術架構與規格演進歷程。
- 🤖 **[Coding Agent 規格書](docs/CODING_AGENT_SPEC_AND_PLAN.md)**：自主編程代理、安全權限審批與架構演進規劃。
- 💬 **[Telegram 與通訊軟體串接計劃](docs/TELEGRAM_INTEGRATION_SPEC_AND_PLAN.md)**：跨裝置行動端遠端控制、非同步任務推播與 HITL 按鈕審批。
- 🌐 **[Web 遠端操控介面實作計劃](docs/WEB_INTERFACE_SPEC_AND_PLAN.md)**：現代化 Web SPA、多欄位即時 Diff 預覽與嵌入式 Web Terminal。
- 🐧 **[Daemon 背景常駐範本](docs/daemon/)**：包含 Linux `systemd` 與 macOS `launchd` 服務範本。
