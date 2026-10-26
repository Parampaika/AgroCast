"""Календарь посева и уборки «регион × культура»: data/clean/crop_calendar.parquet.

GGCMI Phase 3 (Jägermeyr et al., 2021; сетка 0,5°): день посева (planting_day), созревания (maturity_day)
и длина сезона по каждой точке пашни; режим rf (богара) — основной, ir (орошение) — справочно.
Если в ячейке точки нет значения, берётся ближайшая непустая ячейка в окне 5×5 (±1°).
Регион — циркулярное среднее дня года по точкам с весом доли пашни.
Культуры ЕМИСС сопоставлены с GGCMI в crops.parquet (ggcmi_crop, ggcmi_proxy — если нужен аналог).
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import rasterio

from preprocess.common import RAW, Config, load, points, save, write_stats

VARS = ["planting_day", "maturity_day", "growing_season_length"]


def _read(crop: str, irr: str, var: str) -> np.ndarray:
    f = RAW / "crop_calendar_ggcmi" / f"{crop}_{irr}_ggcmi_crop_calendar_phase3_v1.01.nc4"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with rasterio.open(f"netcdf:{f.as_posix()}:{var}") as s:
            a = s.read(1).astype("float64")
    a[a > 1e19] = np.nan
    return a  # строка 0 — 89.75° с. ш., столбец 0 — −179.75° в. д.


def _sample(a: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    r = np.clip(((90 - lat) / 0.5).astype(int), 0, 359)
    c = np.clip(((lon + 180) / 0.5).astype(int), 0, 719)
    v = a[r, c]
    moved = np.zeros(len(v), bool)
    for i in np.where(np.isnan(v))[0]:
        best = None
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                x = a[np.clip(r[i] + dr, 0, 359), (c[i] + dc) % 720]
                if not np.isnan(x) and (best is None or dr * dr + dc * dc < best[0]):
                    best = (dr * dr + dc * dc, x)
        if best:
            v[i], moved[i] = best[1], True
    return v, moved


def _circ_mean(doy: pd.Series, w: pd.Series) -> float:
    ok = doy.notna()
    if not ok.any():
        return np.nan
    ang = 2 * np.pi * doy[ok] / 365.0
    s, c = (np.sin(ang) * w[ok]).sum(), (np.cos(ang) * w[ok]).sum()
    d = np.arctan2(s, c) * 365.0 / (2 * np.pi)
    return float(round(d % 365, 1)) or 365.0


def build(cfg: Config) -> None:
    crops = load("crops").dropna(subset=["ggcmi_crop"])
    pts = points()
    rows = []
    for g in sorted(crops.ggcmi_crop.unique()):
        df = pts[["point_id", "okato", "w"]].copy()
        for irr in ("rf", "ir"):
            for var in VARS:
                v, moved = _sample(_read(g, irr, var), pts.lat.values, pts.lon.values)
                df[f"{var}_{irr}"] = v
                if var == "planting_day" and irr == "rf":
                    df["moved"] = moved
        for okato, x in df.groupby("okato"):
            rec = {"okato": okato, "ggcmi_crop": g, "n_points": len(x),
                   "n_points_valid": int(x.planting_day_rf.notna().sum()), "n_points_neighbor": int(x.moved.sum())}
            for irr in ("rf", "ir"):
                rec[f"plant_doy_{irr}"] = _circ_mean(x[f"planting_day_{irr}"], x.w)
                rec[f"maturity_doy_{irr}"] = _circ_mean(x[f"maturity_day_{irr}"], x.w)
                gl = x[f"growing_season_length_{irr}"]
                rec[f"season_length_{irr}"] = float((gl * x.w).sum() / x.w[gl.notna()].sum()) if gl.notna().any() \
                    else np.nan
            rows.append(rec)
    cal = pd.DataFrame(rows)
    cm = crops[["crop_code", "crop_name", "ggcmi_crop", "ggcmi_proxy", "season_type"]]
    out = cm.merge(cal, on="ggcmi_crop", how="left")
    ref = pd.Timestamp("2001-01-01")
    for k in ("plant", "maturity"):
        d = out[f"{k}_doy_rf"]
        out[f"{k}_mmdd"] = [(ref + pd.Timedelta(days=x - 1)).strftime("%m-%d") if pd.notna(x) else None for x in d]
        out[f"{k}_month"] = [int((ref + pd.Timedelta(days=x - 1)).month) if pd.notna(x) else None for x in d]
    out["plant_month"] = out.plant_month.astype("Int64")
    out["maturity_month"] = out.maturity_month.astype("Int64")
    # посев в прошлом году (озимые): день посева позже дня созревания
    out["sown_previous_year"] = out.plant_doy_rf > out.maturity_doy_rf
    out = out.sort_values(["okato", "crop_code"]).reset_index(drop=True)
    save(out, "crop_calendar", cfg)
    write_stats("calendar", {"rows": len(out), "crops": out.crop_code.nunique(), "ggcmi": sorted(cal.ggcmi_crop.unique()),
                             "nan_plant_rf": int(out.plant_doy_rf.isna().sum()),
                             "points_neighbor": int(cal.n_points_neighbor.sum())})
