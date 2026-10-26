"""Почасовые ряды ERA5 / ERA5-Land для точек из data/raw/geo/points.csv напрямую из открытого бакета
Open-Meteo на AWS (s3://openmeteo, без ключа; это те же данные, что отдаёт archive-api.open-meteo.com,
но без суточного лимита API).

Файлы в бакете: data/<model>/<var>/year_YYYY.om (полный год, по 2021) и chunk_N.om (N*504 ч от 1970-01-01 UTC,
покрывают 2022 — н. в.). Массив [lat, lon, time], lat от -90 (шаг 0.25° ERA5, 0.1° ERA5-Land), lon от -180.

Выход: data/raw/era5_om/<model>/<var>/<year_YYYY|chunk_N>.parquet — колонки time(UTC) + по одной колонке
на ячейку сетки "iy_ix"; data/raw/era5_om/<model>/cells.csv — точка -> ячейка.
Запуск: uv run python -I scripts/download/era5_openmeteo_s3.py era5_land temperature_2m dew_point_2m ...
"""
import asyncio
import csv
import sys
import time
from pathlib import Path

import fsspec
import numpy as np
import omfiles
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "era5_om"
RES = {"copernicus_era5": 0.25, "copernicus_era5_land": 0.1}
FIRST_YEAR, LAST_YEAR_FILE = 2000, 2021
CHUNK_H = 504


def cells_for(model):
    res = RES[model]
    pts = list(csv.DictReader((ROOT / "data" / "raw" / "geo" / "points.csv").open(encoding="utf-8")))
    rows = []
    for p in pts:
        lat, lon = float(p["lat"]), float(p["lon"])
        iy, ix = int(round((lat + 90) / res)), int(round((lon + 180) / res))
        rows.append({"point_id": p["point_id"], "lat": lat, "lon": lon, "iy": iy, "ix": ix,
                     "cell_lat": round(iy * res - 90, 3), "cell_lon": round(ix * res - 180, 3), "cell": f"{iy}_{ix}"})
    d = OUT / model
    d.mkdir(parents=True, exist_ok=True)
    with (d / "cells.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return sorted({(r["iy"], r["ix"]) for r in rows})


async def read_file(fs, url, cells, sem):
    r = await omfiles.OmFileReaderAsync.from_fsspec(fs, url)
    nt = r.shape[2]
    slabs = sorted({(iy, ix // 6 * 6) for iy, ix in cells})

    async def rd(iy, x0):
        async with sem:
            for attempt in range(5):
                try:
                    return (iy, x0), await r.read_array((slice(iy, iy + 1), slice(x0, min(x0 + 6, r.shape[1])), slice(0, nt)))
                except Exception as e:  # сетевые сбои — повтор
                    if attempt == 4:
                        raise
                    await asyncio.sleep(2 * (attempt + 1))

    res = dict(await asyncio.gather(*[rd(*s) for s in slabs]))
    data = {f"{iy}_{ix}": res[(iy, ix // 6 * 6)][0, ix - ix // 6 * 6, :].astype("float32") for iy, ix in cells}
    return nt, data


async def run(model, variables):
    cells = cells_for(model)
    fs = fsspec.filesystem("s3", anon=True, asynchronous=True, config_kwargs={"max_pool_connections": 128})
    session = await fs.set_session()
    sem = asyncio.Semaphore(96)
    for var in variables:
        d = OUT / model / var
        d.mkdir(parents=True, exist_ok=True)
        listing = await fs._ls(f"openmeteo/data/{model}/{var}/", detail=False)
        names = [p.rsplit("/", 1)[1] for p in listing]
        jobs = [f"year_{y}" for y in range(FIRST_YEAR, LAST_YEAR_FILE + 1) if f"year_{y}.om" in names]
        start_chunk = int(pd.Timestamp(f"{LAST_YEAR_FILE + 1}-01-01").value // 3_600_000_000_000 // CHUNK_H)
        jobs += sorted((n[:-3] for n in names if n.startswith("chunk_") and int(n[6:-3]) >= start_chunk),
                       key=lambda s: int(s[6:]))
        for stem in jobs:
            fn = d / f"{stem}.parquet"
            if fn.exists():
                continue
            t0 = time.time()
            try:
                nt, data = await read_file(fs, f"s3://openmeteo/data/{model}/{var}/{stem}.om", cells, sem)
            except Exception as e:
                print(model, var, stem, "FAILED", repr(e)[:200], flush=True)
                continue
            if stem.startswith("year_"):
                t = pd.date_range(f"{stem[5:]}-01-01", periods=nt, freq="h")
            else:
                t = pd.date_range(pd.Timestamp(int(stem[6:]) * CHUNK_H * 3600, unit="s"), periods=nt, freq="h")
            df = pd.DataFrame(data, index=t)
            df.index.name = "time_utc"
            df.to_parquet(fn.with_suffix(".tmp"), compression="zstd")
            fn.with_suffix(".tmp").rename(fn)
            print(model, var, stem, f"{len(cells)} cells, {time.time() - t0:.0f}s", flush=True)
    await session.close()


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1] if sys.argv[1].startswith("copernicus") else "copernicus_" + sys.argv[1], sys.argv[2:]))
