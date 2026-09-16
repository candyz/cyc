# clichat

現代化終端 CLI 對話工具，支援本地端模型（Ollama、OMLX）與雲端模型（OpenRouter、NVIDIA NIM、Google Gemini）。

## 功能特性

- **多後端無縫切換**：支援本地 Ollama、OMLX (Apple Silicon MLX)、Google Antigravity (`agy`，直接使用 Gemini AI Pro 訂閱額度) 及各大雲端 API (Gemini, OpenRouter, NVIDIA NIM)。
- **即時 Markdown 串流渲染**：結合 `rich.live.Live`，文字隨生成即時渲染 Markdown 格式、程式碼區塊高亮與排版。
- **互動式 REPL 與智慧補全**：
  - 輸入歷史自動跨終端持久化保存 (`~/.local/share/clichat/history`)。
  - Tab 智慧自動補全 Slash 指令、動態拉取之模型名稱 (`/model `)、提供者名稱 (`/provider `) 及本地檔案路徑 (`/save `, `/load `)。
  - 支援單行與多行編輯模式切換 (`/multiline`)、`Alt+Enter` 隨時插入換行。
  - `Ctrl+C` 訊號優雅中斷當前生成，不崩潰、不中斷對話。
- **會話與 Token 管理**：
  - Context Token 自動估算與超長自動滑動窗口裁切（保障 System Prompt 永遠留存）。
  - 會話支援匯出為 Markdown 或完整結構化 JSON，並可隨時載入續聊。
- **Pipeline 管線模式**：支援 Unix 管道輸入，例如 `cat error.log | clichat "分析此日誌"`。
- **彈性配置**：支援 `~/.config/clichat/config.yaml` 並自動解析環境變數 `${API_KEY}`。

## 安裝與執行

### 快速開始

```bash
# 1. 初始化預設設定檔 (~/.config/clichat/config.yaml)
uv run clichat init

# 2. 啟動互動式聊天 (預設使用本地 Ollama)
uv run clichat

# 3. 指定 Provider 與 Model
uv run clichat -p agy -m "gemini-3.1-pro-high"     # 使用本地 agy，直連 Gemini Pro 訂閱額度
uv run clichat -p gemini -m "gemini-2.5-flash"      # 使用 Google AI Studio API Key
uv run clichat -p ollama -m "llama3.3:latest"

# 4. 單次問答 / Pipeline 模式
uv run clichat "什麼是量子計算？"
cat main.py | uv run clichat "請幫我 code review 這段程式碼"
```

### 全域 CLI 安裝

您可以將 `clichat` 安裝為系統全域命令，在任何終端機目錄下直接呼叫：

```bash
# 方法 A: 透過 uv tool 全域安裝 (推薦)
uv tool install .

# 方法 B: 透過 pipx 全域安裝
pipx install .

# 安裝完成後直接呼叫
clichat
```


## Slash Commands (在 REPL 模式下)

| 指令 | 說明 |
| :--- | :--- |
| `/help` | 顯示所有指令說明 |
| `/models` | 表格化列出當前 Provider 所有可用模型清單 |
| `/model <name>` | 動態切換模型（支援 Tab 自動補全） |
| `/provider <name>` | 動態切換提供者（支援 Tab 自動補全） |
| `/system [prompt]` | 設定或檢視當前 System Prompt |
| `/tokens` | 表格化顯示目前對話的 Token 估算量、上限與利用率 |
| `/multiline` | 切換多行 / 單行輸入模式 |
| `/save <filepath>` | 儲存會話（`.md` 儲存為 Markdown，`.json` 儲存為結構化會話） |
| `/load <filepath>` | 載入過往的 JSON 會話檔案並接續對話 |
| `/clear` | 清空當前對話歷史 |
| `/exit` 或 `/quit` | 退出對話 |

## 規格書與規劃

請參閱 [docs/CLI_CHAT_SPEC_AND_PLAN.md](docs/CLI_CHAT_SPEC_AND_PLAN.md)。
