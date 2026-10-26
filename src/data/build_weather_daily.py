"""Почасовые ERA5 / ERA5-Land (бакет Open-Meteo) → суточные ряды по точкам и регионам.

Запуск:
    uv run python -I -X utf8 src/data/build_weather_daily.py

Вход:  data/raw/era5_om/<model>/<var>/{year_YYYY,chunk_N}.parquet (индекс time_utc, колонки — ячейки),
       data/raw/era5_om/<model>/cells.csv (point_id → cell), data/raw/geo/points.csv.
Выход: data/processed/weather/cell_daily/<model>__<var>__<agg>.parquet — дата × ячейка;
       data/processed/weather/point_daily.parquet — длинная таблица point_id × date × переменные;
       data/processed/weather/region_daily.parquet — среднее по точкам субъекта (okato × date).

Сутки — местные: время UTC сдвигается на round(lon/15) ч (солнечное время ячейки).
Неполные сутки (< 20 ч) — NaN. Источники:
  ERA5-Land (0.1°): температура, точка росы, влажность и температура почвы, снег (в 2022 г. пробел);
  ERA5 (0.25°): осадки, радиация, ветер, снегопад; температура — запасной вариант для ячеек над морем.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import PROC_ROOT, ROOT  # noqa: E402

RAW = ROOT / "data" / "raw" / "era5_om"
OUT = PROC_ROOT / "weather"
CELL_OUT = OUT / "cell_daily"
CELL_OUT.mkdir(parents=True, exist_ok=True)

# (модель, переменная) → агрегаты
SPEC = {
    ("copernicus_era5_land", "temperature_2m"): ["mean", "max", "min"],
    ("copernicus_era5_land", "dew_point_2m"): ["mean"],
    ("copernicus_era5_land", "soil_moisture_0_to_7cm"): ["mean"],
    ("copernicus_era5_land", "soil_moisture_7_to_28cm"): ["mean"],
    ("copernicus_era5_land", "soil_moisture_28_to_100cm"): ["mean"],
    ("copernicus_era5_land", "soil_temperature_0_to_7cm"): ["min"],
    ("copernicus_era5_land", "snow_depth"): ["mean"],
    ("copernicus_era5", "temperature_2m"): ["mean", "max", "min"],
    ("copernicus_era5", "dew_point_2m"): ["mean"],
    ("copernicus_era5", "precipitation"): ["sum"],
    ("copernicus_era5", "snowfall_water_equivalent"): ["sum"],
    ("copernicus_era5", "shortwave_radiation"): ["mean"],
    ("copernicus_era5", "wind_speed_10m"): ["mean"],  # из u/v
}


def files(model: str, var: str) -> list[Path]:
    d = RAW / model / var
    yrs = sorted(d.glob("year_*.parquet"))
    ch = sorted(d.glob("chunk_*.parquet"), key=lambda p: int(p.stem.split("_")[1]))
    return yrs + ch


def read(model: str, var: str, f: Path) -> pd.DataFrame:
    if var == "wind_speed_10m":
        u = pd.read_parquet(f)
        v = pd.read_parquet(RAW / model / "wind_v_component_10m" / f.name.replace("u_component", "v_component"))
        return np.sqrt(u ** 2 + v.reindex_like(u) ** 2)
    return pd.read_parquet(f)


def daily(model: str, var: str, aggs: list[str]) -> dict[str, pd.DataFrame]:
    src_var = "wind_u_component_10m" if var == "wind_speed_10m" else var
    cells = pd.read_csv(RAW / model / "cells.csv").drop_duplicates("cell")
    offset = dict(zip(cells.cell, np.round(cells.cell_lon / 15).astype(int)))
    parts = []
    for f in files(model, src_var):
        df = read(model, var, f)
        df = df[~df.index.duplicated()]
        groups: dict[int, list[str]] = {}
        for c in df.columns:
            groups.setdefault(offset.get(c, 3), []).append(c)
        for off, cols in groups.items():
            sub = df[cols].copy()
            sub.index = sub.index + pd.Timedelta(hours=int(off))
            g = sub.groupby(sub.index.floor("D"))
            p = {"count": g.count()}
            if "mean" in aggs or "sum" in aggs:
                p["sum"] = g.sum(min_count=1)
            if "max" in aggs:
                p["max"] = g.max()
            if "min" in aggs:
                p["min"] = g.min()
            parts.append(p)
    res = {}
    cnt = pd.concat([p["count"] for p in parts]).groupby(level=0).sum()
    full = cnt >= 20
    for a in aggs:
        if a in ("mean", "sum"):
            s = pd.concat([p["sum"] for p in parts]).groupby(level=0).sum(min_count=1)
            v = s / cnt if a == "mean" else s
        elif a == "max":
            v = pd.concat([p["max"] for p in parts]).groupby(level=0).max()
        else:
            v = pd.concat([p["min"] for p in parts]).groupby(level=0).min()
        v = v.where(full.reindex_like(v).fillna(False)).astype("float32")
        v.index.name = "date"
        res[a] = v
    return res


def et0_fao56(tmax, tmin, tdew, rs_wm2, u10, lat_deg, doy, z):
    """Суточная эталонная эвапотранспирация FAO-56 (мм/сут). Все аргументы — массивы одной формы."""
    tmean = (tmax + tmin) / 2
    e0 = lambda t: 0.6108 * np.exp(17.27 * t / (t + 237.3))  # noqa: E731
    es = (e0(tmax) + e0(tmin)) / 2
    ea = e0(tdew)
    rs = rs_wm2 * 0.0864
    phi = np.deg2rad(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    dec = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(dec), -1, 1))
    ra = 24 * 60 / np.pi * 0.0820 * dr * (ws * np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.sin(ws))
    rso = (0.75 + 2e-5 * z) * ra
    rns = 0.77 * rs
    ratio = np.clip(np.where(rso > 0, rs / np.where(rso > 0, rso, 1), 0.5), 0.25, 1.0)
    rnl = 4.903e-9 * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2 * (0.34 - 0.14 * np.sqrt(np.clip(ea, 0, None))) \
        * (1.35 * ratio - 0.35)
    rn = rns - rnl
    p = 101.3 * ((293 - 0.0065 * z) / 293) ** 5.26
    gamma = 0.000665 * p
    delta = 4098 * e0(tmean) / (tmean + 237.3) ** 2
    u2 = u10 * 4.87 / np.log(67.8 * 10 - 5.42)
    et0 = (0.408 * delta * rn + gamma * 900 / (tmean + 273) * u2 * (es - ea)) / (delta + gamma * (1 + 0.34 * u2))
    return np.clip(et0, 0, None), es - ea


def main():
    # 1. суточные по ячейкам
    for (model, var), aggs in SPEC.items():
        names = {a: CELL_OUT / f"{model}__{var}__{a}.parquet" for a in aggs}
        if all(p.exists() for p in names.values()):
            continue
        res = daily(model, var, aggs)
        for a, v in res.items():
            v.to_parquet(names[a])
        print(model, var, aggs, res[aggs[0]].shape, res[aggs[0]].index.min().date(), res[aggs[0]].index.max().date(),
              flush=True)

    # 2. по точкам
    pts = pd.read_csv(ROOT / "data" / "raw" / "geo" / "points.csv", dtype={"okato": str})
    cl = {m: pd.read_csv(RAW / m / "cells.csv").set_index("point_id").cell for m in
          ("copernicus_era5", "copernicus_era5_land")}
    stat = pd.read_csv(RAW / "copernicus_era5" / "static_cells.csv").set_index("cell").HSURF

    def pt(model, var, agg):
        w = pd.read_parquet(CELL_OUT / f"{model}__{var}__{agg}.parquet")
        cols = cl[model].reindex(pts.point_id)
        out = w.reindex(columns=cols.values)
        out.columns = pts.point_id.values
        return out

    land, era = "copernicus_era5_land", "copernicus_era5"
    V = {}
    for agg in ("mean", "max", "min"):
        t_l, t_e = pt(land, "temperature_2m", agg), pt(era, "temperature_2m", agg)
        V[f"t{agg}"] = t_l.combine_first(t_e.reindex_like(t_l))
    V["tdew"] = pt(land, "dew_point_2m", "mean").combine_first(pt(era, "dew_point_2m", "mean"))
    V["prec"] = pt(era, "precipitation", "sum")
    V["snowfall"] = pt(era, "snowfall_water_equivalent", "sum")
    V["rad"] = pt(era, "shortwave_radiation", "mean")
    V["wind"] = pt(era, "wind_speed_10m", "mean")
    V["sm0_7"] = pt(land, "soil_moisture_0_to_7cm", "mean")
    V["sm7_28"] = pt(land, "soil_moisture_7_to_28cm", "mean")
    V["sm28_100"] = pt(land, "soil_moisture_28_to_100cm", "mean")
    V["tsoil_min"] = pt(land, "soil_temperature_0_to_7cm", "min")
    V["snow_depth"] = pt(land, "snow_depth", "mean")
    idx = V["tmean"].index
    for k in V:
        V[k] = V[k].reindex(idx)

    lat = pts.set_index("point_id").lat.reindex(V["tmax"].columns).values[None, :]
    z = cl[era].reindex(V["tmax"].columns).map(stat).fillna(0).values[None, :]
    doy = idx.dayofyear.values[:, None]
    et0, vpd = et0_fao56(V["tmax"].values, V["tmin"].values, V["tdew"].values, V["rad"].values, V["wind"].values,
                         lat, doy, z)
    V["et0"] = pd.DataFrame(et0, index=idx, columns=V["tmax"].columns).astype("float32")
    V["vpd"] = pd.DataFrame(vpd, index=idx, columns=V["tmax"].columns).astype("float32")

    long = pd.concat({k: v.stack(future_stack=True) for k, v in V.items()}, axis=1)
    long.index.names = ["date", "point_id"]
    long = long.reset_index()
    long.to_parquet(OUT / "point_daily.parquet", index=False)
    print("point_daily", long.shape, flush=True)

    # 3. по регионам: среднее по точкам с весом доли пашни вокруг точки
    w = pts.set_index("point_id").crop_frac_3km.clip(lower=0.05)
    long = long.merge(pts[["point_id", "okato"]], on="point_id")
    long["w"] = long.point_id.map(w)
    vals = [c for c in V]
    num = long[vals].mul(long.w, axis=0)
    num["okato"], num["date"] = long.okato, long.date
    den = long[vals].notna().mul(long.w, axis=0)
    den["okato"], den["date"] = long.okato, long.date
    reg = num.groupby(["okato", "date"]).sum(min_count=1) / den.groupby(["okato", "date"]).sum()
    reg = reg.astype("float32").reset_index()
    reg.to_parquet(OUT / "region_daily.parquet", index=False)
    print("region_daily", reg.shape, reg.date.min(), reg.date.max())


if __name__ == "__main__":
    main()
