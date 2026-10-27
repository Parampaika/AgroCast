"""MODIS LAI/FPAR (MOD15A2H), LST (MOD11A2), GPP (MOD17A2H): 8-дневные композиты по точкам пашни → регион.

Выход:
- data/clean/modis_extra_region.parquet — длинная таблица okato × var × date (var: lai, fpar, lst_day, lst_night,
  lst_diff, gpp);
- data/clean/modis_extra_region_year.parquet — годовые признаки okato × year, колонки с префиксом переменной.

Вход: data/raw/modis_<lai|lst|gpp>/<тайл>/<ГГГГДДД>_r1.csv (точки rank_in_region ≤ 1 — 1–2 на регион, апрель–октябрь).
Качество и шкалы (логика как у NDVI, но со своими QC):
- LAI, FPAR — центральный пиксель (QC относится к нему); годны значения ≤ 100 (249–255 — не растительность/заполнитель)
  при SCF_QC (биты 5–7 FparLai_QC) = 0 или 1 — основной алгоритм. LAI × 0.1 (м²/м²), FPAR × 0.01 (доля).
- LST — mean3x3 при ≥ 5 годных пикселях, иначе центр; 0 — заполнитель. День: биты 0–1 QC_Day = 0 или 1 (LST получена);
  для ночи QC в выгрузке нет — только проверка заполнителя. °C = raw × 0.02 − 273.15, годны −60…+75 °C.
  lst_diff = день − ночь в той же точке и композите.
- GPP — mean3x3 при ≥ 5 годных пикселях, иначе центр; годны 0…3000 (32761–32767 — заполнители; > 3000, т. е.
  > 300 г C/м² за 8 суток, для пашни невозможно). QC в выгрузке нет. г C/м² за 8 суток = raw × 0.1.
  Скачано только 2021–2026 гг.: нормы (≤ train_end_year) нет, аномалий GPP нет.
Регион — среднее по точкам с весом доли пашни. В регионах с одной точкой оценка шумнее (`n_points`).
Годовые признаки — по композитам апреля–октября; аномалии `<var>_a*` — к норме региона по годам ≤ train_end_year
(считаются, только если в норме ≥ 5 лет).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from preprocess.common import CACHE, RAW, Config, log, points, save, write_stats

PRODUCTS = {"lai": ["Lai_500m", "Fpar_500m", "FparLai_QC"], "lst": ["LST_Day_1km", "LST_Night_1km", "QC_Day"],
            "gpp": ["Gpp_500m"]}
VARS = ["lai", "fpar", "lst_day", "lst_night", "lst_diff", "gpp"]
MONTHS = range(4, 11)
MIN_NORM_YEARS = 5


def _read_product(prod: str, cfg: Config) -> pd.DataFrame:
    out = CACHE / "modis" / f"{prod}.parquet"
    tiles = sorted(d for d in (RAW / f"modis_{prod}").iterdir() if d.is_dir())
    files = [f for t in tiles for f in t.glob("*.csv") if not f.name.startswith("_")]
    if out.exists() and not cfg.force and out.stat().st_mtime > max(f.stat().st_mtime for f in files):
        return pd.read_parquet(out)
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    # дубли сцен в STAC: при повторе берём строку с бóльшим числом годных пикселей
    df = df.sort_values("n_valid3x3").drop_duplicates(["point_id", "date", "band"], keep="last")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    log(f"MODIS {prod}: {len(files)} файлов, {len(df):,} строк")
    return df


def _wide(df: pd.DataFrame, col: str) -> pd.DataFrame:
    return df.pivot_table(index=["point_id", "date"], columns="band", values=col, aggfunc="first")


def point_values(cfg: Config) -> pd.DataFrame:
    parts = []
    lai = _read_product("lai", cfg)
    c = _wide(lai, "center")
    scf = (c["FparLai_QC"].fillna(255).to_numpy().astype(np.int64) >> 5) & 7
    good = pd.Series(np.isin(scf, [0, 1]), index=c.index)
    parts.append(pd.DataFrame({"lai": (c["Lai_500m"] * 0.1).where(good & (c["Lai_500m"] <= 100)),
                               "fpar": (c["Fpar_500m"] * 0.01).where(good & (c["Fpar_500m"] <= 100))}))

    lst = _read_product("lst", cfg)
    c, m, n = _wide(lst, "center"), _wide(lst, "mean3x3"), _wide(lst, "n_valid3x3")

    def lst_c(band):
        v = m[band].where(n[band] >= 5, c[band])
        v = v.where(v > 0) * 0.02 - 273.15
        return v.where(v.between(-60, 75))

    qc_ok = pd.Series(np.isin(c["QC_Day"].fillna(3).to_numpy().astype(np.int64) & 3, [0, 1]), index=c.index)
    day, night = lst_c("LST_Day_1km").where(qc_ok), lst_c("LST_Night_1km")
    parts.append(pd.DataFrame({"lst_day": day, "lst_night": night, "lst_diff": day - night}))

    gpp = _read_product("gpp", cfg)
    c, m, n = _wide(gpp, "center"), _wide(gpp, "mean3x3"), _wide(gpp, "n_valid3x3")
    v = m["Gpp_500m"].where(n["Gpp_500m"] >= 5, c["Gpp_500m"])
    # формально годны 0…30000, но > 3000 (300 г C/м² за 8 суток, ~37 г/сут) для пашни физически невозможно
    parts.append(pd.DataFrame({"gpp": (v * 0.1).where(v.between(0, 3000))}))

    pv = pd.concat(parts, axis=1).reset_index()
    pv["date"] = pd.to_datetime(pv.date)
    return pv


def build(cfg: Config) -> None:
    pv = point_values(cfg)
    pts = points().set_index("point_id")
    pv = pv.join(pts[["okato", "w"]], on="point_id", how="inner")
    long = pv.melt(id_vars=["point_id", "date", "okato", "w"], value_vars=VARS, var_name="var", value_name="v")
    # точка «существует» для переменной, если у неё есть строка продукта (LST и LAI скачаны по одним и тем же точкам)
    long["valid"] = long.v.notna()
    long["wv"] = long.v * long.w
    long["w_ok"] = long.w.where(long.valid, 0)
    g = long.groupby(["okato", "var", "date"])
    r = pd.DataFrame({"value": g.wv.sum(min_count=1) / g.w_ok.sum().replace(0, np.nan),
                      "n_points": g.size(), "n_points_valid": g.valid.sum(),
                      "valid_weight_share": g.w_ok.sum() / g.w.sum()}).reset_index()
    prod_dates = {"lai": "lai", "fpar": "lai", "lst_day": "lst", "lst_night": "lst", "lst_diff": "lst", "gpp": "gpp"}
    r = r[r.groupby(["var", "date"]).n_points_valid.transform("sum") > 0]  # даты, которых у продукта нет
    r["year"] = r.date.dt.year.astype("int16")
    r["doy"] = r.date.dt.dayofyear.astype("int16")
    r["period"] = ((r.doy - 1) // 8 + 1).astype("int8")
    r["product"] = r["var"].map(prod_dates)
    r["value"] = r.value.astype("float32")
    r = r[["okato", "var", "product", "year", "period", "doy", "date", "value", "n_points", "n_points_valid",
           "valid_weight_share"]].sort_values(["okato", "var", "date"]).reset_index(drop=True)
    save(r, "modis_extra_region", cfg)

    # ---- годовые признаки (апрель–октябрь) ----
    s = r[r.date.dt.month.isin(MONTHS)].copy()
    s["month"] = s.date.dt.month
    rows = []
    for (ok, var, y), x in s.groupby(["okato", "var", "year"], sort=False):
        x = x.sort_values("doy")
        v = x.value.to_numpy(float)
        nv = int(np.isfinite(v).sum())
        rec = {"okato": ok, "var": var, "year": y, "n_periods": len(x), "n_valid": nv}
        if nv:
            i = int(np.nanargmax(v))
            rec.update(max=float(v[i]), mean=float(np.nanmean(v)), peak_doy=int(x.doy.values[i]))
            if nv >= 0.6 * len(x) and len(x) >= 20:
                vi = pd.Series(v, index=x.doy.values).interpolate(method="index", limit_direction="both")
                rec["integral"] = float(np.trapezoid(vi.values, vi.index.values))
                if var == "gpp":  # 8-дневные суммы → сезонная сумма, г C/м²
                    rec["integral"] /= 8
        rows.append(rec)
    yr = pd.DataFrame(rows)
    mon = s.pivot_table(index=["okato", "var", "year"], columns="month", values="value", aggfunc="mean")
    mon.columns = [f"{m:02d}" for m in mon.columns]
    yr = yr.merge(mon.reset_index(), on=["okato", "var", "year"], how="left")
    feats = ["max", "mean", "integral", "peak_doy"] + [f"{m:02d}" for m in MONTHS]
    for f in feats:
        if f not in yr:
            yr[f] = np.nan
    # аномалии к норме региона по годам ≤ train_end_year (не меньше MIN_NORM_YEARS лет)
    tr = yr[yr.year <= cfg.train_end_year]
    norm = tr.groupby(["okato", "var"])[feats].mean()
    nyears = tr.groupby(["okato", "var"])[feats].count()
    norm = norm.where(nyears >= MIN_NORM_YEARS)
    idx = pd.MultiIndex.from_frame(yr[["okato", "var"]])
    anom = yr[feats].to_numpy(float) - norm.reindex(idx).to_numpy(float)
    yr[[f"a{f}" for f in feats]] = anom
    wide = yr.pivot_table(index=["okato", "year"], columns="var",
                          values=feats + [f"a{f}" for f in feats] + ["n_valid"], dropna=False)
    wide.columns = [f"{v}_{f}" for f, v in wide.columns]
    order = [f"{v}_{f}" for v in VARS for f in ["n_valid"] + feats + [f"a{x}" for x in feats]
             if f"{v}_{f}" in wide.columns]
    wide = wide[order].reset_index()
    wide = wide.dropna(axis=1, how="all")
    npts = pv.groupby("okato").point_id.nunique()
    wide["modis_n_points"] = wide.okato.map(npts).astype("int16")
    wide["year"] = wide.year.astype("int16")
    fc = wide.select_dtypes("float").columns
    wide[fc] = wide[fc].astype("float32")
    save(wide, "modis_extra_region_year", cfg)
    write_stats("modis_extra", {
        "points": int(pv.point_id.nunique()), "regions": int(r.okato.nunique()),
        "regions_one_point": int((npts == 1).sum()),
        "years_by_var": {v: [int(x.year.min()), int(x.year.max())] for v, x in r[r.n_points_valid > 0].groupby("var")},
        "valid_share_by_var": long.groupby("var").valid.mean().round(3).to_dict(),
        "norm_years_by_var": tr.groupby("var").year.agg(lambda s: f"{s.min()}-{s.max()}").to_dict(),
        "anomaly_available_share": {v: float(wide[f"{v}_amean"].notna().mean()) if f"{v}_amean" in wide else 0.0
                                    for v in VARS},
    })
