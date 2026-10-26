"""USDA FAS PSD Online — bulk CSV (все страны и товары, включая текущий маркетинговый год 2025/26 и прогноз 2026/27).
-> data/raw/usda_psd/. Запуск: uv run python -I scripts/download/usda_psd.py
"""
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "usda_psd"
OUT.mkdir(parents=True, exist_ok=True)
BASE = "https://apps.fas.usda.gov/psdonline/downloads/"
for name in ["psd_alldata_csv.zip", "psd_grains_pulses_csv.zip", "psd_oilseeds_csv.zip"]:
    fn = OUT / name
    if fn.exists() and fn.stat().st_size > 1000:
        continue
    r = requests.get(BASE + name, timeout=600, headers={"User-Agent": "Mozilla/5.0"})
    print(name, r.status_code, r.headers.get("content-type"), len(r.content))
    if r.ok and r.content[:2] == b"PK":
        fn.write_bytes(r.content)
