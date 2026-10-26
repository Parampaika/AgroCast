"""NDVI MODIS MOD13Q1 v061: data/clean/ndvi_region.parquet (регион × год × 16-дневный композит)
и data/clean/ndvi_region_year.parquet (годовые признаки).

Вход: data/raw/modis_ndvi/<тайл>/<год><день>{_r2,_r3-99,}.csv — по строке на точку и слой (NDVI, pixel_reliability),
значения центрального пикселя и среднего окна 3×3 (~750 м). Логика из src/data/build_ndvi.py, расширена на все
450 точек (файлы _r3-99 докачаны):
- NDVI = mean3x3 / 10000, если в окне ≥ 5 годных пикселей, иначе центр / 10000;
- годны только композиты с pixel_reliability центра 0 (good) или 1 (marginal); 2 — снег, 3 — облака, −1 — нет;
- значения вне [−0.2, 1] отбрасываются.
Регион — среднее по точкам с весом доли пашни. Годовые признаки — по композитам апреля–сентября.
LST и GPP MODIS в каталоге не описаны и докачаны частично (LST) или не скачаны (GPP) — не включены.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from preprocess.common import CACHE, RAW, Config, log, points, save, write_stats

SEASON_DOY = (97, 273)  # композиты, начинающиеся 7 апреля … 30 сентября


def _read_tile(tile_dir) -> pd.DataFrame:
    out = CACHE / "ndvi" / f"{tile_dir.name}.parquet"
    files = [f for f in tile_dir.glob("*.csv") if not f.name.startswith("_")]
    if out.exists() and out.stat().st_mtime > max(f.stat().st_mtime for f in files):
        return pd.read_parquet(out)
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df = df.drop_duplicates(["point_id", "date", "band"], keep="last")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return df


def point_ndvi(cfg: Config) -> pd.DataFrame:
    tiles = sorted(d for d in (RAW / "modis_ndvi").iterdir() if d.is_dir())
    parts = []
    for t in tiles:
        if cfg.force:
            (CACHE / "ndvi" / f"{t.name}.parquet").unlink(missing_ok=True)
        parts.append(_read_tile(t))
    df = pd.concat(parts, ignore_index=True).drop_duplicates(["point_id", "date", "band"], keep="last")
    nd = df[df.band == "NDVI"].drop(columns="band")
    rel = df[df.band == "pixel_reliability"][["point_id", "date", "center"]].rename(columns={"center": "rel"})
    nd = nd.merge(rel, on=["point_id", "date"], how="left")
    raw = nd.mean3x3.where(nd.n_valid3x3 >= 5, nd.center) / 10000
    nd["valid"] = nd.rel.isin([0, 1]) & raw.between(-0.2, 1)
    nd["ndvi"] = raw.where(nd.valid)
    nd["date"] = pd.to_datetime(nd.date)
    log(f"NDVI: точек {nd.point_id.nunique()}, композитов {nd.date.nunique()}, доля годных {nd.valid.mean():.3f}")
    return nd[["point_id", "date", "ndvi", "rel", "valid"]]


def build(cfg: Config) -> None:
    nd = point_ndvi(cfg)
    pts = points().set_index("point_id")
    nd = nd.join(pts[["okato", "w"]], on="point_id", how="inner")
    nd["wv"] = nd.ndvi * nd.w
    nd["w_ok"] = nd.w.where(nd.valid, 0)
    nd["good"] = (nd.rel == 0) & nd.valid
    g = nd.groupby(["okato", "date"])
    r = pd.DataFrame({
        "ndvi": g.wv.sum(min_count=1) / g.w_ok.sum().replace(0, np.nan),
        "n_points": g.size(), "n_points_valid": g.valid.sum(), "n_points_good": g.good.sum(),
        "valid_weight_share": g.w_ok.sum() / g.w.sum(),
    }).reset_index()
    r["year"] = r.date.dt.year.astype("int16")
    r["doy"] = r.date.dt.dayofyear.astype("int16")
    r["period"] = ((r.doy - 1) // 16 + 1).astype("int8")
    r["ndvi"] = r.ndvi.astype("float32")
    r = r[["okato", "year", "period", "doy", "date", "ndvi", "n_points", "n_points_valid", "n_points_good",
           "valid_weight_share"]].sort_values(["okato", "date"]).reset_index(drop=True)
    save(r, "ndvi_region", cfg)

    # ---- годовые признаки ----
    s = r[r.doy.between(*SEASON_DOY)]
    rows = []
    for (ok, y), x in s.groupby(["okato", "year"]):
        x = x.sort_values("doy")
        v = x.ndvi.values
        n_valid = int(np.isfinite(v).sum())
        rec = {"okato": ok, "year": y, "n_periods": len(x), "n_valid_periods": n_valid}
        if n_valid:
            i = int(np.nanargmax(v))
            m58 = x.date.dt.month.between(5, 8).values
            rec.update(ndvi_max=float(v[i]), ndvi_peak_doy=int(x.doy.values[i]), ndvi_peak_date=x.date.values[i],
                       ndvi_mean_5_8=float(np.nanmean(v[m58])) if np.isfinite(v[m58]).any() else np.nan)
        full = len(x) >= 11 and n_valid >= 0.6 * len(x)
        if full:
            vi = pd.Series(v, index=x.doy.values).interpolate(method="index", limit_direction="both")
            rec["ndvi_integral"] = float(np.trapezoid(vi.values, vi.index.values))  # NDVI·сутки
            rec["ndvi_integral_interp_share"] = round(1 - n_valid / len(x), 3)
        rows.append(rec)
    yr = pd.DataFrame(rows)
    mon = s.assign(month=s.date.dt.month).pivot_table(index=["okato", "year"], columns="month", values="ndvi",
                                                       aggfunc="mean")
    mon.columns = [f"ndvi_{m:02d}" for m in mon.columns]
    yr = yr.merge(mon.reset_index(), on=["okato", "year"], how="left")
    yr["season_complete"] = yr.n_periods >= 11
    fc = yr.select_dtypes("float").columns
    yr[fc] = yr[fc].astype("float32")
    save(yr, "ndvi_region_year", cfg)
    write_stats("ndvi", {
        "points": int(nd.point_id.nunique()), "regions": int(r.okato.nunique()), "dates": int(r.date.nunique()),
        "first": r.date.min(), "last": r.date.max(), "valid_share_points": float(nd.valid.mean()),
        "valid_share_by_month": nd.assign(m=nd.date.dt.month).groupby("m").valid.mean().round(3).to_dict(),
        "rel_counts": nd.rel.value_counts().to_dict(),
        "integral_available_share": float(yr.ndvi_integral.notna().mean()),
        "lst": "не включён: в каталоге нет, data/raw/modis_lst докачан частично",
        "gpp": "не включён: data/raw/modis_gpp пуст",
    })
