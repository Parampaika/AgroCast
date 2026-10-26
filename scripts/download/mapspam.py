"""MapSPAM 2020 v2.0 r2 (IFPRI, Harvard Dataverse doi:10.7910/DVN/SWPENT): глобальные растры 5' (~10 км)
по 46 культурам — убранная/физическая площадь, производство, урожайность (rainfed/irrigated/all).
Берём GeoTIFF-архивы (растры) + readme. -> data/raw/mapspam2020/
Запуск: uv run python -I scripts/download/mapspam.py
"""
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "mapspam2020"
OUT.mkdir(parents=True, exist_ok=True)
FILES = {13803225: "Readme_SPAM2020V2r2.txt",
         13827040: "spam2020V2r2_global_harvested_area.geotiff.zip",
         13827041: "spam2020V2r2_global_physical_area.geotiff.zip",
         13827043: "spam2020V2r2_global_production.geotiff.zip",
         13827044: "spam2020V2r2_global_yield.geotiff.zip"}
for fid, name in FILES.items():
    fn = OUT / name
    if fn.exists():
        continue
    with requests.get(f"https://dataverse.harvard.edu/api/access/datafile/{fid}", stream=True, timeout=900) as r:
        r.raise_for_status()
        with open(fn.with_suffix(".part"), "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    fn.with_suffix(".part").rename(fn)
    print(name, fn.stat().st_size // 2**20, "MB", flush=True)
