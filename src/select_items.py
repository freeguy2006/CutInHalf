#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v2 物品圖庫選取腳本(建置時執行,需要網路與 Pillow、numpy):

  python src/select_items.py

做的事:
  1. 取得 Fluent Emoji 的檔案樹與每個資料夾的 metadata.json(群組、emoji 字元),
     以及 Unicode CLDR 繁體中文 emoji 名稱 —— 全部快取在 src/cache/(已加入 .gitignore)。
  2. 只收「食物飲料、動植物、日常物品、交通與地點、活動」且有非膚色變體 3D PNG 的資料夾。
  3. 自動篩選(見規格書第七節):
       - 不透明像素佔外框面積 > 90%(整塊方形)→ 排除
       - 不透明面積 < 全圖的 MIN_AREA → 排除
       - 近乎重複的系列(時鐘、月相等)只留代表 → 排除
       - 不適合「切」的內容(武器、死亡、血、菸…)→ 排除
       - 沒有繁體中文名稱 → 排除
  4. 把入選圖片轉成 WebP 放到 img/(RGB 有損 q85、透明通道無損),並驗證 alpha>128 的像素數與原 PNG 完全一致。
  5. 輸出 src/items.json(物品清單,committed)與 src/decor/*.webp(開始畫面的裝飾小圖)。

之後再執行 `python src/build.py` 產生 index.html。
"""
import io
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(HERE, "cache")
PNG_DIR = os.path.join(CACHE, "png")
IMG_OUT = os.path.join(ROOT, "img")
DECOR_OUT = os.path.join(HERE, "decor")
MANIFEST = os.path.join(HERE, "items.json")

REPO = "microsoft/fluentui-emoji"
RAW = "https://raw.githubusercontent.com/%s/main" % REPO
TREE_URL = "https://api.github.com/repos/%s/git/trees/main?recursive=1" % REPO
CLDR = "https://raw.githubusercontent.com/unicode-org/cldr-json/main/cldr-json/cldr-annotations-full/annotations/zh-Hant/annotations.json"
CLDR_DERIVED = "https://raw.githubusercontent.com/unicode-org/cldr-json/main/cldr-json/cldr-annotations-derived-full/annotationsDerived/zh-Hant/annotations.json"

GROUPS = ["Food & Drink", "Animals & Nature", "Objects", "Travel & Places", "Activities"]
MAX_FILL = 0.90      # 不透明像素 / 不透明外框面積 的上限
MIN_AREA = 0.15      # 不透明像素 / (256×256) 的下限(太細的棍狀物,例如筷子、拐杖、掃帚)
WEBP_QUALITY = 90

# v1 的 30 個物品:沿用原本的中文名稱,且一律收錄
V1 = [
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
V1_NAMES = dict((f, zh) for zh, f in V1)

# 開始畫面的裝飾小圖(內嵌在 index.html;其餘圖片一律延遲載入)
DECOR = ["Doughnut", "Croissant", "Taco", "Avocado", "Hot dog", "Carrot", "Broccoli", "Red apple"]
DECOR_PX = 144

# ---- 近乎重複的系列:只留代表 ----
CLOCK_RE = re.compile(r"^(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Eleven|Twelve)(-thirty| o.?clock)$", re.I)
MOON_KEEP = {"Crescent moon", "Full moon", "First quarter moon"}
MOON_SERIES = {
    "New moon", "Waxing crescent moon", "First quarter moon", "Waxing gibbous moon", "Full moon", "Waning gibbous moon",
    "Last quarter moon", "Waning crescent moon", "Crescent moon", "New moon face", "First quarter moon face",
    "Last quarter moon face", "Full moon face",
}
# 其他明顯的近似系列(同一概念的小變化,各系列只留代表)
DROP_NEAR_DUP = {
    "Hourglass not done",                                                                                   # 留 Hourglass done
    "Globe showing americas", "Globe showing asia-australia", "Globe with meridians",                      # 留 europe-africa
    "Speaker low volume", "Speaker medium volume", "Muted speaker",                                         # 留 high volume
    "Closed mailbox with lowered flag", "Open mailbox with lowered flag", "Open mailbox with raised flag",  # 留 closed + raised flag
    "2nd place medal", "3rd place medal",                                                                   # 留 1st
    "Oncoming automobile", "Oncoming bus", "Oncoming police car", "Oncoming taxi",                          # 留一般版本
    "Airplane arrival", "Airplane departure",
    "Sun behind cloud", "Sun behind small cloud", "Cloud with lightning", "Snowman without snow", "Umbrella on ground",
    "Locked with pen", "Unlocked", "Magnifying glass tilted left", "Round pushpin", "Outbox tray", "Musical note",
}
# ---- 不適合在可愛的遊戲裡「切」的內容(輕度判斷:武器、死亡、血與藥物、菸,以及宗教場所與宗教用品)----
DROP_INAPPROPRIATE = {
    "Dagger", "Crossed swords", "Bomb", "Pistol", "Coffin", "Funeral urn", "Headstone", "Cigarette", "Drop of blood",
    "Syringe", "Pill", "Chains", "Kitchen knife", "Hocho", "Knife", "Skull", "Skull and crossbones",
    "Church", "Mosque", "Synagogue", "Hindu temple", "Kaaba", "Shinto shrine", "Prayer beads", "Hamsa", "Nazar amulet",
    "Love hotel", "Wedding",
}


def log(*a):
    print(*a, flush=True)


def http_get(url, binary=True, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cut-in-half-build"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            return data if binary else data.decode("utf-8")
        except Exception as e:  # noqa
            last = e
    raise RuntimeError("下載失敗 %s: %s" % (url, last))


def cached(name, url, binary=False):
    path = os.path.join(CACHE, name)
    if not os.path.exists(path) or os.path.getsize(path) < 10:
        os.makedirs(CACHE, exist_ok=True)
        log("下載", url)
        data = http_get(url, binary=True)
        with open(path, "wb") as f:
            f.write(data)
    with open(path, "rb") as f:
        raw = f.read()
    return raw if binary else raw.decode("utf-8")


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return s


def load_tree():
    return json.loads(cached("tree.json", TREE_URL))["tree"]


def load_meta(folders):
    path = os.path.join(CACHE, "meta.json")
    meta = {}
    if os.path.exists(path):
        meta = json.load(open(path, encoding="utf-8"))
    todo = [f for f in folders if f not in meta]
    if todo:
        log("下載 %d 個 metadata.json" % len(todo))

        def one(f):
            url = "%s/assets/%s/metadata.json" % (RAW, urllib.parse.quote(f))
            return f, json.loads(http_get(url, binary=False))
        with ThreadPoolExecutor(16) as ex:
            for f, m in ex.map(one, todo):
                meta[f] = m
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(meta, fp, ensure_ascii=False)
    return meta


def load_names():
    ann = json.loads(cached("cldr.json", CLDR))["annotations"]["annotations"]
    der = json.loads(cached("cldr_derived.json", CLDR_DERIVED))["annotationsDerived"]["annotations"]

    def lookup(glyph):
        for g in (glyph, glyph.replace("️", ""), glyph + "️"):
            for table in (ann, der):
                if g in table and table[g].get("tts"):
                    return table[g]["tts"][0]
        return None
    return lookup


def png_path(folder):
    return os.path.join(PNG_DIR, slug(folder) + ".png")


def fetch_png(entry):
    folder, rel = entry
    path = png_path(folder)
    if os.path.exists(path) and os.path.getsize(path) > 500:
        return
    url = "%s/%s" % (RAW, urllib.parse.quote(rel))
    with open(path, "wb") as f:
        f.write(http_get(url))


def alpha_stats(path):
    a = np.array(Image.open(path).convert("RGBA"))[:, :, 3] > 128
    ys, xs = np.nonzero(a)
    n = int(a.sum())
    if n == 0:
        return {"n": 0, "fill": 0, "area": 0, "bw": 0, "bh": 0}
    bw, bh = int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
    return {"n": n, "fill": n / float(bw * bh), "area": n / float(a.size), "bw": bw, "bh": bh}


def make_decor():
    """開始畫面裝飾:小尺寸 WebP(內嵌在 index.html,所以要小)"""
    os.makedirs(DECOR_OUT, exist_ok=True)
    for old in os.listdir(DECOR_OUT):
        os.remove(os.path.join(DECOR_OUT, old))
    for f in DECOR:
        im = Image.open(png_path(f)).convert("RGBA").resize((DECOR_PX, DECOR_PX), Image.LANCZOS)
        im.save(os.path.join(DECOR_OUT, slug(f) + ".webp"), "WEBP", quality=78, alpha_quality=90, method=6)


def main():
    if "--decor-only" in sys.argv:
        make_decor()
        return
    os.makedirs(PNG_DIR, exist_ok=True)
    tree = load_tree()
    # 有非膚色變體 3D PNG 的資料夾:assets/<Folder>/3D/<name>_3d.png
    png_rel = {}
    for x in tree:
        m = re.fullmatch(r"assets/([^/]+)/3D/([^/]+\.png)", x["path"])
        if m:
            png_rel[m.group(1)] = x["path"]
    meta = load_meta(sorted(png_rel))
    names = load_names()

    cand = [f for f in sorted(png_rel) if meta[f].get("group") in GROUPS]
    log("符合分類且有 3D PNG 的資料夾:%d" % len(cand))
    with ThreadPoolExecutor(16) as ex:
        list(ex.map(fetch_png, [(f, png_rel[f]) for f in cand]))

    removed = {"clock": [], "moon": [], "neardup": [], "inappropriate": [], "full": [], "small": [], "noname": []}
    keep = []
    for f in cand:
        v1 = f in V1_NAMES
        if not v1:
            if CLOCK_RE.match(f):
                removed["clock"].append(f); continue
            if f in MOON_SERIES and f not in MOON_KEEP:
                removed["moon"].append(f); continue
            if f in DROP_NEAR_DUP:
                removed["neardup"].append(f); continue
            if f in DROP_INAPPROPRIATE:
                removed["inappropriate"].append(f); continue
        st = alpha_stats(png_path(f))
        if not v1:
            if st["fill"] > MAX_FILL:
                removed["full"].append((f, round(st["fill"], 3))); continue
            if st["area"] < MIN_AREA:
                removed["small"].append((f, round(st["area"], 3))); continue
        zh = V1_NAMES.get(f) or names(meta[f]["glyph"])
        if not zh:
            removed["noname"].append(f); continue
        keep.append({"folder": f, "zh": zh, "group": meta[f]["group"], "glyph": meta[f]["glyph"], "st": st, "v1": v1})

    # 同名處理:兩個物品中文名相同時,在後者加上英文原名區分(通常不會發生)
    seen = {}
    for it in keep:
        seen.setdefault(it["zh"], []).append(it)
    dups = {k: [i["folder"] for i in v] for k, v in seen.items() if len(v) > 1}

    # 排序:v1 的 30 個放最前面(保持規格書順序),其餘依群組與資料夾名
    order = {f: i for i, (_, f) in enumerate(V1)}
    keep.sort(key=lambda it: (0, order[it["folder"]]) if it["v1"] else (1, GROUPS.index(it["group"]), it["folder"]))

    # 轉 WebP
    os.makedirs(IMG_OUT, exist_ok=True)
    for old in os.listdir(IMG_OUT):
        if old.endswith(".webp"):
            os.remove(os.path.join(IMG_OUT, old))
    total_bytes = 0
    mismatch = 0
    max_alpha_diff = 0
    items = []
    used = set()
    for it in keep:
        s = slug(it["folder"])
        assert s and s not in used, it["folder"]
        used.add(s)
        src = Image.open(png_path(it["folder"])).convert("RGBA")
        out = os.path.join(IMG_OUT, s + ".webp")
        src.save(out, "WEBP", quality=WEBP_QUALITY, alpha_quality=100, method=4)
        total_bytes += os.path.getsize(out)
        a0 = np.array(src)[:, :, 3]
        a1 = np.array(Image.open(out).convert("RGBA"))[:, :, 3]
        max_alpha_diff = max(max_alpha_diff, int(np.abs(a0.astype(int) - a1.astype(int)).max()))
        if int((a0 > 128).sum()) != int((a1 > 128).sum()):
            mismatch += 1
        items.append({"n": it["zh"], "f": s, "g": it["group"], "e": it["folder"]})

    make_decor()

    with open(MANIFEST, "w", encoding="utf-8") as fp:
        json.dump(items, fp, ensure_ascii=False, indent=0, separators=(",", ":"))
        fp.write("\n")

    # ---- 報告 ----
    by_group = {}
    for i in items:
        by_group[i["g"]] = by_group.get(i["g"], 0) + 1
    log("\n===== 報告 =====")
    log("候選:%d  入選:%d" % (len(cand), len(items)))
    for g in GROUPS:
        log("  %-18s %d" % (g, by_group.get(g, 0)))
    log("排除:時鐘 %d、月相 %d、其他近似系列 %d、不適合 %d、整塊方形(fill>%.2f) %d、面積太小(<%.0f%%) %d、無中文名 %d" % (
        len(removed["clock"]), len(removed["moon"]), len(removed["neardup"]), len(removed["inappropriate"]), MAX_FILL,
        len(removed["full"]), MIN_AREA * 100, len(removed["small"]), len(removed["noname"])))
    for k in ("moon", "neardup", "inappropriate", "full", "small", "noname"):
        log("  [%s] %s" % (k, removed[k]))
    log("  [clock] %s" % removed["clock"])
    log("同名:%s" % dups)
    log("img/:%d 個檔案,共 %.2f MB(平均 %.1f KB)" % (len(items), total_bytes / 1048576.0, total_bytes / 1024.0 / len(items)))
    log("WebP 驗證:alpha>128 像素數不一致 %d 個;alpha 最大差 %d" % (mismatch, max_alpha_diff))
    v1_fail = [it["folder"] for it in keep if it["v1"] and (it["st"]["fill"] > MAX_FILL or it["st"]["area"] < MIN_AREA)]
    log("v1 物品中本會被篩掉的:%s" % v1_fail)


if __name__ == "__main__":
    sys.exit(main())
