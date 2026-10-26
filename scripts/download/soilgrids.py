"""SoilGrids v2.0 (ISRIC) для точек из data/raw/geo/points.csv.

REST (rest.isric.org/soilgrids/v2.0/properties/query) на полный набор свойств не успевает ответить за 180 с
(бета-сервис), поэтому основной путь — точечное чтение из глобальных COG/VRT на files.isric.org
(та же модель SoilGrids 2.0, 250 м, проекция Interrupted Goode Homolosine): rasterio.sample по каждой точке.

Выход: data/raw/soilgrids/soilgrids_points.csv — point_id, lat, lon, property, depth, stat, value_raw.
value_raw — целые значения в единицах SoilGrids (mapped units: clay/sand/silt g/kg, soc dg/kg, phh2o pH*10,
nitrogen cg/kg, cec mmol(c)/kg, bdod cg/cm3, cfvo cm3/dm3, ocd hg/m3, ocs t/ha, wv* 10^-3 cm3/cm3);
nodata (вода/город/нет данных) = -32768 сохраняется как есть.
Готовые (property, depth, stat) пропускаются при перезапуске.
Запуск: uv run python -I scripts/download/soilgrids.py
"""
import csv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import rasterio
from rasterio.warp import transform

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "soilgrids"
OUT.mkdir(parents=True, exist_ok=True)
DST = OUT / "soilgrids_points.csv"
BASE = "/vsicurl/https://files.isric.org/soilgrids/latest/data/{p}/{p}_{d}_{s}.vrt"
PROPS = ["clay", "sand", "silt", "soc", "phh2o", "nitrogen", "cec", "bdod", "cfvo", "ocd"]  # wv0010/wv0033/wv1500 на files.isric.org отсутствуют (404)
DEPTHS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm"]
STATS = ["mean", "Q0.05", "Q0.5", "Q0.95", "uncertainty"]

pts = list(csv.DictReader((ROOT / "data" / "raw" / "geo" / "points.csv").open(encoding="utf-8")))
done = set()
if DST.exists():
    for r in csv.DictReader(DST.open(encoding="utf-8")):
        done.add((r["property"], r["depth"], r["stat"]))
# порядок: сначала mean по всем свойствам/глубинам, затем медиана, затем остальные статистики
jobs = [(p, d, s) for s in STATS for p in PROPS for d in DEPTHS if (p, d, s) not in done]
jobs += [("ocs", "0-30cm", s) for s in STATS if ("ocs", "0-30cm", s) not in done]  # ocs есть только для 0–30 см


def run(job):
    prop, depth, stat = job
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", VSI_CACHE="TRUE", GDAL_HTTP_MAX_RETRY="5",
                      GDAL_HTTP_RETRY_DELAY="5"):
        try:
            with rasterio.open(BASE.format(p=prop, d=depth, s=stat)) as r:
                xs, ys = transform("EPSG:4326", r.crs, [float(p["lon"]) for p in pts], [float(p["lat"]) for p in pts])
                vals = [int(v[0]) for v in r.sample(zip(xs, ys))]
        except Exception as e:
            print(job, "FAILED", repr(e)[:150], flush=True)
            return job, None
    print(job, "ok", flush=True)
    return job, vals


new = not DST.exists()
with DST.open("a", newline="", encoding="utf-8") as f, ThreadPoolExecutor(16) as ex:
    w = csv.writer(f)
    if new:
        w.writerow(["point_id", "lat", "lon", "property", "depth", "stat", "value_raw"])
    for (prop, depth, stat), vals in ex.map(run, jobs):
        if vals is None:
            continue
        w.writerows([p["point_id"], p["lat"], p["lon"], prop, depth, stat, v] for p, v in zip(pts, vals))
        f.flush()
