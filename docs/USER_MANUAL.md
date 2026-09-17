# clichat 使用手冊 (User Manual)

`clichat` 是一款現代化、高效且具備自主編程代理能力的終端 CLI 對話與程式碼輔助工具。它無縫整合本地開源大模型與主流雲端 API，並相容多種常見 AI 代理工具之會話資料。

---

## 1. 快速開始與基礎使用

### 1.1 初始化與啟動

首次使用建議先產生預設設定檔：
```bash
# 產生預設設定檔 (~/.config/clichat/config.yaml)
clichat init

# 啟動互動式終端介面 (預設為對話模式，連線本地 Ollama)
clichat
```

### 1.2 指定提供者 (Provider) 與模型 (Model)

您可以透過 `-p` (`--provider`) 與 `-m` (`--model`) 啟動指定的後端：

```bash
# 1. 使用本地 Google Antigravity (直連 Gemini Pro 訂閱配額)
clichat -p agy -m "gemini-3.1-pro-high"

# 2. 使用本地 OpenCode (直連 Zen Free 免費社群模型)
clichat -p opencode -m "opencode/nemotron-3.5-lightning-free"

# 3. 使用 Google Gemini 官方 API (支援免費層與付費層)
clichat -p gemini -m "gemini-2.5-flash"

# 4. 使用本地 Apple Silicon MLX (OMLX)
clichat -p omlx -m "default"

# 5. 使用 OpenRouter
clichat -p openrouter -m "anthropic/claude-3.5-sonnet"
```

### 1.3 單次查詢與 Unix Pipeline (管線模式)

無需進入互動 REPL，可直接於指令列傳入問題或搭配管道傳遞文字日誌：

```bash
# 直接問答
clichat "請解釋 Python asyncio 的事件迴圈機制"

# 管道輸出與分析
cat app.log | clichat "請分析這些錯誤日誌並列出可能的根因"
git diff | clichat "請為這份 diff 撰寫 Conventional Commit 訊息"
```

---

## 2. 兩種運作模式 (Mode)

`clichat` 支援兩種核心執行模式：

### 2.1 💬 聊天模式 (Chat Mode - 預設)
- 專注於即時串流問答、概念諮詢與文字編輯。
- 結合 `rich.live` 即時排版 Markdown、表格與語法高亮。
- 支援 `<think>` 思考鏈（Thinking Process）專屬折疊面板渲染。

### 2.2 🤖 自主編程代理模式 (Coding Agent Mode)
- 具備自主決策循環（ReAct Agent Loop），模型能主動調用工具讀寫檔案、檢索專案及執行命令。
- 啟動方式：
  ```bash
  # 啟動時直接進入 Agent 模式
  clichat --agent

  # 免確認模式 (自動執行所有工具呼叫)
  clichat --agent -y

  # 唯讀沙箱模式 (禁止任何檔案修改或指令執行)
  clichat --agent --read-only
  ```
- 或在 REPL 中輸入 `/mode agent` 隨時切換。

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
| `MCP Tools` | 擴充 | 透過 Model Context Protocol 動態掛載之外部工具 |

---

## 4. 深度架構特性 (DeepSeek Harness 特性)

### 4.1 PTC (Programmatic Tool-Calling，程式化工具呼叫)
傳統 Agent 需經過多次 round-trip 才能完成「讀取多個檔案 ➔ 數據過濾 ➔ 寫入新檔案」。`run_script` 工具讓模型能夠在單次回合內產出完整 Python/Bash 運算管線，顯著節省 API 延遲與 Token 開銷。

### 4.2 可插拔 Loop 執行策略 (`/loop`)
- `/loop` 可動態切換代理決策策略：
  - `standard`（預設）：15 回合動態 ReAct 循環，平衡效率與工具除錯。
  - `plan`：**先規劃後執行**（Plan-and-Solve），適合大型架構重構或跨模組開發。
  - `minimal`：極簡模式（上限 3 回合），專門用於快速快跑測試與 Benchmark。

### 4.3 專業技能庫 (Skills Management)
`clichat` 提供系統化技能庫，引導 Agent 遵循最佳工程實踐：
- 輸入 `/skills` 查看所有可用技能。
- 輸入 `/skill <name>` 動態載入技能工作流程：
  - `commit`：自動遵循 Conventional Commits 規範。
  - `test`：結構化測試、測試失敗分析與精準修復流程。
  - `refactor`：安全代碼重構（測試保護傘、單一責任原則）。
- **自訂技能擴充**：只要在全域目錄 `~/.config/clichat/skills/<name>.md` 或專案目錄 `.clichat/skills/<name>.md` 放置 Markdown 指引，即可自動掃描並載入。

### 4.4 事件溯源 (Event Sourcing) 與會話分支 (`/fork`)
- 每次對話皆會產生追加寫入（Append-only）的 `.events.jsonl` 日誌，完整記錄系統決策、模型輸入與工具觀察結果。
- 輸入 `/fork <id>`：可隨時將現有對話與工具執行歷程分岔至全新會話分支，進行不同方向的實作嘗試。

---

## 5. 安全與信任機制 (Security & Trust)

1. **目錄信任管理 (`/trust`)**：
   - 首次在未探索的專案目錄執行 Agent 時，`clichat` 會主動詢問是否信任該目錄。
   - 若選擇拒絕或未信任，系統自動鎖定為 **唯讀模式 (Read-Only)**，全面阻擋寫檔與指令執行。
   - 隨時使用 `/trust show`、`/trust allow`、`/trust deny` 管理授權。
2. **彩色 Unified Diff 預覽**：
   - 代理呼叫 `replace_file_content` 時，終端會以紅綠色彩呈現變更對比，經使用者審查確認後才套用修改。
3. **一鍵還原 (`/undo`)**：
   - 隨時輸入 `/undo` 即可退回前一回合對話，並可選擇同步執行 `git restore .` 撤銷工作區所有未提交的檔案修改。

---

## 6. 全指令一覽表 (Slash Commands)

在互動 REPL 環境中，輸入 `/` 即會彈出自動補全選單：

| 指令 | 說明 |
| :--- | :--- |
| `/help` | 顯示所有指令清單與格式說明 |
| `/mode <mode>` | 切換或檢視互動模式 (`chat` 或 `agent`) |
| `/loop` | 切換或檢視 Agent Loop 策略 (`standard`, `plan`, `minimal`) |
| `/tools` | 表格化列出目前已註冊之內建工具與 MCP 外部工具 |
| `/skills` | 列出所有可用技能（內建 commit, test, refactor，全域或專案專屬） |
| `/skill <name>` | 動態載入特定技能工作指引至 Agent 系統提示詞中 |
| `/trust <action>` | 檢視或切換專案工作區信任狀態 (`show`, `allow`, `deny`) |
| `/sessions <source>` | 列出所有已儲存會話（支援 `all`, `clichat`, `agy`, `claude`, `pi`, `opencode`） |
| `/resume <id>` | 接續現有會話或跨工具匯入歷史對話 |
| `/fork <id>` | 將目前會話分岔出獨立分支並立即切換 |
| `/sync <agent>` | 雙向寫回外部代理（例如 `/sync agy`，使原工具亦可接續對話） |
| `/models` | 表格化列出當前 Provider 所有可用模型清單 |
| `/model <name>` | 動態切換模型（支援 Tab 自動補全） |
| `/provider <name>` | 動態切換提供者（支援 Tab 自動補全） |
| `/system <prompt>` | 設定或檢視當前 System Prompt |
| `/tokens` | 表格化顯示當前上下文視窗的 Token 佔比與利用率 |
| `/usage` | 檢視 Token 累積消耗、模型訂閱狀態與 Rate Limit 限額資訊 |
| `/multiline` | 切換單行 / 多行輸入模式（多行模式按 `Esc+Enter` 送出） |
| `/save <filepath>` | 儲存會話（`.md` 存為 Markdown，`.json` 存為結構化會話） |
| `/load <filepath>` | 載入 JSON 會話檔案並接續對話 |
| `/undo` | 回退上一輪對話，並可選擇復原工作區檔案修改 |
| `/clear` | 清空當前對話歷史 |
| `/exit` 或 `/quit` | 退出對話終端 |
