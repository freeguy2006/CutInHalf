# 切一半 Cut In Half

只能切**一刀**，把東西切成指定的面積比例——考驗你的「目測面積」直覺！

**線上遊玩：<https://freeguy2006.github.io/CutInHalf/>**

## 遊戲說明

畫面上會出現一個去背的物品（披薩、大象、吉他、火箭……）和一個目標比例（例如 `30 : 70`）。
按住滑鼠（或手指）拖曳出一條線，放開就切下去。兩塊的面積越接近目標比例，分數越高。

## 玩法

1. 按「開始」，一場遊戲共 **5 回合**，每回合滿分 1000 分（總分 5000）。
2. 每回合從 **673 種物品**（食物飲料、動植物、日常物品、交通與地點、活動）中隨機抽一個（同一場不重複），再隨機抽一個目標比例：
   `50:50`、`40:60`、`1:2`、`30:70`、`1:3`、`20:80`。
3. 在砧板上**按住拖曳、放開即切**。你畫的線會被視為「無限延伸的直線」（整把刀劃過去），方向不限。
   - 拖曳中只有刀光，不會顯示即時百分比。
   - 拖曳距離不到 30px 視為誤觸，不算一刀。
   - 如果刀沒有碰到物品（其中一側是 0%），顯示「沒切到！」，可以重切，不扣分。
4. 切開後物品會裂成兩塊滑開，並標示實際百分比，接著顯示本回合分數與評語。
5. 5 回合結束後，結算畫面依總分給你一個稱號——「你是哪一種秤？」（共 11 級，從「用手掂一掂」到「國際公斤原器」）。

最高分會存在瀏覽器的 `localStorage`，右上角的喇叭按鈕可以靜音（狀態也會記住）。

## 計分

- 誤差 `e` = |實際較小那塊的 % − 目標較小那塊的 %|（不分左右）
- 單回合分數 = `round(1000 × (1 − e/20)^1.5)`，`e ≥ 20` 時為 0 分

| 誤差 | 0% | 1% | 2% | 5% | 10% | 20%+ |
|---|---|---|---|---|---|---|
| 分數 | 1000 | 926 | 854 | 650 | 354 | 0 |

面積用像素計算：圖片載入後先畫到看不見的 canvas 讀出所有像素，alpha > 128 視為物品的一部分，再用外積判斷每個像素落在刀線的哪一側，兩側像素數 ÷ 總像素數就是實際百分比。因此任何形狀都準確（包含甜甜圈中間的洞）。

完整規則（評語門檻、11 級稱號與說明、流程、視覺風格、物品圖庫與篩選規則）請見 [規格書.md](./規格書.md)。

## 在本機遊玩

圖片是「用到才載入」的獨立檔案（`img/`），遊戲要讀取它們的像素來算面積。瀏覽器基於安全限制，**直接雙擊 `index.html`（`file://`）時不允許讀取圖片像素**，遊戲會顯示提示。請用任何本機靜態伺服器開啟，例如：

```bash
python -m http.server 8000
# 然後用瀏覽器開 http://localhost:8000/
```

部署到 GitHub Pages 時圖片與網頁同網域，不需要任何設定。

## 技術

- `index.html` 是唯一的程式檔（HTML、CSS、JavaScript），原生 JavaScript，不使用框架、不依賴任何外部資源（無 CDN、無網路字型）。
- 物品圖片放在 `img/`（WebP，RGB 有損、透明通道無損，所以面積計算與原 PNG 完全一致）。`index.html` 只內嵌一份物品清單（名稱、檔名），首頁**不會**下載任何物品圖片：開始遊戲才載入第 1 回合的圖，玩第 N 回合時在背景預先載入第 N+1 回合的圖，載入失敗會自動換一個物品。
- Canvas 2D、Pointer Events（滑鼠＋觸控）、Web Audio API 即時合成音效（無外部音檔）。
- 部署：GitHub Pages（`main` 分支根目錄）。

### 專案結構

```
index.html            遊戲本體（由 src/build.py 產生，請直接部署這個檔案）
img/                  673 張物品圖（WebP，約 3.9 MB，用到才載入）
規格書.md             遊戲規格
src/template.html     index.html 的可編輯樣板
src/build.py          組裝 index.html（不需網路與第三方套件）
src/select_items.py   從 Fluent Emoji 篩選物品、取得中文名稱、轉成 img/*.webp（需網路、Pillow、numpy）
src/items.json        物品清單（名稱、檔名、分類、英文原名；由 select_items.py 產生）
src/decor/            開始畫面的裝飾小圖（內嵌進 index.html）
src/cache/            下載的原始 PNG / metadata / CLDR 快取（已加入 .gitignore，不上傳）
LICENSE-ASSETS        圖片素材與名稱資料的授權聲明
```

### 重新建置

只改了程式碼（`src/template.html`）時：

```bash
python src/build.py
```

要重新篩選物品、重新產生圖片時（需要網路；會下載約 850 張原始 PNG 到 `src/cache/`）：

```bash
pip install pillow numpy
python src/select_items.py     # 產生 img/*.webp、src/items.json、src/decor/*.webp
python src/build.py            # 再組出 index.html
```

篩選規則（見規格書第七節）：只收食物飲料、動植物、日常物品、交通與地點、活動；排除不透明像素佔外框超過 90% 的「整塊方形」圖、不透明面積太小的細棍狀圖、時鐘與月相等近似系列（只留代表）、不適合「切」的內容（武器、死亡、藥物、菸、宗教場所等）。

## 素材來源與授權

- 圖片：Microsoft [Fluent Emoji](https://github.com/microsoft/fluentui-emoji) 3D 版，Fluent Emoji © Microsoft，以 [MIT License](https://github.com/microsoft/fluentui-emoji/blob/main/LICENSE) 授權。
- 物品中文名稱：[Unicode CLDR](https://cldr.unicode.org/) 繁體中文 emoji 名稱（Unicode License v3）；v1 原有的 30 個物品沿用原本的名字。
- 詳見 [LICENSE-ASSETS](./LICENSE-ASSETS)。

本專案為政大「生成式 AI：文字與圖像生成的原理與實務」課程作業（Vibe Coding 互動網頁）。
