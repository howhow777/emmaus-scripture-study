# 以馬忤斯之路：經文研究與互動圖譜

這是可直接部署到 GitHub Pages 的靜態網站。`index.html` 是研究閱讀頁，`graph.html` 是互動經文圖譜，`dating.html` 提供每處引用段落的年代說明與來源。頁面使用相對連結，因此放在同一目錄即可互通，也能從下載的網站包離線閱讀；Bible.com 與學術來源連結仍需要網路。

圖譜的實線僅代表研究條目列出的經文。虛線代表共同研究主題，不表示經文本身彼此直接引用或應驗。耶穌親口經節的逐節標註與原研究的「耶穌親引／比較」標記分開；判準見 [`data/jesus-speech-notes.md`](data/jesus-speech-notes.md)。

## 維護

需要 Python 3 與 Node.js。經文年代的單一資料來源是 `data/passage-dates.json`；更新研究頁、年代或耶穌發言標註後，在專案目錄執行：

```sh
npm ci
npm run build:data
npm run build:graph
npm test
npm run check:graph
```

公開網站包含 `index.html`、`graph.html`、`dating.html`、`graph.css`、`graph-data.js`、`graph.bundle.js`，並附 `THIRD_PARTY_NOTICES.txt`。`graph.bundle.js` 已包含 D3 依賴，公開頁面不讀取 CDN。

發布前，請在 iPhone Safari 與 Android Chrome 各測試捏合、拖移、篩選、條目跳轉和經文連結。圖譜頁下方的「手機手勢流暢度紀錄」提供近似影格間隔，供實機檢查。
