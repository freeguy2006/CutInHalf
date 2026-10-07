#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
建置腳本:下載 Fluent Emoji 3D 圖片(快取於 src/img/),
把圖片轉成 base64 data URI 嵌入 src/template.html,輸出單一檔案 ../index.html。

用法:  python src/build.py
"""
import base64
import json
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(HERE, "img")
TEMPLATE = os.path.join(HERE, "template.html")
OUTPUT = os.path.join(os.path.dirname(HERE), "index.html")

BASE = "https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets"

# (中文名稱, Fluent Emoji 資料夾名稱) — 依規格書順序
ITEMS = [
    ("披薩", "Pizza"), ("生日蛋糕", "Birthday cake"), ("西瓜", "Watermelon"),
    ("吐司", "Bread"), ("甜甜圈", "Doughnut"), ("香蕉", "Banana"),
    ("起司", "Cheese wedge"), ("漢堡", "Hamburger"), ("可頌", "Croissant"),
    ("雞腿", "Poultry leg"), ("熱狗", "Hot dog"), ("紅蘋果", "Red apple"),
    ("酪梨", "Avocado"), ("鳳梨", "Pineapple"), ("草莓", "Strawberry"),
    ("紅蘿蔔", "Carrot"), ("茄子", "Eggplant"), ("壽司", "Sushi"),
    ("塔可", "Taco"), ("餅乾", "Cookie"), ("西洋梨", "Pear"),
    ("檸檬", "Lemon"), ("法國麵包", "Baguette bread"), ("椒鹽卷餅", "Pretzel"),
    ("飯糰", "Rice ball"), ("三明治", "Sandwich"), ("花椰菜", "Broccoli"),
    ("月餅", "Moon cake"), ("寶石", "Gem stone"), ("泰迪熊", "Teddy bear"),
]


def slug(folder):
    return folder.lower().replace(" ", "_")


def fetch(folder):
    s = slug(folder)
    path = os.path.join(IMG_DIR, s + ".png")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    url = "%s/%s/3D/%s_3d.png" % (BASE, urllib.parse.quote(folder), s)
    print("下載", url)
    req = urllib.request.Request(url, headers={"User-Agent": "cut-in-half-build"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    with open(path, "wb") as f:
        f.write(data)
    return path


def main():
    os.makedirs(IMG_DIR, exist_ok=True)
    items = []
    total = 0
    for name, folder in ITEMS:
        path = fetch(folder)
        with open(path, "rb") as f:
            raw = f.read()
        total += len(raw)
        b64 = base64.b64encode(raw).decode("ascii")
        items.append({"name": name, "src": "data:image/png;base64," + b64})

    with open(TEMPLATE, "r", encoding="utf-8") as f:
        tpl = f.read()
    marker = "/*__ITEMS__*/[]"
    if marker not in tpl:
        sys.exit("template.html 找不到 " + marker)
    out = tpl.replace(marker, json.dumps(items, ensure_ascii=False, separators=(",", ":")))
    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    print("PNG 合計 %.1f KB;index.html = %.1f KB" % (total / 1024, os.path.getsize(OUTPUT) / 1024))


if __name__ == "__main__":
    main()
