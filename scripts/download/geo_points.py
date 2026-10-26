"""Точки на сельхозугодьях для каждого субъекта РФ -> data/raw/geo/points.csv.

1. Полигоны: geoBoundaries ADM1 (simplified), RUS + UKR (см. regions_table.py).
2. Кандидаты: регулярная сетка внутри полигона (~600 узлов на регион, шаг >= 0.05°).
3. Маска пашни: ESA WorldCover 2021 v200 (10 м, COG на AWS, без ключа), читается обзорный уровень 1/64
   (~640 м/пикс). Сам обзорный слой тайла кэшируется в data/raw/worldcover/ov64/<tile>.npy.
   Для кандидата считается доля класса 40 (cropland) в окне 5x5 пикселей обзора (~3x3 км).
4. Отбор: кандидаты с долей пашни >= 0.25; число точек N = clip(площадь_пашни_км2 / 2500, 2, 15), не меньше 5 при пашне > 8000 км2;
   точки разносятся по региону farthest-point sampling. Если пашни нет — 1–2 точки в южной части
   региона вне воды/снега/застройки (method=fallback_south).
"""
import csv
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from shapely.geometry import shape, Point
from shapely.prepared import prep

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data" / "raw" / "geo"
WC = ROOT / "data" / "raw" / "worldcover" / "ov64"
WC.mkdir(parents=True, exist_ok=True)
WC_URL = "/vsicurl/https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{}_Map.tif"


def norm(s):
    return s.replace("–", "-").replace("—", "-").strip().lower()


def tile_name(lat, lon):
    la, lo = math.floor(lat / 3) * 3, math.floor(lon / 3) * 3
    return f"{'N' if la >= 0 else 'S'}{abs(la):02d}{'E' if lo >= 0 else 'W'}{abs(lo):03d}", la, lo


_cache = {}


def tile(name):
    if name in _cache:
        return _cache[name]
    fn = WC / f"{name}.npy"
    if fn.exists():
        arr = np.load(fn)
    else:
        try:
            with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"), \
                    rasterio.open(WC_URL.format(name), overview_level=5) as r:
                arr = r.read(1)
        except rasterio.errors.RasterioIOError:
            arr = np.zeros((1, 1), dtype=np.uint8)  # тайла нет (море) -> 0 = нет данных
        np.save(fn, arr)
        print("  tile", name, arr.shape, flush=True)
    _cache[name] = arr
    return arr


def land_stats(lat, lon):
    """(доля пашни, класс в центре) в окне 5x5 обзорного уровня."""
    name, la, lo = tile_name(lat, lon)
    a = tile(name)
    if a.shape == (1, 1):
        return 0.0, 0
    n = a.shape[0]
    row = int((la + 3 - lat) / 3 * n)
    col = int((lon - lo) / 3 * a.shape[1])
    w = a[max(row - 2, 0): row + 3, max(col - 2, 0): col + 3]
    return float((w == 40).mean()), int(a[min(row, n - 1), min(col, a.shape[1] - 1)])


def fps(pts, k, first):
    chosen = [first]
    d = np.full(len(pts), np.inf)
    for _ in range(k - 1):
        d = np.minimum(d, np.hypot(*(pts - pts[chosen[-1]]).T))
        chosen.append(int(d.argmax()))
    return chosen


def main():
    regions = list(csv.DictReader((GEO / "regions.csv").open(encoding="utf-8")))
    polys = {}
    for src in ("RUS", "UKR"):
        g = json.loads((GEO / f"geoboundaries_{src}_ADM1_simplified.geojson").read_text(encoding="utf-8"))
        for f in g["features"]:
            polys[(src, norm(f["properties"]["shapeName"]))] = shape(f["geometry"])
    out_rows = []
    for reg in regions:
        geom = polys[(reg["gb_source"], norm(reg["gb_name"]))]
        pg = prep(geom)
        minx, miny, maxx, maxy = geom.bounds
        if maxx - minx > 180:  # Чукотка через 180° — берём только восточное полушарие
            minx = max(minx, 0)
        area_deg = geom.area
        step = max(0.05, math.sqrt(area_deg / 600))
        cands = [(y, x) for y in np.arange(miny + step / 2, maxy, step) for x in np.arange(minx + step / 2, maxx, step)
                 if pg.contains(Point(x, y))]
        if not cands:
            c = geom.representative_point()
            cands = [(c.y, c.x)]
        stats = [land_stats(y, x) for y, x in cands]
        frac = np.array([s[0] for s in stats])
        cls = np.array([s[1] for s in stats])
        pts = np.array(cands)
        # площадь региона в км2 (приближённо) и пашни
        lat0 = np.mean([p[0] for p in cands])
        area_km2 = area_deg * 111.32 ** 2 * math.cos(math.radians(lat0))
        crop_km2 = float(frac.mean()) * area_km2
        good = np.where(frac >= 0.25)[0]
        if len(good) > 0:
            k = int(np.clip(round(crop_km2 / 2500), 2, 15))
            if crop_km2 > 8000:
                k = max(k, 5)
            k = min(k, len(good))
            sel = good[fps(pts[good], k, int(frac[good].argmax()))]
            method = "worldcover_cropland_fps"
        else:
            ok = np.where(~np.isin(cls, [0, 50, 70, 80]))[0]  # нет данных, застройка, снег/лёд, вода
            if len(ok) == 0:
                ok = np.arange(len(pts))
            south = ok[pts[ok, 0] <= np.quantile(pts[ok, 0], 0.2)]
            k = min(2 if area_km2 > 50000 else 1, len(south))
            sel = south[fps(pts[south], k, int(np.argmin(pts[south, 0])))]
            method = "fallback_south"
        for j, i in enumerate(sel):
            out_rows.append({"point_id": f"{reg['iso3166_2']}_{j:02d}", "okato": reg["okato"],
                             "region": reg["name_emiss"], "iso3166_2": reg["iso3166_2"],
                             "lat": round(float(pts[i, 0]), 4), "lon": round(float(pts[i, 1]), 4),
                             "method": method, "crop_frac_3km": round(float(frac[i]), 3),
                             "wc_class_center": int(cls[i]), "rank_in_region": j,
                             "region_crop_km2_est": round(crop_km2)})
        print(reg["iso3166_2"], len(cands), "cands, crop_km2~", round(crop_km2), "->", len(sel), method, flush=True)
    with (GEO / "points.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0]))
        w.writeheader()
        w.writerows(out_rows)
    print(len(out_rows), "points")


if __name__ == "__main__":
    main()
