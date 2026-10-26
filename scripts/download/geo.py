"""Границы субъектов РФ: geoBoundaries ADM1 (RUS и UKR — для Крыма, Севастополя и новых субъектов,
которые есть в ЕМИСС с 2014/2023 гг.) и russia.geojson из click_that_hood (альтернатива).
Запуск: uv run python -I scripts/download/geo.py  ->  data/raw/geo/
"""
import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "geo"
OUT.mkdir(parents=True, exist_ok=True)


def get(url, fn):
    fn = OUT / fn
    if fn.exists() and fn.stat().st_size > 0:
        return fn
    r = requests.get(url, timeout=600)
    r.raise_for_status()
    fn.write_bytes(r.content)
    print(fn.name, len(r.content) // 1024, "KB")
    return fn


for iso in ("RUS", "UKR"):
    meta_fn = get(f"https://www.geoboundaries.org/api/current/gbOpen/{iso}/ADM1/", f"geoboundaries_{iso}_ADM1_meta.json")
    meta = json.loads(meta_fn.read_text(encoding="utf-8"))
    get(meta["gjDownloadURL"], f"geoboundaries_{iso}_ADM1.geojson")
    get(meta["simplifiedGeometryGeoJSON"], f"geoboundaries_{iso}_ADM1_simplified.geojson")

get("https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/russia.geojson",
    "click_that_hood_russia.geojson")
