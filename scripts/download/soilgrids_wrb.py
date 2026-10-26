"""SoilGrids WRB: наиболее вероятный класс почвы (MostProbable) и вероятности классов в точках из points.csv.
-> data/raw/soilgrids/wrb_points.csv: point_id, lat, lon, layer, value_raw (для MostProbable — код класса, расшифровка в
data/raw/soilgrids/wrb_classes.json из MostProbable.vrt.aux/ или в QML слоя; вероятности классов — 0..100).
Запуск: uv run python -I scripts/download/soilgrids_wrb.py
"""
import csv
from pathlib import Path
import rasterio
from rasterio.warp import transform

ROOT = Path(__file__).resolve().parents[2]
pts = list(csv.DictReader((ROOT / "data/raw/geo/points.csv").open(encoding="utf-8")))
BASE = "/vsicurl/https://files.isric.org/soilgrids/latest/data/wrb/"
out = ROOT / "data/raw/soilgrids/wrb_points.csv"
with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"), out.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["point_id", "lat", "lon", "layer", "value_raw"])
    with rasterio.open(BASE + "MostProbable.vrt") as r:
        xs, ys = transform("EPSG:4326", r.crs, [float(p["lon"]) for p in pts], [float(p["lat"]) for p in pts])
        vals = [int(v[0]) for v in r.sample(zip(xs, ys))]
        w.writerows([p["point_id"], p["lat"], p["lon"], "MostProbable", v] for p, v in zip(pts, vals))
        try:
            import json
            (ROOT / "data/raw/soilgrids/wrb_mostprobable_meta.json").write_text(
                json.dumps({"tags": r.tags(), "cat": r.categories(1) if hasattr(r, "categories") else None,
                            "colormap_keys": list(r.colormap(1).keys())[:200] if r.colorinterp[0].name == "palette" else None},
                           ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        except Exception as e:
            print("meta", repr(e)[:100])
print(len(pts), "points ->", out)
