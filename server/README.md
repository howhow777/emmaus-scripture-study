# Hermes 經文語意搜尋服務

公開端點：`https://emmaus-search.promelink.link/search`（POST，JSON `{ "query": "想摸傷口才肯相信復活" }`）。健康檢查：`/health`。

## 本機部署

- 專用 Hermes profile：`~/.hermes/profiles/emmaus-search`，由官方 `hermes profile create emmaus-search --no-skills --no-alias` 建立，沒有複製主 profile 的對話、記憶或憑證。沿用 Hermes 共用 Codex 登入；模型為 `gpt-6.1-sol` / `openai-codex`，fallback 清單為空。
- profile 的 `platform_toolsets.api_server`、`cli` 設為 `[no_mcp]`，所有工具停用；內建記憶與 user profile 停用。專用隨機 `API_SERVER_KEY` 只存在該 profile 的 `.env`，檔案權限 600，不可提交 Git。
- 公開服務只接受搜尋文字，沒有聊天、sessions、任意模型、tools 或代理路由。原有 Hermes API 不直接對網站公開。每次模型請求使用新的 session id，不承接其他查詢的對話。
- 執行目錄：`~/.hermes/projects/emmaus-search`。程式以 Python 標準函式庫執行，沒有額外套件依賴。只綁定 `127.0.0.1:18891`。
- 獨立具名 Cloudflare tunnel `emmaus-scripture-search`，不修改現有隧道。LaunchAgents：`com.promelink.emmaus-search` 與 `com.promelink.emmaus-tunnel`。
- 原有 Gateway、CRM、LINE、n8n 服務沒有重啟或改路由。

更新模型索引與服務程式（於 Git 倉庫根目錄）：

```sh
python3 server/search_service.py --runtime "$HOME/.hermes/projects/emmaus-search/runtime" --build .
cp server/search_service.py "$HOME/.hermes/projects/emmaus-search/search_service.py"
launchctl kickstart -k "gui/$(id -u)/com.promelink.emmaus-search"
```

若索引內容改變，將產生的 corpus 值同步至網站 `semantic-config.js`。更新網站需重新建置 `npm run build:graph`。金鑰、隧道 credentials、模型快取、查詢資料庫、Hermes sessions 皆不部署到 GitHub Pages 或下載包。

## 檢索與限制

模型讀取本站完整引用經文與研究文字，以語意選取索引代碼，不生成經文或新解經結論。伺服器只接受索引內的代碼；前端把語意結果與文字結果合併，再套用現有研究篩選。圖中的實線仍只沿用原有引用。

允許網站 Origin `https://howhow777.github.io`。CORS 不是使用者身分驗證，因此另外設每 IP 每分鐘 20 次、同時最多 2 次模型請求、每日全站最多 100 次未快取模型呼叫（UTC 計日，持久化計數）。相同查詢的結果快取七天；到達模型額度後仍可取既有快取。額度包含失敗的模型嘗試，以限制反覆失敗對帳號的影響。這些查詢會共用站主的 Codex 訂閱額度。

查詢快取鍵為雜湊，公開服務不寫入原始查詢或 IP 存取日誌；Hermes 專用 profile 仍會依自身設定儲存搜尋 session / agent 日誌，勿將其對外發布。本機休眠、斷線、Gateway 停止或訂閱用量不足時，前端顯示訊息並保留文字搜尋。

單元測試（不呼叫模型）：

```sh
python3 -m unittest discover -s server -p 'test_*.py'
```

## 覆蓋查核預覽與模型驗收

`server/preview.py` 在獨立 loopback 連接埠提供審核站及相同受限搜尋路由，以明確指定的預覽 Origin 驗證請求。它只服務公開網站檔案、data／reports 的 JSON／Markdown，拒絕程式、資料庫、私密設定與目錄穿越。正式服務仍使用原固定 Origin。

macOS LaunchAgent 應從審核專用執行目錄讀取網站副本，避免 Documents 的隱私權限制；不要為此調整整台電腦的隱私權。預覽索引、程式與靜態副本均與正式版分開。使用新版程式的服務若共用計數資料庫，`BEGIN IMMEDIATE` 保證跨程序的每日預算原子遞增；正式程式仍須在發布時一併更新。

`verify-semantic-live.py` 的 `use_cache=False` 僅為內部呼叫參數；公開 API 仍只接受 `query`，不接受模型、額度、快取繞過、messages或tools。評估結果須記錄corpus，新增經文後應重測，不能挪用前一版本的通過成績。額外驗證不得默默提高公開每日限制。

內部驗證可用 `--call-limit 48` 搭配獨立私有 runtime 將本次測試硬性限制於48次；這個CLI選項不由公開API接受，也不提高公開服務每日100次的限制。
