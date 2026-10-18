# 以馬忤斯之路：經文研究與互動圖譜

這是可直接部署到 GitHub Pages 的靜態網站。`index.html` 是研究閱讀頁，`graph.html` 是互動經文圖譜，`dating.html` 提供每處引用段落的年代說明與來源，`coverage.html` 記錄範圍內的補充經文及 27 卷新約查核。頁面使用相對連結，因此放在同一目錄即可互通，也能從下載的網站包離線閱讀；Bible.com 與學術來源連結仍需要網路。

閱讀頁與圖譜詳情中的 Bible.com 經文連結可用滑鼠懸浮預覽；手機長按連結約半秒可預覽，輕點仍開啟原連結。鍵盤選取連結可預覽，按向下鍵進入預覽、Escape 關閉。預覽至多顯示前四節，文字取自維基文庫的和合本 1919 用字版（神版）；外連是 Bible.com 的新標點和合本（神版），文字與標點可能不同。

圖譜關鍵字會搜尋研究說明與站內每處引用經文的完整段落，並在結果清單顯示命中的經節；搜尋文字使用上述維基文庫和合本。初次載入顯示主線 49 組，輸入關鍵字時自動切換為全部 206 組，也可手動只查主線。未列為研究條目引用的站內經文會單獨列出並直達原經文，不在圖上畫新的關係線。網站只索引已引用的段落，不是全本聖經搜尋。

關鍵字實際命中的節點會以橘色放大，並輕微呼吸；「減少動態效果」開啟時保留靜態高亮。被其他篩選隱藏的研究會顯示提示，可一鍵恢復全部搜尋結果。

輸入一句話後，按「用 AI 找相關經文」或 Enter 可加入語意搜尋，模型建議以粉紅色放大標示，與文字命中分開。語意搜尋由站主本機 Hermes 的獨立 `emmaus-search` profile 使用 Codex 訂閱模型執行；模型對照本站 901 處引用段落及 206 組研究文字選取，伺服器再驗證回傳代碼。語意建議可能不準確，請核對原文；不增加圖譜關係或研究結論。查詢會傳至 Hermes 與雲端模型。主機休眠、離線或模型額度不足時，語意搜尋可能無法使用，文字搜尋仍在瀏覽器本機執行。服務設定見 `server/README.md`。

圖譜的實線僅代表研究條目列出的經文。虛線代表共同研究主題，不表示經文本身彼此直接引用或應驗。耶穌親口經節的逐節標註與原研究的「耶穌親引／比較」標記分開；判準見 [`data/jesus-speech-notes.md`](data/jesus-speech-notes.md)。

## 維護

以下指令適用於 GitHub 原始碼倉庫；下載的網站包只含發布檔案。維護需要 Python 3 與 Node.js。經文年代的單一資料來源是 `data/passage-dates.json`；更新研究頁、年代或耶穌發言標註後，在專案目錄執行：

```sh
npm ci
npm run build:data
npm run build:coverage
npm run build:previews
npm run build:graph
npm test
npm run check:graph
```

首次重建時，先執行 `python3 scripts/build-scripture-previews.py --fetch`，再執行 `python3 scripts/build-coverage.py --fetch`，下載並以 SHA-256 驗證引用書卷及完整 27 卷新約的固定修訂來源。快取預設在倉庫外的 `../scripture-source/wikisource-1919/`；之後可離線重建。原始來源快取不需部署。

公開網站包含 `index.html`、`graph.html`、`dating.html`、`coverage.html`、`graph.css`、`graph-data.js`、`graph.bundle.js`、`scripture-preview.css`、`scripture-preview.js`、`scripture-previews-data.js`、`scripture-search-data.js`、`semantic-config.js`，並附 `THIRD_PARTY_NOTICES.txt`。`graph.bundle.js` 已包含 D3 依賴，公開頁面不讀取 CDN。

發布前，請在 iPhone Safari 與 Android Chrome 各測試捏合、拖移、篩選、條目跳轉和經文連結。圖譜頁下方的「手機手勢流暢度紀錄」提供近似影格間隔，供實機檢查。

## 搜尋覆蓋與修訂驗證

原有 186 組、49 組主線與既有 ID 保留；此次增列 E187–E206 共 20 組，另在 29 組既有研究補入 57 處平行／相關引用。148 處補充引用提供範圍內的語境，不自動新增圖譜實線。詳見 [查核報告](reports/search-audit-report.md)。

- `data/research-baseline.json`：修改前的內容快照；測試逐欄核對保留情況。
- `data/research-additions.json`：本輪新條目、附加引用及解釋界線的審核帳本。
- `data/audit-source-pins.json`：27 卷新約的固定修訂、原文雜湊。
- `data/coverage-manifest.json`：1,220 個獨立候選的納入、補充或範圍排除理由；候選來自語詞與譯本來源的舊約交叉註。不是全本經文搜尋或所有互文的無遺漏保證。
- `data/coverage/search-golden.json`：40 個正例、20 個反例，以及 24 個語意案例。舊拼字與常見經文書名別稱只用於搜尋正規化；顯示的經文不改寫。

`npm test` 不呼叫模型。真實模型驗證須另外執行下列指令，會使用訂閱額度；每日保護限制包含失敗嘗試，碰到限制須停止並回報，不能改用假結果。

```sh
python3 server/search_service.py --runtime /path/to/private-review-runtime --build .
python3 scripts/verify-semantic-live.py --runtime /path/to/private-review-runtime --rounds 2 --call-limit 48 --output reports/semantic-live.json
```

驗證執行器強制略過快取，記錄每次原始回應及 corpus。可用 `--resume` 接續同一 corpus，不能接續到不同資料版本。服務部署與前端 `semantic-config.js` 的 corpus 必須一致；預覽採獨立執行目錄，正式環境須待手機驗收後才更新。

瀏覽器回歸另可執行 `python3 scripts/verify-browser.py --site https://emmaus-preview.promelink.link`，需要已安裝的 Playwright 與 Chrome；不呼叫模型，網路錯誤案例採注入並明確與真實模型成績分開。

最終索引的48次真實模型驗收已達標（recall@10 100%、precision 99.17%）；Android與iPhone均由使用者回報測試通過。原始成績見 [reports/semantic-live.json](reports/semantic-live.json)。

正式網址：[研究首頁](https://howhow777.github.io/emmaus-scripture-study/) · [互動圖譜](https://howhow777.github.io/emmaus-scripture-study/graph.html)。發布驗證可執行 `python3 scripts/verify-production.py`；會向公開API送出一次正常查詢，遵守既有快取與每日保護限制。

[下載完整網站包](https://howhow777.github.io/emmaus-scripture-study/emmaus_website.zip)（可離線閱讀與文字搜尋；AI及外部經文連結需要網路）。
