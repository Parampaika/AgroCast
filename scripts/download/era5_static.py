"""Статические слои ERA5 / ERA5-Land из бакета Open-Meteo (высота рельефа HSURF, тип почвы soil_type, маска суша-море)
в ячейках точек из cells.csv. -> data/raw/era5_om/<model>/static_cells.csv (cell, iy, ix, <слой>...). Запуск: uv run python -I scripts/download/era5_static.py
"""
import csv
from pathlib import Path
import fsspec, omfiles

ROOT = Path(__file__).resolve().parents[2]
fs = fsspec.filesystem("s3", anon=True)
for model in ["copernicus_era5", "copernicus_era5_land"]:
    cells = list(csv.DictReader((ROOT / f"data/raw/era5_om/{model}/cells.csv").open(encoding="utf-8")))
    uniq = sorted({(int(c["iy"]), int(c["ix"])) for c in cells})
    names = [p.rsplit("/", 1)[1][:-3] for p in fs.ls(f"openmeteo/data/{model}/static/") if p.endswith(".om")]
    res = {u: {} for u in uniq}
    for n in names:
        try:
            with fs.open(f"openmeteo/data/{model}/static/{n}.om", "rb") as f:
                r = omfiles.OmFileReader(f)
                for iy, ix in uniq:
                    res[(iy, ix)][n] = float(r[iy:iy + 1, ix:ix + 1][0, 0])
        except Exception as e:
            print(model, n, "FAILED", repr(e)[:100])
    with (ROOT / f"data/raw/era5_om/{model}/static_cells.csv").open("w", newline="", encoding="utf-8") as o:
        w = csv.writer(o)
        w.writerow(["cell", "iy", "ix"] + names)
        for (iy, ix), d in res.items():
            w.writerow([f"{iy}_{ix}", iy, ix] + [d.get(n, "") for n in names])
    print(model, names, len(uniq), "cells")
