"""Другие 8-дневные продукты MODIS (Terra, v061) в точках из data/raw/geo/points.csv: Planetary Computer, COG, без регистрации.
Продукты (аргумент 1):
  lst  — MOD11A2: LST_Day_1km, LST_Night_1km, QC_Day  (K*50 в сыром виде, scale 0.02, 1 км)
  lai  — MOD15A2H: Lai_500m, Fpar_500m, FparLai_QC     (LAI scale 0.1, FPAR scale 0.01; fill > 100/249)
  gpp  — MOD17A2H: Gpp_500m                            (scale 0.0001 кг C/м2 за 8 дней)
Аргумент 2 — максимальный rank_in_region точек (по умолчанию 1). Только вегетационный сезон (апрель–октябрь), 2000/2002–2026.
-> data/raw/modis_<продукт>/<тайл>/<YYYYDDD>_r<rank>.csv: point_id, date, band, center, mean3x3, n_valid3x3 (сырые целые).
Запуск: uv run python -I scripts/download/modis_pc.py lai 1
"""
import csv
import math
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import rasterio
import requests
from rasterio.warp import transform

ROOT = Path(__file__).resolve().parents[2]
CFG = {
    "lst": ("modis-11A2-061", "MOD11A2", ["LST_Day_1km", "LST_Night_1km", "QC_Day"], 0),
    "lai": ("modis-15A2H-061", "MOD15A2H", ["Lai_500m", "Fpar_500m", "FparLai_QC"], 255),
    "gpp": ("modis-17A2H-061", "MOD17A2H", ["Gpp_500m"], 32767),
}
PRODUCT = sys.argv[1]
MAX_RANK = int(sys.argv[2]) if len(sys.argv) > 2 else 1
COLL, PREFIX, BANDS, NODATA = CFG[PRODUCT]
OUT = ROOT / "data" / "raw" / f"modis_{PRODUCT}"
OUT.mkdir(parents=True, exist_ok=True)
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
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
                raise RuntimeError("SAS token")
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
        body = {"collections": [COLL], "limit": 100, "datetime": f"{y}-04-01T00:00:00Z/{y}-10-31T23:59:59Z",
                "query": {"modis:horizontal-tile": {"eq": h}, "modis:vertical-tile": {"eq": v}}}
        for attempt in range(6):
            try:
                r = requests.post(STAC, json=body, timeout=120).json()
                if "features" not in r:
                    raise requests.RequestException(str(r)[:200])
                break
            except requests.RequestException:
                time.sleep(20 * (attempt + 1))
        else:
            raise RuntimeError("STAC")
        for f in r.get("features", []):
            if f["id"].startswith(PREFIX):
                rows.append({"id": f["id"], "date": f["properties"]["start_datetime"][:10],
                             **{b: f["assets"][b]["href"] for b in BANDS}})
    with fn.open("w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=["id", "date"] + BANDS)
        w.writeheader()
        w.writerows(rows)
    print(f"h{h:02d}v{v:02d}: {len(rows)} items", flush=True)
    return rows


def process(item, pts, tdir):
    fn = tdir / f"{item['id'].split('.')[1][1:]}_r{MAX_RANK}.csv"
    if fn.exists():
        return
    out = []
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="3"):
        for b in BANDS:
            for attempt in range(3):
                try:
                    with rasterio.open(f"/vsicurl/{item[b]}?{token()}") as r:
                        nod = r.nodata if r.nodata is not None else NODATA
                        xs, ys = transform("EPSG:4326", r.crs, [p["lon"] for p in pts], [p["lat"] for p in pts])
                        for p, x, y in zip(pts, xs, ys):
                            row, col = r.index(x, y)
                            win = r.read(1, window=((row - 1, row + 2), (col - 1, col + 2)), boundless=True, fill_value=nod)
                            valid = win[win != nod]
                            out.append([p["point_id"], item["date"], b, int(win[1, 1]),
                                        round(float(valid.mean()), 2) if valid.size else "", int(valid.size)])
                    break
                except Exception as e:
                    if attempt == 2:
                        print(item["id"], b, "FAILED", repr(e)[:100], flush=True)
                        return
                    time.sleep(5)
    with fn.open("w", newline="", encoding="utf-8") as fo:
        w = csv.writer(fo)
        w.writerow(["point_id", "date", "band", "center", "mean3x3", "n_valid3x3"])
        w.writerows(out)


def main():
    pts = [{**p, "lat": float(p["lat"]), "lon": float(p["lon"])}
           for p in csv.DictReader((ROOT / "data" / "raw" / "geo" / "points.csv").open(encoding="utf-8"))
           if int(p["rank_in_region"]) <= MAX_RANK]
    by_tile = {}
    for p in pts:
        by_tile.setdefault(tile_of(p["lat"], p["lon"]), []).append(p)
    print(PRODUCT, len(pts), "points,", len(by_tile), "tiles", flush=True)
    with ThreadPoolExecutor(24) as ex:
        for (h, v), tp in sorted(by_tile.items(), key=lambda kv: -len(kv[1])):
            tdir = OUT / f"h{h:02d}v{v:02d}"
            list(ex.map(lambda it: process(it, tp, tdir), items_for(h, v)))
            print(f"h{h:02d}v{v:02d} done ({len(tp)} points)", flush=True)


if __name__ == "__main__":
    main()
