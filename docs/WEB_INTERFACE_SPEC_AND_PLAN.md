# Web 遠端操控介面可行性與實作計劃

本文件評估為 `cyc` 提供現代化 Web 介面以實現本機與區域網路/公網遠端操控之可行性，規劃高內聚低耦合之系統架構、通訊協議與實作藍圖。

---

## 1. 需求背景與目標

`cyc` 目前雖然在終端 CLI 具備流暢的 Rich 即時渲染與補全體驗，但在以下使用場景中，Web 介面能提供質的飛躍：
1. **多裝置跨平台存取**：透過平板（iPad）、筆記型電腦或瀏覽器，直接存取工作站或雲端主機上運行的 `cyc`。
2. **豐富的多欄位視覺化**：
   - 雙欄/三欄視窗排版：左側會話歷程、中間對話主體與思考過程、右側即時檔案預覽（File Tree）與彩色 Unified Diff 比對器。
   - 視覺化 MCP 伺服器狀態與連線拓撲。
   - 一鍵切換模型、Loop 策略與 Token 消耗統計儀表板。
3. **終端擬真（Web Terminal）**：整合 xterm.js，讓使用者在同一個介面無縫執行終端 Shell 任務與 Agent 操作。

---

## 2. 可行性評估 (Feasibility Analysis)

### 2.1 技術選型與架構適配
- **後端框架：FastAPI + Uvicorn (ASGI Native)**：
  - `cyc` 核心完全基於 Python 3.10+ 的原生 `asyncio` 與 `pydantic`。FastAPI 同樣以 Pydantic 與 Asyncio 為基石，兩者天生一對，無需進行任何同步-非同步轉換。
  - 支援 **WebSocket** 與 **Server-Sent Events (SSE)**，能以毫秒級延遲雙向串流 Token、Thought 區塊與工具 Observation 事件。
- **前端架構：現代單頁應用 (SPA) 或輕量輕快方案**：
  - **推薦方案：Next.js / Vite + React + TailwindCSS + Lucide Icons + Monaco Editor (或 CodeMirror 6)**。
  - 前端靜態資源打包後（`npm run build`），可直接由 FastAPI 的 `StaticFiles` 掛載託管為**單一二進位/單一 Python 套件**，使用者無需額外安裝 Node.js，執行 `cyc web` 即可開箱即用。
- **終端虛擬化：xterm.js + WebSocket PTY**：
  - 透過 Python 原生 `pty` / `asyncio.subprocess` 模組，可將本機虛擬偽終端直接投影至前端瀏覽器。

### 2.2 核心安全考量 (Security Safeguards)
由於 Web 介面具備檔案讀寫與 Shell 執行能力，暴露於網路時具備極高安全要求：

| 安全面向 | 風險描述 | 防禦機制 |
| :--- | :--- | :--- |
| **未授權存取** | 公網或區網內任何人皆可執行系統指令 | **Token-Based 身分驗證 (Magic Token / Password)**：啟動時自動產生 32 碼加密隨機 Token（類似 Jupyter Notebook），或設定靜態 Password / JWT；支援 Cookie HttpOnly 儲存。 |
| **跨站請求偽造 (CSRF / CORS)** | 惡意第三方網頁誘騙瀏覽器發送執行請求 | 嚴格配置 CORS 白名單，啟用 WebSocket Origin Header 檢驗與 CSRF Token。 |
| **監聽與封包截獲** | 明文 HTTP 傳輸金鑰與程式碼 | 內建支援自動產生本機 Self-Signed SSL 憑證或支援掛載自訂 HTTPS 憑證；整合反向代理（Nginx / Caddy / Cloudflare Tunnel）。 |
| **目錄越權存取** | Path Traversal (`../../etc/passwd`) | 複用 `cyc` 現有之 `WorkspaceTrustManager` 與路徑檢查機制，將檔案瀏覽與操作嚴格侷限於授權 Workspace 根目錄內。 |

---

## 3. 系統架構設計 (System Architecture)

```mermaid
flowchart TD
    subgraph Browser [瀏覽器客戶端]
        UI[現代 Web SPA\n(React / TailwindCSS)]
        Monaco[Monaco Editor / Diff View]
        Terminal[xterm.js 終端視窗]
    end

    subgraph Cyc_WebServer [cyc Web Server (FastAPI + Uvicorn)]
        Auth[Token / JWT 認證中介軟體]
        REST_API[REST API 路由\n(/api/sessions, /api/models, /api/fs)]
        WS_Agent[WebSocket / SSE 閘道\n(Agent Loop 雙向事件串流)]
        WS_PTY[WebSocket PTY 橋接器\n(直接映射 Bash / Zsh)]
    end

    subgraph Cyc_Core [cyc 核心模組]
        SessionMgr[SessionManager (事件溯源)]
        AgentLoop[AgentLoop (ReAct Engine)]
        ToolRegistry[9 Core Tools + MCP Tools]
        ProviderFactory[Provider Factory (Ollama/agy/Gemini...)]
    end

    Browser <-->|HTTP / Static Assets| REST_API
    Browser <-->|WebSocket: Token & Tool Events| WS_Agent
    Browser <-->|WebSocket: Terminal I/O| WS_PTY
    Auth --> REST_API
    Auth --> WS_Agent
    Auth --> WS_PTY

    WS_Agent <--> AgentLoop
    AgentLoop <--> SessionMgr
    AgentLoop <--> ToolRegistry
    AgentLoop <--> ProviderFactory
    REST_API <--> SessionMgr
```

---

## 4. 前端介面佈局與互動規劃

```text
+------------------------------------------------------------------------------------+
|  [Logo] cyc Web     [Workspace: /Users/candyz/AI/cyc]    [Provider/Model Selector] |
+------------------+-----------------------------------------------+-----------------+
| SESSIONS / FILES | CHAT & AGENT STREAM                           | DIFF & PREVIEW  |
| ---------------- | --------------------------------------------- | --------------- |
| > Recent Session | User: 請幫我重構 SessionManager               | unified diff:   |
| > Feature-Branch | Agent: [Thinking...]                          | - old code      |
|                  | - 正在分析原始碼...                           | + new code      |
| [Files Explorer] |                                               |                 |
| 📁 src/cyc       | [Tool Call: replace_file_content]             | [Approve] [Deny]|
|   📄 cli.py      | Observation: 變更成功                         | --------------- |
|   📄 loop.py     |                                               | TERMINAL DOCK   |
|   📄 config.py   | Agent: 我已完成代碼變更，請確認右側 Diff。     | $ git status    |
|                  +-----------------------------------------------+ $ pytest        |
|                  | [Input Box: 鍵入提示詞或指令...        ] [Send] |                 |
+------------------+-----------------------------------------------+-----------------+
```

### 4.1 核心介面模組
1. **即時雙向串流聊天面板**：
   - 支援折疊的 `<think>` 思考鏈視覺化卡片。
   - 每個 Tool Call 獨立呈現為狀態卡片（包含執行時間、輸入參數 JSON、截斷預覽）。
2. **視覺化 Diff 審批抽屜（Drawer）**：
   - 當 Agent 調用 `replace_file_content` 或 `write_file` 且處於 `INTERACTIVE` 模式時，右側即時彈出語法高亮之前後對比圖，提供 `[Approve]` 與 `[Reject]` 點擊操作。
3. **嵌入式終端（Bottom Terminal Drawer）**：
   - 可一鍵向上拉開底部 xterm.js 終端，即時執行 `git log`, `npm test` 等輔助指令。
4. **工作區與模型設定抽屜**：
   - 直觀查看當前 Token 上限、已耗用百分比進度條、一鍵觸發 `/compact` 壓縮。

---

## 5. 設定檔擴充規格 (`config.yaml`)

```yaml
# ~/.config/cyc/config.yaml 新增 web 區塊
web:
  enabled: false
  host: "127.0.0.1"               # "127.0.0.1" (本機限制) 或 "0.0.0.0" (開放區域網路/公網)
  port: 8888
  auth_token: ""                  # 若為空則每次啟動動態產生一組 32 碼隨機 Token
  cors_origins:
    - "http://localhost:8888"
  ssl_cert: null                  # 可選 SSL 憑證路徑
  ssl_key: null
  enable_terminal: true           # 是否開放嵌入式 Web xterm 終端
```

---

## 6. 實作計劃與里程碑 (Implementation Milestones)

| 階段 | 週期預估 | 核心交付成果 | 驗收標準 |
| :--- | :---: | :--- | :--- |
| **Phase 1: 後端 REST API 與 WebSocket 核心** | 3 天 | 1. 建立 `cyc.web` 模組，引入 `fastapi`, `uvicorn`<br>2. 實作會話列表、模型列表、檔案樹 REST API<br>3. 實作 WebSocket 事件分發器（映射 AgentLoop 事件） | 透過 Postman / 測試腳本能經由 WebSocket 觸發問答並獲取完整 Token 與 Tool Call 串流事件。 |
| **Phase 2: 現代前端 SPA 原型** | 3 天 | 1. 建立基於 Vite/React/TailwindCSS 之 SPA<br>2. 實作即時串流渲染、Markdown 語法高亮與思考摺疊卡<br>3. 支援多會話切換與歷史續聊 | 前端能順暢展示文字串流與工具執行歷程，延遲低於 50ms。 |
| **Phase 3: 視覺化 Diff 審批與 Web Terminal** | 3 天 | 1. 整合 Monaco Editor 差異比對元件<br>2. 實作 HITL 視覺化工具核准/拒絕按鈕<br>3. 引入 xterm.js + PTY 終端 | 變更檔案時能在瀏覽器以紅綠高亮比對修改，並能在 Web 終端直接執行命令。 |
| **Phase 4: 打包內嵌與全域 CLI 命令** | 2 天 | 1. 前端 Build Artifact 內嵌至 Python 套件<br>2. 新增 CLI 指令：`cyc web [--port 8888] [--open]`<br>3. 實作 Magic Token 認證與瀏覽器自動彈跳開啟 | 使用者僅需執行 `cyc web`，即可自動在預設瀏覽器開啟免設定的 Web 介面。 |
