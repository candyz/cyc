# Telegram 與通訊軟體串接可行性與實作計劃

本文件詳細評估 `cyc` 串接 Telegram、Discord、Slack 等主流通訊軟體的技術可行性，並規劃系統架構、安全性授權與分階段實作藍圖。

---

## 1. 需求背景與目標

`cyc` 目前定位為強大之終端 CLI 對話與自主編程代理工具。透過串接通訊軟體（以 Telegram 為首選首發目標，後續擴充 Discord / Slack），可實現：
1. **跨裝置行動端存取**：在外透過手機 Telegram 即可向在家中或雲端伺服器運行的 `cyc` 發起編程提問、伺服器巡檢或執行工作流。
2. **非同步長任務通知**：當自主代理（Coding Agent）執行耗時較長的測試或排程重構任務時，主動推播完成通知、Git Diff 與錯誤報告。
3. **遠端人機協同審批（HITL）**：透過 Telegram 內建按鈕（Inline Keyboards）直接進行工具執行的授權審批（Approve / Deny）。

---

## 2. 可行性評估 (Feasibility Analysis)

### 2.1 技術架構優勢
- **非同步事件核心（Asyncio-Native）**：`cyc` 內部核心（`AgentLoop`, `BaseProvider`, `SessionManager`）皆基於 Python `asyncio` 實作。Telegram 的主流非同步庫（如 `aiogram` 或 `python-telegram-bot[async]`）能與 `cyc` 核心無縫協同運行於同一 Event Loop。
- **解耦的 Session 與 AgentLoop 設計**：`cyc` 的 `CliApp` 將終端 I/O 與業務邏輯（`AgentLoop`）清晰隔離，只要為通訊軟體實作專屬的 `GatewayAdapter` / `BotHandler`，即可重複調用現有的 9 核心工具、多模型 Provider、Skills 與記憶體機制。
- **豐富的富文本與交互元件**：Telegram 官方原生支援 MarkdownV2、HTML 標籤、程式碼區塊高亮、Inline Keyboard 互動按鈕與 Document 檔案傳送，非常適合呈現 Agent 的 Thought Process、Unified Diff 與輸出日誌。

### 2.2 核心風險與防護策略

| 風險面向 | 潛在問題 | 防範措施與應對方案 |
| :--- | :--- | :--- |
| **遠端命令安全性** | 惡意第三方若發現 Bot，可能透過自然語言讓 Agent 執行任意系統 Shell (`rm -rf`) | **嚴格白名單與身分綁定**：僅允許設定檔中指定之 `allowed_user_ids` 存取，其餘訊息直接忽略；強制支援二次確認金鑰（PIN / 2FA）。 |
| **訊息長度限制** | Telegram 單則文字上限為 4,096 字元，程式碼或日誌容易被截斷報錯 | **智慧分段與檔案附件**：若輸出超過 3,500 字元，自動切分為多則訊息；若為大型 Diff 或 Log，自動包裝為 `.txt` / `.patch` 檔案以 Attachment 發送。 |
| **串流傳輸率（Rate Limit）** | Telegram Bot API 對每秒編輯訊息次數有嚴格限制（約 1 次/秒），即時串流易遭 429 封鎖 | **緩衝節流（Debounced Chunking）**：採動態緩衝區，每隔 1.0 ~ 1.5 秒更新一次訊息 Bubble，任務完成時發送最終完整渲染版本。 |
| **目錄與會話隔離** | 多使用者或多會話同時交談時可能產生 Context 污染 | **Chat ID 隔離**：將 Telegram 的 `chat_id` / `user_id` 映射至獨立的 `SessionManager`，會話完全獨立。 |

---

## 3. 系統架構設計 (System Architecture)

```mermaid
flowchart TD
    subgraph Client [使用者客戶端]
        TG_Mobile[Telegram App / 手機]
        TG_Desktop[Telegram Desktop]
    end

    subgraph Telegram_Cloud [Telegram 雲端]
        TG_API[Telegram Bot API\n(Long Polling / Webhook)]
    end

    subgraph Cyc_Host [cyc 宿主運行端]
        subgraph Gateway [通訊閘道層]
            BotRouter[Telegram Bot Service\n(aiogram 3.x)]
            AuthMiddleware[身分驗證與白名單中介軟體]
            ThrottleStream[節流串流輸出器]
        end

        subgraph Core [cyc 核心層]
            SessionMgr[SessionManager\n(依 Chat ID 隔離持久化)]
            AgentLoop[AgentLoop (ReAct Engine)]
            ToolRegistry[ToolRegistry (9 Core Tools + MCP)]
        end

        subgraph Providers [LLM 提供者]
            LocalLLM[Ollama / OMLX / agy]
            CloudLLM[Gemini / OpenRouter / NVIDIA]
        end
    end

    Client <-->|HTTPS| TG_API
    TG_API <-->|Long Polling| BotRouter
    BotRouter --> AuthMiddleware
    AuthMiddleware -->|已授權指令| SessionMgr
    SessionMgr <--> AgentLoop
    AgentLoop <--> ToolRegistry
    AgentLoop <--> Providers
    AgentLoop -->|即時進度| ThrottleStream
    ThrottleStream -->|編輯/推送訊息| TG_API
```

---

## 4. 關鍵互動功能設計 (Bot Interactions)

### 4.1 指令集映射 (Commands)
- `/start`：歡迎訊息、驗證狀態檢視、綁定當前 Working Directory。
- `/mode <chat|agent>`：動態切換對話或自動代理模式。
- `/model <name>`：線上切換模型（可透過 Inline Keyboard 彈出選單點選）。
- `/status`：查看當前系統負載、Context Token 佔比與工作區 Git 狀態。
- `/undo`：撤銷上一輪變更並還原代碼。
- `/stop`：緊急中斷當前正在執行的 Agent Loop（發送 Cancel 訊號並消毒狀態）。
- `!<command>`：執行受限本機指令（需在白名單模式下開啟）。

### 4.2 人機協同審批（HITL Inline Keyboard）
當 Agent 欲呼叫具副作用工具（例如 `write_file`, `replace_file_content`, `run_command`）且未開啟 `auto_approve` 時：
1. Bot 傳送即時卡片包含工具名稱、參數摘要與 Unified Diff。
2. 附帶兩個按鈕：`[ ✅ 批准 (Approve) ]` 與 `[ ❌ 拒絕 (Deny) ]`。
3. 點擊按鈕後，回呼 `CallbackQuery` 解除 `asyncio.Event` 等待，代理繼續運作。

---

## 5. 設定檔擴充規格 (`config.yaml`)

```yaml
# ~/.config/cyc/config.yaml 新增通訊軟體閘道區塊
bot:
  enabled: false
  platform: "telegram"               # telegram | discord | slack
  telegram:
    token: "${TELEGRAM_BOT_TOKEN}"    # 從 @BotFather 取得之 Token
    allowed_user_ids:                # 允許控制的使用者 Telegram ID 白名單
      - 123456789
    workspace_path: "~/Projects"      # 預設工作目錄（可透過 /cd 變更）
    streaming_throttle_seconds: 1.2  # 訊息更新節流間隔 (避免 429)
    auto_approve: false              # 是否免確認自動放行變更工具
```

---

## 6. 實作計劃與里程碑 (Implementation Milestones)

| 階段 | 週期預估 | 核心交付成果 | 驗收標準 |
| :--- | :---: | :--- | :--- |
| **Phase 1: 基礎 Bot 服務與身分驗證** | 2 天 | 1. 導入 `aiogram 3.x` 基礎架構<br>2. 實作 `TelegramBotService` 輪詢服務<br>3. 身分白名單驗證中介軟體 | 非白名單用戶直接被阻絕；白名單用戶發送純文字訊息能串接 `BaseProvider` 回覆。 |
| **Phase 2: 串流更新與 Markdown 適配** | 2 天 | 1. 實作 `TelegramStreamRenderer` 節流器<br>2. MarkdownV2 標籤自動跳脫與修復<br>3. 超長訊息自動分割與檔案轉換 | LLM 生成過程每 1.2 秒流暢更新，不觸發 Telegram 429，程式碼區塊排版完整。 |
| **Phase 3: Agent 迴圈與審批按鈕** | 3 天 | 1. 整合 `AgentLoop` 工具調度<br>2. 實作 Inline Keyboard 審批卡片<br>3. 支援 `/stop` 取消與狀態消毒 | 工具呼叫卡片清晰，能在手機上直接點擊按鈕確認寫檔與指令執行。 |
| **Phase 4: 多平台抽象與打包發布** | 2 天 | 1. 抽象化 `BaseChatGateway` 介面<br>2. 新增 CLI 啟動指令：`cyc bot start`<br>3. 提供 `systemd` / `launchd` 背景服務範本 | 可作為本機常駐服務（Daemon）後台持續運行，穩定提供行動端存取。 |
