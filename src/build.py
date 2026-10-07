#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
建置腳本(不需網路、不需第三方套件):
把 src/template.html 與 src/items.json(物品清單)組合成單一 ../index.html。

  - 物品清單只內嵌「名稱 + 檔名」,圖片放在 ../img/,遊戲中用到才載入。
  - 開始畫面的裝飾小圖(src/decor/*.webp)與示範動畫的披薩(img/pizza.webp)以 data URI 內嵌,
    讓首頁不需要任何額外請求。

用法:  python src/build.py
(物品清單與 img/ 由 `python src/select_items.py` 產生,通常不需要重跑。)
"""
import base64
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TEMPLATE = os.path.join(HERE, "template.html")
MANIFEST = os.path.join(HERE, "items.json")
DECOR_DIR = os.path.join(HERE, "decor")
IMG_DIR = os.path.join(ROOT, "img")
OUTPUT = os.path.join(ROOT, "index.html")


def data_uri(path):
    with open(path, "rb") as f:
        return "data:image/webp;base64," + base64.b64encode(f.read()).decode("ascii")


def main():
    with open(MANIFEST, "r", encoding="utf-8") as f:
        items = json.load(f)
    # 只把遊戲需要的欄位(n=名稱, f=檔名)放進 index.html
    slim = [{"n": it["n"], "f": it["f"]} for it in items]
    for it in slim:
        if not os.path.exists(os.path.join(IMG_DIR, it["f"] + ".webp")):
            sys.exit("缺少圖片: img/%s.webp(請先執行 python src/select_items.py)" % it["f"])

    decor = [data_uri(os.path.join(DECOR_DIR, n)) for n in sorted(os.listdir(DECOR_DIR)) if n.endswith(".webp")]
    demo = data_uri(os.path.join(IMG_DIR, "pizza.webp"))

    with open(TEMPLATE, "r", encoding="utf-8") as f:
        tpl = f.read()
    for marker in ("/*__ITEMS__*/[]", "/*__DECOR__*/[]", "/*__DEMO__*/"):
        if marker not in tpl:
            sys.exit("template.html 找不到 " + marker)
    out = tpl.replace("/*__ITEMS__*/[]", json.dumps(slim, ensure_ascii=False, separators=(",", ":")))
    out = out.replace("/*__DECOR__*/[]", json.dumps(decor, separators=(",", ":")))
    out = out.replace("/*__DEMO__*/", demo)
    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    img_total = sum(os.path.getsize(os.path.join(IMG_DIR, n)) for n in os.listdir(IMG_DIR))
    print("物品 %d 個;img/ 共 %.2f MB;index.html = %.1f KB(其中內嵌裝飾圖 %d 張)" % (
        len(slim), img_total / 1048576.0, os.path.getsize(OUTPUT) / 1024.0, len(decor)))


if __name__ == "__main__":
    main()
