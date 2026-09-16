# Coding Agent 演進規格書與實作計劃

## 1. 可行性評估 (Feasibility Analysis)

將現有以對話為主的 `clichat` 工具演進為全功能 **Coding Agent**（自動化代碼編寫、終端指令執行、專案分析修復），**技術可行性極高且具有清晰的演進路徑**。

### 1.1 現有架構延伸性分析

`clichat` 在前期階段已具備優良的模組化基底，為 Coding Agent 的開發打下了堅實基礎：
- **Provider 抽象層 (`BaseProvider`)**：已封裝非同步串流呼叫，擴充 `tools` / `function_call` 參數時不需顛覆現有 API。
- **會話管理層 (`SessionManager`)**：具備 Token 估算、滑動窗口裁剪、JSON/Markdown 持久化，可直接擴展支援 `tool_calls` 與 `tool` 角色訊息。
- **終端介面層 (`TerminalUI`)**：結合 `rich` 與 `prompt_toolkit`，已具備高亮、表格、即時渲染能力，可直接擴充 Tool 呼叫卡片與代碼 Diff 呈現。

### 1.2 目標後端 Tool Calling 能力與相容性分析

| 後端類型 | 模型範例 | Tool Calling 支援度 | 接入策略 |
| :--- | :--- | :--- | :--- |
| **OpenRouter** | Claude 3.5 Sonnet, GPT-4o, Llama 3.3 | **原生 100% 支援** | 遵循標準 OpenAI `tools` 與 `tool_choice` 協議，成熟度最高。 |
| **Google Gemini** | Gemini 2.5 Flash, Gemini 2.5 Pro | **原生 100% 支援** | 透過 `google-genai` SDK 原生支援 Python 函式聲明 (`types.Tool`) 與自動參數轉換。 |
| **NVIDIA NIM** | Meta Llama 3.3 70B, Qwen 2.5 Coder | **原生 100% 支援** | 遵循標準 OpenAI 格式傳入 `tools` 參數。 |
| **本地 Ollama** | Qwen 2.5 Coder (7B/14B/32B), Llama 3.3 | **原生支援** | 最新版 Ollama 在 `/v1/chat/completions` 原生支援 OpenAI 格式的工具調用。 |
| **本地 OMLX** | MLX-LM 伺服器 | **部分支援 / 需適配** | 部分版本支援 OpenAI function calling；若不支援可透過 System Prompt 結構化輸出（JSON ReAct 提示詞）作為後備方案。 |

> **結論**：現今主流的本地開源模型（如 Qwen 2.5 Coder）與雲端模型皆已原生具備出色的 Tool Calling 能力，後端門檻已完全掃除。

### 1.3 核心挑戰與應對策略

1. **安全與毀滅性操作防護 (Safety & Permissions)**：
   - *挑戰*：Agent 自行執行 `rm -rf` 或覆蓋重要代碼可能導致災難。
   - *策略*：導入 **Human-in-the-Loop (HITL) 權限審批機制**。唯讀工具（讀檔、搜尋、目錄瀏覽）預設自動放行；變更工具（寫檔、置換代碼、Shell 指令）必須由使用者確認 `[y/N]`，並提供 `-y/--yes` 參數供無人值守模式使用。
2. **Context Window 膨脹與 Token 控制**：
   - *挑戰*：讀取超大檔案或執行輸出巨量 log 會瞬間撐爆上下文。
   - *策略*：工具輸出限制截斷（如只回傳前 200 行或 30KB），引導模型使用行號範圍分頁讀取或使用 `grep_search`。
3. **終端可讀性與互動體驗 (UX)**：
   - *挑戰*：大量工具調用與回傳若直接印出終端會眼花撩亂。
   - *策略*：使用 `rich.panel.Panel` 與動態 Spinner 封裝工具呼叫過程，檔案修改前呈現彩色 Unified Diff。

---

## 2. 系統架構與設計規格 (System Architecture & Specification)

### 2.1 Agent 執行迴圈架構圖 (ReAct Loop)

```mermaid
flowchart TD
    User([使用者輸入任務]) --> Agent[Coding Agent 主迴圈]
    Agent --> LLM[LLM 思考 & 規劃\n(Tool Calling)]
    
    LLM -->|文字回覆| End[串流輸出給使用者]
    LLM -->|調用工具 Tool Call| PermCheck{安全權限檢查\nPermission Check}
    
    PermCheck -->|唯讀操作| Exec[工具執行器 Tool Executor]
    PermCheck -->|變更操作 / Shell| Confirm{使用者確認 [y/N]}
    
    Confirm -->|允許 (Yes)| Exec
    Confirm -->|拒絕 (No)| Reject[注入「使用者拒絕執行」Observation]
    
    Exec --> LocalSys[(本機檔案系統 / Shell)]
    LocalSys --> Observation[擷取執行結果 / 輸出]
    Reject --> Observation
    
    Observation --> Truncate[輸出長度截斷 & 格式化]
    Truncate --> Context[寫入 Session 歷史]
    Context --> Agent
```

### 2.2 核心工具集規範 (Built-in Tools)

Coding Agent 必須具備以下核心工具：

| 工具名稱 | 類型 | 描述 | 主要參數 |
| :--- | :--- | :--- | :--- |
| `read_file` | 唯讀 | 讀取檔案內容，支援指定行號區間 | `path`: 檔案路徑, `start_line`?: 起始行, `end_line`?: 結束行 |
| `write_file` | 變更 | 建立新檔案或覆寫現有檔案 | `path`: 檔案路徑, `content`: 寫入內容 |
| `replace_file_content` | 變更 | 精確置換檔案中的某段程式碼區塊 | `path`: 檔案路徑, `target`: 欲替換原文, `replacement`: 新內容 |
| `run_command` | 變更 | 在指定目錄執行 Shell 指令並擷取 stdout/stderr | `command`: 指令字串, `cwd`?: 工作目錄, `timeout`?: 逾時秒數 |
| `list_dir` | 唯讀 | 瀏覽目錄清單與檔案結構 | `path`: 目錄路徑, `recursive`?: 是否遞迴, `max_depth`?: 最大深度 |
| `grep_search` | 唯讀 | 在專案中搜尋字串或正則表達式 | `pattern`: 搜尋樣式, `path`?: 搜尋路徑, `include`?: 檔案副檔名過濾 |

### 2.3 工具抽象與多後端轉換層設計

為各後端提供統一的 Python 工具註冊定義，並自動轉譯成對應後端的格式：

```python
# src/clichat/agent/tools/base.py 示意
class Tool(ABC):
    name: str
    description: str
    parameters: dict  # JSON Schema 格式
    is_mutation: bool = False  # 是否會改更狀態 (需安全確認)

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """執行工具並回傳字串結果"""
        pass

    def to_openai_tool(self) -> dict:
        """轉為 OpenAI function calling 規格 (相容 Ollama, OpenRouter, NVIDIA)"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }

    def to_gemini_tool(self) -> types.Tool:
        """轉為 Google GenAI 規格"""
        ...
```

### 2.4 安全與權限控制規範 (Permission Management)

提供三種安全模式：
1. **Interactive Mode (預設)**：唯讀操作自動允許；變更操作 (`write_file`, `replace_file_content`, `run_command`) 提示確認，顯示將被修改的檔案路徑或執行的 Shell 指令。
2. **Auto Mode (`-y`, `--yes`)**：全自動執行，適合排程或具信賴的小型重構任務。
3. **Read-Only Mode (`--read-only`)**：禁止所有變更與 Shell 指令，僅允許進行代碼分析、架構審查與檔案搜尋。

### 2.5 終端 UI 呈現規格

1. **Tool Invocation 卡片**：
   ```
   ╭─ ⚙️  Tool Call: read_file ────────────────────────────╮
   │ path: src/clichat/config.py, start_line: 1, end_line: 30 │
   ╰───────────────────────────────────────────────────────╯
   ```
2. **變更確認提示 (帶 Diff 預覽)**：
   ```
   ╭─ ⚠️  Permission Request: replace_file_content ────────╮
   │ File: src/clichat/cli.py                               │
   │                                                        │
   │ - def parse_args():                                    │
   │ + def parse_args(sys_argv=None):                       │
   ╰────────────────────────────────────────────────────────╯
   Allow this change? [y/n/all] (y)
   ```

---

## 3. 分階段實作計劃 (Implementation Plan)

### Phase 1: 核心工具集與統一 Tool 抽象介面 (預估 2 天)
- [ ] 建立 `src/clichat/agent/tools/` 模組目錄。
- [ ] 實作 `Tool` 基礎抽象類別，包含 JSON Schema 生成與 OpenAI/Gemini 適配器。
- [ ] 實作 6 大核心內建工具：
  - `read_file` (支援行號切片與超長防護)
  - `write_file` (安全父目錄自動建立)
  - `replace_file_content` (精確單一區塊替換)
  - `run_command` (非同步執行、逾時控制與輸出截斷)
  - `list_dir` (格式化目錄樹)
  - `grep_search` (以 Python 原生或 ripgrep 進行正則搜尋)
- [ ] 撰寫單元測試覆蓋所有工具的執行與邊界情況。

### Phase 2: Agent ReAct 執行迴圈與多後端串接 (預估 3 天)
- [ ] 擴展 `BaseProvider` 支援 `tools` 參數與非串流/串流之 Tool Call 回傳解析。
- [ ] 更新 `OpenAICompatibleProvider`：解析 response 中的 `tool_calls`（對應 Ollama, OpenRouter, NVIDIA）。
- [ ] 更新 `GeminiProvider`：對接 `types.Tool` 與 function call 結構。
- [ ] 實作 `AgentLoop`：
  - 模型接收系統提示詞與可用工具清單。
  - 當模型回傳 `tool_calls` 時，派發執行工具並將 `tool` role 訊息加回對話。
  - 迴圈自動推進直至模型判定任務完成或達到最大反覆次數（防止死循環，預設上限 15 輪）。
- [ ] 支援 Slash 指令切換模式（例如 `/mode chat` 與 `/mode agent`）。

### Phase 3: 安全審批與 Human-in-the-Loop 機制 (預估 2 天)
- [ ] 實作 `PermissionManager`：
  - 分類工具安全等級（`READ_ONLY`, `MUTATION`, `EXECUTE`）。
  - 終端提示使用者確認 (`[y] Yes, [n] No, [a] Always allow for this session`)。
- [ ] 新增命令列安全參數：
  - `-y` / `--yes`：全自動核准所有工具。
  - `--read-only`：禁止所有寫檔與執行指令工具。
- [ ] 支援中斷機制：使用者可隨時按下 `Ctrl+C` 取消後續工具鏈執行。

### Phase 4: 終端 Diff 渲染與代碼庫上下文增強 (預估 2 天)
- [ ] 整合 Rich Diff：在檔案置換或寫入前，在終端渲染彩色統一修訂格式 (Unified Diff)。
- [ ] 專案感知系統提示詞 (System Prompt with Workspace Awareness)：
  - 自動偵測工作目錄路徑、Git 狀態 (`git branch`, `git status --short`)。
  - 自動載入專案規範檔案（如 `GEMINI.md`, `CLAUDE.md`, `.cursorrules`）。
- [ ] 實作專案索引精簡指令（如 `/context` 查看當前 Agent 感知之檔案空間）。

### Phase 5: MCP (Model Context Protocol) 擴充支援 (預估 2 天)
- [ ] 支援外部 MCP Server 接入（透過 stdio 串接）。
- [ ] 在 `~/.config/clichat/config.yaml` 中新增 `mcp_servers` 設定區塊。
- [ ] 動態將 MCP 工具註冊至 Agent 工具清單中。

---

## 4. 驗證與測試策略 (Verification & Testing)

1. **單元測試 (Unit Tests)**：
   - 工具執行安全性測試（防路徑遍歷 `../../etc/passwd`、逾時指令終止）。
   - Tool Schema 序列化測試（驗證符合 OpenAI 與 Gemini API 格式）。
2. **模擬迴圈測試 (Mock Agent Loop)**：
   - 使用 Mock Provider 模擬「提問 -> 呼叫 read_file -> 取得內容 -> 回覆解答」完整流程。
3. **真實場景端到端驗證 (End-to-End Tasks)**：
   - **任務 1 (唯讀分析)**：「幫我找出專案中所有使用 `ProviderConfig` 的地方並說明其用途」。
   - **任務 2 (修改修復)**：「在 `tests/` 下建立一個新測試並執行 `pytest` 驗證其通過」。
   - **任務 3 (除錯重構)**：「執行測試，如果失敗則閱讀錯誤訊息並自動修正程式碼」。
