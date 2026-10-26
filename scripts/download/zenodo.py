"""Скачивание всех файлов записи Zenodo: uv run python -I scripts/download/zenodo.py <record_id> <папка>
-> data/raw/<папка>/ (+ record.json с метаданными записи).
Использовано для: 5062513 — GGCMI Phase 3 crop calendar (Jägermeyr et al. 2021), сетка 0.5°,
даты посева/созревания по культурам (rf/ir).
"""
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
rec, folder = sys.argv[1], sys.argv[2]
OUT = ROOT / "data" / "raw" / folder
OUT.mkdir(parents=True, exist_ok=True)
meta = requests.get(f"https://zenodo.org/api/records/{rec}", timeout=120).json()
(OUT / "record.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
for f in meta["files"]:
    fn = OUT / f["key"]
    if fn.exists() and fn.stat().st_size == f["size"]:
        continue
    with requests.get(f["links"]["self"], stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(fn, "wb") as out:
            for chunk in r.iter_content(1 << 20):
                out.write(chunk)
    print(f["key"], f["size"] // 1024, "KB", flush=True)
