"""MODIS MOD13Q1 v061 (Terra, 250 м, 16-дневные композиты, 2000 — н. в.): NDVI, EVI, pixel_reliability
в точках из data/raw/geo/points.csv. Источник — COG в Microsoft Planetary Computer (STAC без регистрации,
анонимный SAS-токен /api/sas/v1/token). Значение берётся в пикселе точки и как среднее окна 3x3 (750 м).

-> data/raw/modis_ndvi/<tile>/<YYYYDDD>_r<MAX_RANK>.csv (точки с rank_in_region <= MAX_RANK, по умолчанию 2): point_id, date, band, center, mean3x3, n_valid3x3 (сырые целые,
NDVI/EVI scale 0.0001, nodata -3000; pixel_reliability: 0 good, 1 marginal, 2 snow/ice, 3 cloudy, -1 fill).
Запуск: uv run python -I scripts/download/modis_ndvi.py [MAX_RANK]
Читаются NDVI и pixel_reliability (EVI — ссылки есть в _items.csv, но не читается: ~0.4 с на точку×слой).
"""
import csv
import sys
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.warp import transform

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "modis_ndvi"
OUT.mkdir(parents=True, exist_ok=True)
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
BANDS = ["250m_16_days_NDVI", "250m_16_days_EVI", "250m_16_days_pixel_reliability"]  # ссылки в _items.csv
READ_BANDS = ["250m_16_days_NDVI", "250m_16_days_pixel_reliability"]  # EVI пропущен ради скорости
MAX_RANK = int(sys.argv[1]) if len(sys.argv) > 1 else 2  # точки с MIN_RANK <= rank_in_region <= MAX_RANK
MIN_RANK = int(sys.argv[2]) if len(sys.argv) > 2 else 0  # второй аргумент: нижняя граница ранга (докачка остальных точек: 99 3)
R, T = 6371007.181, 1111950.5197665

_tok = {"t": None, "exp": 0}
_lock = threading.Lock()


def token():
    with _lock:
        if time.time() > _tok["exp"]:
            for attempt in range(6):
                try:
                    j = requests.get("https://planetarycomputer.microsoft.com/api/sas/v1/token/modiseuwest/modis-061-cogs", timeout=60).json()
                    break
                except requests.RequestException:
                    time.sleep(10 * (attempt + 1))
            else:
                raise RuntimeError("SAS-токен недоступен")
            _tok["t"], _tok["exp"] = j["token"], time.time() + 1800
        return _tok["t"]


def tile_of(lat, lon):
    x = R * math.radians(lon) * math.cos(math.radians(lat))
    y = R * math.radians(lat)
    return int((x + 20015109.354) // T), int((10007554.677 - y) // T)


def items_for(h, v):
    fn = OUT / f"h{h:02d}v{v:02d}" / "_items.csv"
    if fn.exists():
        return list(csv.DictReader(fn.open(encoding="utf-8")))
    fn.parent.mkdir(exist_ok=True)
    rows = []
    for y in range(2000, 2027):
        body = {"collections": ["modis-13Q1-061"], "limit": 100, "datetime": f"{y}-01-01/{y}-12-31",
                "query": {"modis:horizontal-tile": {"eq": h}, "modis:vertical-tile": {"eq": v}}}
        for attempt in range(6):
            try:
                r = requests.post(STAC, json=body, timeout=120).json()
                break
            except requests.RequestException:
                time.sleep(20 * (attempt + 1))
        else:
            raise RuntimeError("STAC недоступен")
        for f in r.get("features", []):
            if f["id"].startswith("MOD13Q1"):
                rows.append({"id": f["id"], "date": f["properties"]["start_datetime"][:10],
                             **{b: f["assets"][b]["href"] for b in BANDS}})
    with fn.open("w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=["id", "date"] + BANDS)
        w.writeheader()
        w.writerows(rows)
    print(f"h{h:02d}v{v:02d}: {len(rows)} items", flush=True)
    return rows


def process(item, pts, tdir):
    doy = item["id"].split(".")[1][1:]
    fn = tdir / (f"{doy}_r{MAX_RANK}.csv" if MIN_RANK == 0 else f"{doy}_r{MIN_RANK}-{MAX_RANK}.csv")
    if fn.exists():
        return
    out = []
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="3"):
        for b in READ_BANDS:
            for attempt in range(3):
                try:
                    with rasterio.open(f"/vsicurl/{item[b]}?{token()}") as r:
                        xs, ys = transform("EPSG:4326", r.crs, [p["lon"] for p in pts], [p["lat"] for p in pts])
                        for p, x, y in zip(pts, xs, ys):
                            row, col = r.index(x, y)
                            win = r.read(1, window=((row - 1, row + 2), (col - 1, col + 2)), boundless=True,
                                         fill_value=r.nodata if r.nodata is not None else -3000)
                            nod = r.nodata if r.nodata is not None else -3000
                            valid = win[win != nod]
                            out.append([p["point_id"], item["date"], b.replace("250m_16_days_", ""), int(win[1, 1]),
                                        round(float(valid.mean()), 1) if valid.size else "", int(valid.size)])
                    break
                except Exception as e:
                    if attempt == 2:
                        print(item["id"], b, "FAILED", repr(e)[:120], flush=True)
                        return
                    time.sleep(5)
    with fn.open("w", newline="", encoding="utf-8") as fo:
        w = csv.writer(fo)
        w.writerow(["point_id", "date", "band", "center", "mean3x3", "n_valid3x3"])
        w.writerows(out)


def main():
    pts = [{**p, "lat": float(p["lat"]), "lon": float(p["lon"])}
           for p in csv.DictReader((ROOT / "data" / "raw" / "geo" / "points.csv").open(encoding="utf-8"))
           if MIN_RANK <= int(p["rank_in_region"]) <= MAX_RANK]
    by_tile = {}
    for p in pts:
        by_tile.setdefault(tile_of(p["lat"], p["lon"]), []).append(p)
    print(len(by_tile), "tiles", flush=True)
    with ThreadPoolExecutor(48) as ex:
        for (h, v), tp in sorted(by_tile.items(), key=lambda kv: -len(kv[1])):
            tdir = OUT / f"h{h:02d}v{v:02d}"
            items = items_for(h, v)
            list(ex.map(lambda it: process(it, tp, tdir), items))
            print(f"h{h:02d}v{v:02d} done ({len(tp)} points)", flush=True)


if __name__ == "__main__":
    main()
