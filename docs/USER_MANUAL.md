# cyc 使用手冊 (User Manual)

`cyc` 是一款現代化、高效且具備自主編程代理能力的終端 CLI 對話與程式碼輔助工具。它無縫整合本地開源大模型與主流雲端 API，並相容多種常見 AI 代理工具之會話資料。

---

## 1. 快速開始與基礎使用

### 1.1 初始化與啟動

首次使用建議先產生預設設定檔：
```bash
# 產生預設設定檔 (~/.config/cyc/config.yaml)
cyc init

# 啟動互動式終端介面 (預設為對話模式，連線本地 Ollama)
cyc
```

### 1.2 指定提供者 (Provider) 與模型 (Model)

您可以透過 `-p` (`--provider`) 與 `-m` (`--model`) 啟動指定的後端：

```bash
# 1. 使用本地 Google Antigravity (直連 Gemini Pro 訂閱配額)
cyc -p agy -m "gemini-3.1-pro-high"

# 2. 使用本地 OpenCode (直連 Zen Free 免費社群模型)
cyc -p opencode -m "opencode/nemotron-3.5-lightning-free"

# 3. 使用 Google Gemini 官方 API (支援免費層與付費層)
cyc -p gemini -m "gemini-2.5-flash"

# 4. 使用本地 Apple Silicon MLX (OMLX)
cyc -p omlx -m "default"

# 5. 使用 OpenRouter
cyc -p openrouter -m "anthropic/claude-3.5-sonnet"
```

### 1.3 單次查詢與 Unix Pipeline (管線模式)

無需進入互動 REPL，可直接於指令列傳入問題或搭配管道傳遞文字日誌：

```bash
# 直接問答
cyc "請解釋 Python asyncio 的事件迴圈機制"

# 管道輸出與分析
cat app.log | cyc "請分析這些錯誤日誌並列出可能的根因"
git diff | cyc "請為這份 diff 撰寫 Conventional Commit 訊息"
```

---

## 2. 兩種運作模式 (Mode) 與快速問答捷徑

`cyc` 採用 **Agent-First** 設計架構，預設進入自主編程代理模式，同時支援極速問答語法糖：

### 2.1 🤖 自主編程代理模式 (Coding Agent Mode - 預設)
- **開箱即用**：預設提示字元為 `you > `，具備自主決策循環（ReAct Agent Loop），模型能主動調用工具讀寫檔案、檢索專案及執行命令。
- 啟動與控制方式：
  ```bash
  # 預設直接啟動 Agent 模式
  cyc

  # 免確認模式 (自動執行所有工具呼叫)
  cyc -y (或 cyc --agent -y)

  # 唯讀沙箱模式 (禁止任何檔案修改或指令執行)
  cyc --read-only

  # 臨時以純交談模式啟動：
  cyc --chat
  ```
- **全域預設配置 (`~/.config/cyc/config.yaml`)**：
  ```yaml
  agent:
    default_mode: "agent"  # 預設為 agent (命令列可使用 --chat 臨時切換為純交談)
    auto_approve: false    # 是否免確認自動放行變更工具
    default_trust: null    # 工作區信任策略 (true/false/null)
  ```

### 2.2 ⚡ 快速問答捷徑 (Quick Chat Shortcuts)
在預設的 Agent 模式下，若您只是想詢問概念問題或進行簡單諮詢，完全**不需要**切換模式：
- **`?` 前綴捷徑**：在輸入開頭加上 `?`，例如 `? list 與 tuple 有何差別？`，系統會直接觸發單輪串流文字回覆，**完全不載入工具與啟動 Agent Loop**，極速省時且省 Token。
- **`/chat` 指令捷徑**：輸入 `/chat <query>`（例如 `/chat 寫一個正則表達式驗證 Email`），同樣直接執行高速純文字問答。

### 2.3 💬 純交談模式 (Chat Mode)
- 當透過 `/mode chat` 或命令列 `--chat` 進入純聊天模式時，提示字元將顯示為 `[chat] you > `。
- 專注於傳統即時串流問答、概念諮詢與文字編輯，整場會話皆不使用 Agent 工具。
- 結合 `rich.live` 即時排版 Markdown、表格與語法高亮，並支援 `<think>` 思考鏈折疊渲染。
- 隨時可輸入 `/mode agent` 切換回自主代理模式。

---

## 3. 內建 Agent 工具 (Agent Tools)

當處於 Agent 模式時，代理可用以下工具：

| 工具名稱 | 類別 | 說明 |
| :--- | :---: | :--- |
| `read_file` | 唯讀 | 讀取檔案全文或指定行號區間（支援行號標註） |
| `write_file` | 變更 | 建立新檔案或覆寫現有檔案 |
| `replace_file_content` | 變更 | 精確定位並置換指定文字區塊（自動彩色 Unified Diff 預覽） |
| `run_command` | 變更 | 執行 Shell 指令（含安全提示與逾時保護） |
| `run_script` | 變更 | **PTC 模式**：執行多行 Python 或 Bash 腳本，單回合批次處理 |
| `list_dir` | 唯讀 | 列出目錄樹狀結構、檔案大小與屬性 |
| `grep_search` | 唯讀 | 在專案內使用正則表達式快速檢索文字與程式碼符號 |
| `web_search` | 唯讀 | **聯網搜尋**：連接 SearXNG 實例進行隱私且即時的網路資訊檢索 |
| `fetch_url` | 唯讀 | **網頁擷取**：抓取 URL 網頁內容，智慧提取乾淨文字/Markdown 並自動截斷防爆 |
| `MCP Tools` | 擴充 | 透過 Model Context Protocol 動態掛載之外部工具 |

---

## 4. 深度架構特性 (DeepSeek Harness 特性)

### 4.1 PTC (Programmatic Tool-Calling，程式化工具呼叫)
傳統 Agent 需經過多次 round-trip 才能完成「讀取多個檔案 ➔ 數據過濾 ➔ 寫入新檔案」。`run_script` 工具讓模型能夠在單次回合內產出完整 Python/Bash 運算管線，顯著節省 API 延遲與 Token 開銷。

### 4.2 可插拔 Loop 執行策略與上限調整 (`/loop`)
- `cyc` 預設 Agent 思考與工具執行上限為 **100 回合**（可於 `config.yaml` 的 `agent.max_turns` 設定，或透過啟動參數 `--max-turns <int>` 覆蓋）。
- `/loop` 指令支援動態切換決策策略與調整單一會話回合上限：
  - `standard`（預設）：標準多回合 ReAct 循環，平衡效率與工具調度。
  - `plan`：**先規劃後執行**（Plan-and-Solve），適合大型架構重構或跨模組開發。
  - `minimal`：極簡模式（上限 3 回合），專門用於快速快跑測試與 Benchmark。
  - **指令語法**：
    - `/loop`：檢視目前策略與最大回合上限。
    - `/loop <strategy>`：切換策略（如 `/loop plan`）。
    - `/loop <turns>`：調整回合上限（如 `/loop 100` 或 `/loop 50`）。
    - `/loop <strategy> <turns>`：同時切換策略與設定回合數（如 `/loop plan 80`）。

### 4.3 動態模型上下文視窗與自動壓縮 (`/context` / `/compact`)
- **狀態列即時顯示 Context**：狀態列改為 `Context: <current>/<limit>`，清楚呈現上下文記憶體的目前使用水位。
- **自動壓縮機制 (Auto-Compaction)**：
  - 當上下文使用量達到 **80%** 時（可於 `config.yaml` 的 `agent.compact_threshold` 自訂，如 `0.80`），系統將自動啟動 Compact 演算法。
  - 先精簡過長之工具 Observation 輸出，再將過往歷史摘要整合成對話摘要快照，保留最新關鍵對話，避免觸發硬性記憶抹除。
- **手動壓縮指令 (`/compact`)**：
  - 輸入 `/compact` 隨時手動觸發上下文壓縮。
  - 支援指定壓縮目標比例（例如 `/compact 50%` 或 `/compact 0.4`）。
- **動態上限調整 (`/context`)**：
  - `/context`：顯示當前 Token 估算量、上下文視窗上限與利用率。
  - `/context <limit>`：動態調整上限，支援 `k` / `m` 縮寫（例如 `/context 200k`、`/context 1m`、`/context 128000`）。


### 4.4 跨代理標準技能庫 (Standard Agent Skills)
`cyc` 全面遵循並相容現代 AI Agent 行業標準 Skills 規範（如 Google Antigravity / Claude Code / Codex / OpenCode）：
- **標準 Package 結構**：支援 `<skill_name>/SKILL.md`（含 YAML Frontmatter），以及可選的 `scripts/`、`references/`、`resources/`、`examples/` 輔助目錄。
  ```text
  skills/<skill_name>/
  ├── SKILL.md          # 核心流程指引（含 name, description, version 等 YAML 前置標籤）
  ├── scripts/          # 可執行腳本與工具封裝
  └── references/       # 詳細技術文件與手冊（需要時漸進查閱，節省上下文）
  ```
- **單檔 Markdown**：亦相容極簡的 `<skill_name>.md` 技能指引。
- **多代理與跨工具自動探索 (Auto-Discovery)**：
  - **系統內建**：`commit`（Conventional Commits）、`test`（結構化測試與調錯）、`refactor`（安全重構）。
  - **Google Antigravity / Gemini**：自動探索 `~/.gemini/antigravity-cli/builtin/skills/` 與 `~/.gemini/skills/`。
  - **Claude Code**：自動探索 `~/.claude/skills/`（如現有的 `prompt-master`、`agent-reach` 等）。
  - **OpenCode**：自動探索 `~/.config/opencode/skills/`。
  - **全域與自訂設定**：`~/.config/cyc/skills/` 及 `config.yaml` 的 `skills_dirs` 清單。
  - **專案工作區規範**：依優先順序載入專案內的 `.agents/skills/`、`.claude/skills/`、`.cyc/skills/` 或 `skills/`。
- **指令用法**：
  - 輸入 `/skills` 表格化列出所有可用技能、其所屬來源（`AGY`, `CLAUDE`, `WORKSPACE`, `BUILT-IN`）與輔助套件說明。
  - 輸入 `/skill <name>` 動態載入技能工作流程至 Agent 指令集中。

### 4.5 事件溯源 (Event Sourcing) 與會話分支 (`/fork`)
- 每次對話皆會產生追加寫入（Append-only）的 `.events.jsonl` 日誌，完整記錄系統決策、模型輸入與工具觀察結果。
- 輸入 `/fork <id>`：可隨時將現有對話與工具執行歷程分岔至全新會話分支，進行不同方向的實作嘗試。

### 4.6 雙向寫回橋接器 (Two-Way Bridge / `/sync`)
`cyc` 不僅能讀取與接續各大外部 AI 編程代理的歷史對話，更能將在 `cyc` 產生的新對話回合、思考過程與工具呼叫**無縫增量寫回**外部代理原生儲存結構中，實現雙向任意切換：
- **Google Antigravity (`agy`)**：寫回 `~/.gemini/antigravity-cli/brain/<uuid>/.system_generated/logs/transcript.jsonl`。
- **Claude Code (`claude`)**：寫回 `~/.claude/projects/<slug>/<session>.jsonl`。
- **Pi Agent (`pi`)**：寫回 `~/.pi/agent/sessions/*/<session>.jsonl`。
- **OpenCode (`opencode`)**：寫回 SQLite 資料庫 `~/.local/share/opencode/opencode.db`（自動處理 `session`, `message`, `part` 關聯與微秒級時間戳）。
- **指令用法**：
  ```bash
  /sync              # 自動識別原始代理來源並增量寫回
  /sync claude       # 明確指定寫回為 Claude Code 會話
  ```

### 4.7 原生聯網搜尋與網頁擷取 (Web Search & Fetch)
`cyc` 內建開箱即用的聯網查詢與資料抓取能力，無需額外配置複雜外掛：
- **`web_search` (SearXNG 整合)**：
  - 預設可連接自架或區域網路內的 SearXNG 實例（例如 `http://192.168.10.4:8080`），亦可於 `config.yaml` 或環境變數 `SEARXNG_URL` 自訂。
  - 模型可指定查詢關鍵字 `query` 與數量 `max_results`（預設 5 筆），系統回傳標題、URL 與精簡內文摘要，供 Agent 作為事實查核與最新資訊參考。
- **`fetch_url` (智慧網頁抽取)**：
  - 給定任意 HTTP/HTTPS 網址，系統自動抓取 HTML 並以純 Python 正則將其清洗為結構化純文字 / Markdown 內容（自動過濾 `<script>`、`<style>`、`<nav>` 等雜訊標籤）。
  - 支援 `max_chars` 限制（預設 8,000 字元，上限 30,000 字元），搭配防爆截斷機制，保障上下文視窗安全。

### 4.8 本地快捷 Shell 執行 (`!<command>`)
在 REPL 互動環境中，想要快速查看本地狀態（例如 Git、檔案清單或環境變數）而無需讓 Agent 進入推論循環：
- 直接在輸入開頭加上驚嘆號 `!`，例如：
  ```bash
  > !git status
  > !ls -la src/cyc
  > !uv run pytest
  ```
- 系統會直接以非同步子進程執行，即時印出 stdout/stderr，且按下 `Ctrl+C` 可立即終止子進程而不會退出 `cyc`。

### 4.9 系統強韌性與自我修復防護機制 (Stability & Resilience)
為確保長時間自主代理循環不崩潰、不爆上下文，`cyc` 提供全方位的防護網絡：
1. **工具輸出超大防爆 (Auto Truncate Big Output)**：
   - 當工具呼叫（如 `run_command`、`read_file`、`run_script`）產生海量輸出（例如 `npm test` 印出數萬行日誌）時，系統自動啟用 **Head + Tail 截斷策略**（保留前段與末段關鍵資訊，中間插入省略標記與字元統計），防止 context window 一擊被塞爆。
2. **Ctrl+C 優雅中斷 (Graceful Cancellation in Agent Loop)**：
   - 使用者在 Agent 思考或執行工具途中按下 `Ctrl+C` 時，系統不會直接異常跳出，而是：
     - 即時發送 SIGKILL 終止當前運行的子進程。
     - 自動呼叫 `sanitize_cancelled_state` 修復 Session 歷史（補齊 `[Cancelled by user]` 工具回傳），使上下文維持合法 API Schema，避免下一輪對話因「有 tool_calls 卻無對應 tool 訊息」報錯。
3. **API 指數退避重試 (Exponential Backoff with Jitter)**：
   - 自動捕捉 HTTP 429 (Rate Limit)、500、502、503、504 等瞬態錯誤。
   - 預設進行最多 3 次重試，並加入 Full Jitter 隨機延遲，有效緩解高併發衝撞。
4. **Tool Error 智能自我修復提示 (Diagnostic Self-Repair Hints)**：
   - 當工具執行拋出常見錯誤（如 `FileNotFoundError`, `IsADirectoryError`, `SyntaxError`, `KeyError`, `PermissionError`, 指令逾時等）時，系統除了記錄原始錯誤訊息，還會自動在 Observation 末尾注入 `[Diagnostic Self-Repair Hint]`，指引模型「如何換用正確參數或替代工具重新嘗試」，顯著提升自主調錯成功率。

---

## 5. 安全與信任機制 (Security & Trust)

1. **目錄信任管理 (`/trust`)**：
   - 首次在未探索的專案目錄執行 Agent 時，`cyc` 會主動詢問是否信任該目錄。
   - 若選擇拒絕或未信任，系統自動鎖定為 **唯讀模式 (Read-Only)**，全面阻擋寫檔與指令執行。
   - 隨時使用 `/trust show`、`/trust allow`、`/trust deny` 管理授權。
2. **彩色 Unified Diff 預覽**：
   - 代理呼叫 `replace_file_content` 時，終端會以紅綠色彩呈現變更對比，經使用者審查確認後才套用修改。
3. **一鍵還原 (`/undo`)**：
   - 隨時輸入 `/undo` 即可退回前一回合對話，並可選擇同步執行 `git restore .` 撤銷工作區所有未提交的檔案修改。

---

## 6. 全指令一覽表 (Slash Commands 與快捷鍵)

在互動 REPL 環境中，輸入 `/` 即會彈出自動補全選單，輸入 `!` 可直接執行本地終端指令：

| 指令 / 快捷鍵 | 說明 |
| :--- | :--- |
| `!<command>` | 本地 Shell 快捷執行（例如 `!git status`、`!ls`） |
| :--- | :--- |
| `/help` | 顯示所有指令清單與格式說明 |
| `/mode <mode>` | 切換或檢視互動模式 (`agent` 或 `chat`) |
| `/chat <query>` | 快速純問答（亦可直接以 `? <query>` 前綴），繞過 Agent 工具調用 |
| `/loop <strategy> <turns>` | 切換或檢視 Agent Loop 策略與回合上限 (`standard`, `plan`, `minimal`) |
| `/tools` | 表格化列出目前已註冊之內建工具與 MCP 外部工具 |
| `/skills` | 列出所有可用技能（內建 commit, test, refactor，全域或專案專屬） |
| `/skill <name>` | 動態載入特定技能工作指引至 Agent 系統提示詞中 |
| `/trust <action>` | 檢視或切換專案工作區信任狀態 (`show`, `allow`, `deny`) |
| `/sessions <source>` | 列出所有已儲存會話（支援 `all`, `cyc`, `agy`, `claude`, `pi`, `opencode`） |
| `/sessions manage` | 開啟互動式會話管理器（支援搜尋、預覽、改名、刪除與接續） |
| `/resume <id>` | 接續現有會話或跨工具匯入歷史對話 |
| `/fork <id>` | 將目前會話分岔出獨立分支並立即切換 |
| `/sync <agent>` | 雙向寫回外部代理（支援 `agy`, `claude`, `pi`, `opencode`，自動或手動指定，原工具可接續開發） |
| `/models` | 表格化列出當前 Provider 所有可用模型清單 |
| `/model <name>` | 動態切換模型（支援 Tab 自動補全） |
| `/provider <name>` | 動態切換提供者（支援 Tab 自動補全） |
| `/system <prompt>` | 設定或檢視當前 System Prompt |
| `/context <limit>` | 表格化顯示或動態設定當前上下文視窗的 Token 佔比與利用率 |
| `/compact <ratio>` | 手動壓縮對話上下文（摘要過往歷程、精簡工具輸出） |
| `/usage` | 檢視 Token 累積消耗、模型訂閱狀態與 Rate Limit 限額資訊 |
| `/multiline` | 切換單行 / 多行輸入模式（多行模式按 `Esc+Enter` 送出） |
| `/save <filepath>` | 儲存會話（`.md` 存為 Markdown，`.json` 存為結構化會話） |
| `/load <filepath>` | 載入 JSON 會話檔案並接續對話 |
| `/undo` | 回退上一輪對話，並可選擇復原工作區檔案修改 |
| `/clear` | 清空當前對話歷史 |
| `/exit` 或 `/quit` | 退出對話終端 |

---

## 7. 🌐 Web 遠端操控介面 (Web Interface)

`cyc` 內建現代化 Web 遠端控制介面，支援在本地或遠端瀏覽器中監控、驅動 Agent 運作，並即時檢視檔案樹與執行過程。

### 7.1 啟動 Web 伺服器
```bash
# 基本啟動（自動產生隨機 Token 並開啟瀏覽器）
cyc web

# 指定監聽位址與埠號
cyc web --host 0.0.0.0 --port 8080

# 指定固定安全 Token，且啟動時不自動開啟瀏覽器
cyc web --token my-secret-token --no-open
```

### 7.2 主要功能特色
1. **即時雙向串流 (WebSocket Streaming)**：即時視覺化 Assistant 思考過程、工具呼叫 (`tool_call`) 與執行結果 (`observation`)。
2. **三欄現代化 SPA 介面**：
   - **左側欄**：歷史會話清單（支援檢視與一鍵切換）及工作區檔案樹瀏覽器。
   - **中央主聊天區**：支援 Markdown 渲染、程式碼高亮、免審批模式 (Auto Approve) 與隨時中斷按鈕 (Cancel)。
   - **右側抽屜**：詳細工具執行輸出與即時程式碼 Diff 預覽。
3. **HITL 視覺化審批流程與 Monaco Editor 雙欄比對**：
   - 取消勾選「免確認 (Auto Approve)」時，Agent 呼叫破壞性或檔案修改工具（如 `replace_file_content`, `write_file`, `run_command`）時會暫停執行。
   - 整合專業 **Monaco Editor 雙欄行號對齊差異編輯器 (Side-by-Side Diff)**，清楚高亮新增與刪除內容，等待使用者點擊 `[Approve]` 核准或 `[Deny]` 拒絕。
4. **Agent 循環策略與輪數動態切換**：
   - 輸入列支援隨時切換 Loop 策略（`standard`, `plan`, `minimal`）與設定最大執行輪數上限（`Max Turns`）。
5. **雙串流通道支援 (WebSocket & SSE)**：
   - 預設採用低延遲雙向 WebSocket (`/ws/agent`)。
   - 亦支援切換為標準 HTTP **Server-Sent Events (`/api/events/sse`)** 串流通道，穿越企業代理或防火牆更穩定。
6. **內嵌式 Web Terminal (xterm.js + PTY Bridge)**：
   - 點擊頂部 `💻 Terminal` 按鈕即可自底部拉出擬真 Web 終端。
   - 透過 `/ws/terminal` 橋接系統原生 PTY（Bash / Zsh），直接於瀏覽器內執行 `git status`, `pytest` 等 Shell 指令。
7. **Token 消耗儀表板與一鍵上下文壓縮 (`⚡ Compact`)**：
   - 頂部導覽列即時顯示目前 Session 的 Token 佔比進度條（色彩隨水位自綠變黃轉紅）。
   - 支援點擊 `⚡ Compact` 按鈕，直接呼叫後端 `/api/sessions/{id}/compact` 對過長歷史進行摘要壓縮並精簡工具輸出。
8. **視覺化 MCP 伺服器狀態與連線拓撲 (`🔌 MCP Servers`)**：
   - 右側抽屜提供專屬 MCP 分頁，即時列出所有配置之 MCP Server 名稱、可執行檔路徑、工作目錄與健康連線狀態（`ready` / `executable_not_found`）。
9. **安全防護與 SSL/TLS**：
   - 內建 Token 認證中介層（URL Token 與 HTTP Bearer Header 雙重支援）。
   - 工作區路徑檢查，嚴格防止目錄遍歷 (Path Traversal)。
   - 支援於 `config.yaml` 中配置 `ssl_cert` 與 `ssl_key` 啟用 HTTPS / WSS 加密傳輸。

---

## 8. 🤖 Telegram 通訊軟體閘道 (Chatbot Gateway)

`cyc` 內建 Telegram Bot 閘道服務，讓您隨時在外透過手機 Telegram 即可遠端操控主機上的 `cyc` 執行編程、巡檢或會話互動。

### 8.1 設定方式 (`~/.config/cyc/config.yaml`)
```yaml
bot:
  enabled: true
  platform: "telegram"
  telegram:
    token: "${TELEGRAM_BOT_TOKEN}"    # 從 @BotFather 取得之 Bot Token
    allowed_user_ids:                # 允許控制的使用者 Telegram ID 白名單（避免惡意未授權調用）
      - 123456789
    workspace_path: "~/Projects/my-app" # 指定遠端工作目錄（預設為啟動當前目錄）
    streaming_throttle_seconds: 1.2  # 訊息更新節流間隔（避免觸發 Telegram 429 限制）
    auto_approve: false              # 是否免確認自動放行變更工具
```

### 8.2 啟動 Bot 服務
```bash
# 基本啟動（讀取 config.yaml）
cyc bot

# 亦可使用命令列旗標指定 Token
cyc bot --bot-token "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
```

### 8.3 支援指令與特色
1. **白名單安全存取驗證**：嚴格阻絕未授權之第三方帳號，僅允許白名單 `allowed_user_ids` 發起對話。
2. **HITL 視覺化審批按鈕 (Inline Keyboard)**：
   - 當 Agent 欲執行 `write_file`, `replace_file_content` 或 `run_command` 時，Bot 會傳送包含參數摘要與 Unified Diff 預覽的卡片。
   - 附帶 `[ ✅ Approve ]` 與 `[ ❌ Deny ]` 內嵌按鈕，手機一鍵點擊即可核准或阻擋工具執行。
3. **防 Rate Limit 節流串流與智慧長訊息分割**：
   - 生成過程依設定間隔平滑編輯訊息 Bubble，不觸發 Telegram API 限額。
   - 超長程式碼輸出自動切割為多則訊息，並確保 Markdown 標籤修復不破版。
4. **專屬 Telegram 指令集**：
   - `/start`：顯示歡迎介面、工作目錄、目前模型與指令清單。
   - `/mode <agent|chat>`：即時切換自主 Agent 迴圈或純交談 Chat 模式。
   - `/model [name]`：查看或切換模型（未帶參數時自動彈出 Inline Keyboard 列表按鈕供點擊切換）。
   - `/cd <path>`：動態切換遠端工作目錄（支援絕對路徑或相對路徑）。
   - `/status`：查看當前工作目錄、會話 ID、使用模型、歷史訊息數與審批模式。
   - `/undo`：回退上一輪會話歷程。
   - `/stop`：緊急中斷正在背景執行的 Agent 任務。
   - `/clear`：清空當前會話歷史。
   - `!<command>`：快速執行本機 Shell 指令（例如 `!git status`, `!pytest`），輸出超過長度時自動轉換為文字附件發送。
5. **大型 Diff 與輸出自動轉檔案附件**：
   - 當變更範圍過長時，自動打包為 `change.patch` 附件上傳，兼顧閱讀與手機下載保存。

### 8.4 背景常駐服務 (Daemon Setup)
`cyc` 於 `docs/daemon/` 提供主流平台的系統常駐服務範本：
- **Linux (`systemd`)**：[`docs/daemon/cyc-bot.service`](file:///Users/candyz/AI/agy/cyc/docs/daemon/cyc-bot.service)
  ```bash
  mkdir -p ~/.config/systemd/user
  cp docs/daemon/cyc-bot.service ~/.config/systemd/user/
  systemctl --user daemon-reload
  systemctl --user enable --now cyc-bot
  ```
- **macOS (`launchd`)**：[`docs/daemon/com.candyz.cyc-bot.plist`](file:///Users/candyz/AI/agy/cyc/docs/daemon/com.candyz.cyc-bot.plist)
  ```bash
  cp docs/daemon/com.candyz.cyc-bot.plist ~/Library/LaunchAgents/
  launchctl load ~/Library/LaunchAgents/com.candyz.cyc-bot.plist
  ```

