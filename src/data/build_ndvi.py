"""NDVI MODIS MOD13Q1 (16-дневные композиты) по точкам → ряды по регионам.

Запуск:
    uv run python -I -X utf8 src/data/build_ndvi.py

Берутся только файлы `*_r2.csv` (точки rank_in_region ≤ 2, скачаны полностью за 2000–2026).
Значение — mean3x3 / 10000 (окно ~750 м); если в окне меньше 5 годных пикселей — center / 10000.
Отбрасываются пиксели с pixel_reliability не 0/1 (облака, снег, нет данных).
Выход: data/processed/ndvi/point_ndvi.parquet, data/processed/ndvi/region_ndvi.parquet (okato × date).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import PROC_ROOT, ROOT  # noqa: E402

RAW = ROOT / "data" / "raw" / "modis_ndvi"
OUT = PROC_ROOT / "ndvi"
OUT.mkdir(parents=True, exist_ok=True)


def main():
    parts = [pd.read_csv(f) for f in sorted(RAW.glob("h*/*_r2.csv"))]
    df = pd.concat(parts, ignore_index=True)
    nd = df[df.band == "NDVI"].drop(columns="band")
    rel = df[df.band == "pixel_reliability"][["point_id", "date", "center"]].rename(columns={"center": "rel"})
    nd = nd.merge(rel, on=["point_id", "date"], how="left")
    nd["ndvi"] = (nd.mean3x3.where(nd.n_valid3x3 >= 5, nd.center) / 10000).where(nd.rel.isin([0, 1]))
    nd["ndvi"] = nd.ndvi.where(nd.ndvi.between(-0.2, 1))
    nd["date"] = pd.to_datetime(nd.date)
    nd = nd.drop_duplicates(["point_id", "date"])
    nd[["point_id", "date", "ndvi", "rel"]].to_parquet(OUT / "point_ndvi.parquet", index=False)

    pts = pd.read_csv(ROOT / "data" / "raw" / "geo" / "points.csv", dtype={"okato": str})
    nd = nd.merge(pts[["point_id", "okato"]], on="point_id")
    reg = nd.groupby(["okato", "date"]).agg(ndvi=("ndvi", "mean"), n_pts=("ndvi", "count")).reset_index()
    reg.to_parquet(OUT / "region_ndvi.parquet", index=False)
    print("точек", nd.point_id.nunique(), "регионов", reg.okato.nunique(), "дат", reg.date.nunique(),
          reg.date.min().date(), reg.date.max().date(), "доля годных", round(nd.ndvi.notna().mean(), 3))


if __name__ == "__main__":
    main()
