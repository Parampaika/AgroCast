"""Погода: почасовые ERA5 / ERA5-Land → сутки по точкам → признаки «регион × сезон».

Шаг 1 (кэш, тяжёлый): data/clean/_cache/weather/point_daily.parquet.
  Логика суточной агрегации и FAO-56 ET0 — из src/data/build_weather_daily.py (импорт функций):
  сутки по местному солнечному времени, неполные сутки (< 20 ч) — NaN, ERA5-Land основной источник
  температуры и влажности почвы, ERA5 — осадков, радиации, ветра; ERA5 — запасной для ячеек над морем.
Шаг 2: месячные агрегаты по точкам → средневзвешенно (доля пашни) по региону.
  data/clean/weather_region_month.parquet — длинная таблица okato × год × месяц;
  data/clean/weather_region_season.parquet — широкая «регион × сезон» + аномалии к норме.

Сезон Y: сентябрь Y−1 … октябрь Y. Колонки `<переменная>_<тег>`, тег p09…p12 — осень прошлого года,
01…10 — месяцы года урожая. Норма — среднее по сезонам clim_start_year…train_end_year (защита от утечки).
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from preprocess.common import CACHE, RAW, SRC_DATA, Config, log, points, save, weighted_mean, write_stats

WCACHE = CACHE / "weather"
ERA = RAW / "era5_om"

MEAN_VARS = ["tmean", "tmax", "tmin", "tdew", "rad", "wind", "vpd", "sm0_7", "sm7_28", "sm28_100", "snow_depth"]
SUM_VARS = ["prec", "snowfall", "et0", "cwb", "gdd5", "gdd10", "hot30", "hot35", "frost0", "frost2", "dry_days",
            "prec_act", "t_act"]
MIN_VARS = ["tmin_abs", "tsoil_min"]
MAX_VARS = ["tmax_abs"]
SEASON_TAGS = [f"p{m:02d}" for m in range(9, 13)] + [f"{m:02d}" for m in range(1, 11)]
MIN_DAYS = 25  # месяц с меньшим числом суток — NaN (например, незавершённый октябрь 2026)


# ---------- шаг 1: сутки по точкам ----------

def _bwd():
    if str(SRC_DATA) not in sys.path:
        sys.path.insert(0, str(SRC_DATA))
    import build_weather_daily as bwd  # noqa: PLC0415
    return bwd


def build_daily(cfg: Config) -> None:
    out = WCACHE / "point_daily.parquet"
    if out.exists() and not cfg.force:
        log("погода: point_daily в кэше")
        return
    bwd = _bwd()
    cell_dir = WCACHE / "cell_daily"
    cell_dir.mkdir(parents=True, exist_ok=True)
    for (model, var), aggs in bwd.SPEC.items():
        names = {a: cell_dir / f"{model}__{var}__{a}.parquet" for a in aggs}
        if all(p.exists() for p in names.values()) and not cfg.force:
            continue
        res = bwd.daily(model, var, aggs)
        for a, v in res.items():
            v.to_parquet(names[a])
        log("сутки по ячейкам:", model, var, aggs, res[aggs[0]].shape)

    pts = points()
    cl = {m: pd.read_csv(ERA / m / "cells.csv").set_index("point_id").cell
          for m in ("copernicus_era5", "copernicus_era5_land")}
    stat = pd.read_csv(ERA / "copernicus_era5" / "static_cells.csv").set_index("cell").HSURF

    def pt(model, var, agg):
        w = pd.read_parquet(cell_dir / f"{model}__{var}__{agg}.parquet")
        cols = cl[model].reindex(pts.point_id)
        o = w.reindex(columns=cols.values)
        o.columns = pts.point_id.values
        return o

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
    et0, vpd = bwd.et0_fao56(V["tmax"].values, V["tmin"].values, V["tdew"].values, V["rad"].values,
                             V["wind"].values, lat, doy, z)
    V["et0"] = pd.DataFrame(et0, index=idx, columns=V["tmax"].columns).astype("float32")
    V["vpd"] = pd.DataFrame(vpd, index=idx, columns=V["tmax"].columns).astype("float32")
    long = pd.concat({k: v.stack(future_stack=True) for k, v in V.items()}, axis=1).astype("float32")
    long.index.names = ["date", "point_id"]
    long = long.reset_index()
    long.to_parquet(out, index=False)
    log("погода: point_daily", long.shape, long.date.min().date(), long.date.max().date())


# ---------- шаг 2: месяцы и сезоны ----------

def _daily_derived(d: pd.DataFrame) -> pd.DataFrame:
    d["cwb"] = d.prec - d.et0
    d["gdd5"] = (d.tmean - 5).clip(lower=0)
    d["gdd10"] = (d.tmean - 10).clip(lower=0)
    d["hot30"] = (d.tmax > 30).astype("float32").where(d.tmax.notna())
    d["hot35"] = (d.tmax > 35).astype("float32").where(d.tmax.notna())
    d["frost0"] = (d.tmin < 0).astype("float32").where(d.tmin.notna())
    d["frost2"] = (d.tmin < -2).astype("float32").where(d.tmin.notna())
    d["dry_days"] = (d.prec < 1).astype("float32").where(d.prec.notna())
    act = d.tmean > 10  # «активные» сутки для ГТК Селянинова
    d["t_act"] = d.tmean.where(act, 0).where(d.tmean.notna())
    d["prec_act"] = d.prec.where(act, 0).where(d.prec.notna())
    d["tmin_abs"], d["tmax_abs"] = d.tmin, d.tmax
    return d


def _max_run(flag: pd.Series, keys: list[pd.Series]) -> pd.Series:
    """Максимальная длина серии подряд идущих True внутри групп keys (данные отсортированы по дате)."""
    f = flag.fillna(0).astype(bool)
    brk = (~f).astype(int)
    for k in keys:
        brk = brk + (k != k.shift()).astype(int)
    run_id = brk.cumsum()
    runs = f.groupby(run_id).transform("sum")
    return runs.where(f, 0).groupby(keys).max()


def monthly_points(d: pd.DataFrame) -> pd.DataFrame:
    d = d.sort_values(["point_id", "date"]).reset_index(drop=True)
    d = _daily_derived(d)
    d["year"], d["month"] = d.date.dt.year.astype("int16"), d.date.dt.month.astype("int8")
    keys = ["point_id", "year", "month"]
    g = d.groupby(keys)
    m = pd.concat([g[MEAN_VARS].mean(), g[SUM_VARS].sum(min_count=1), g[MIN_VARS].min(), g[MAX_VARS].max(),
                   g.size().rename("n_days")], axis=1)
    m["dry_spell"] = _max_run(d.dry_days, [d.point_id, d.year, d.month])
    m = m.reset_index()
    full = m.n_days >= MIN_DAYS
    vals = [c for c in m.columns if c not in keys + ["n_days"]]
    m.loc[~full, vals] = np.nan
    # сезонная засушливая серия апрель–август и зимние признаки — тоже на уровне точки
    gs = d[d.month.between(4, 8)]
    dry48 = _max_run(gs.dry_days, [gs.point_id, gs.year]).rename("dry_spell_4_8")
    n48 = gs.groupby(["point_id", "year"]).size()
    dry48 = dry48.where(n48 >= 150)
    w = d[d.month.isin([12, 1, 2, 3])].copy()
    w["season"] = np.where(w.month == 12, w.year + 1, w.year)
    gw = w.groupby(["point_id", "season"])
    win = pd.DataFrame({
        "tsoil_min_win": gw.tsoil_min.min(),
        "cold20_win": gw.tmin.apply(lambda s: (s < -20).sum()),
        "snow_win": gw.snow_depth.mean(),
        "thaw_win": w[w.month.isin([1, 2])].groupby(["point_id", "season"]).tmax.apply(lambda s: (s > 3).sum()),
        "n": gw.size(),
    })
    win = win[win.n >= 110].drop(columns="n")
    return m, dry48.reset_index(), win.reset_index()


def build(cfg: Config) -> None:
    build_daily(cfg)
    pts = points()
    d = pd.read_parquet(WCACHE / "point_daily.parquet")
    last_date = d.date.max()
    mp, dry48, win = monthly_points(d)
    del d
    wcol = pts.set_index("point_id")[["okato", "w"]]
    mp = mp.join(wcol, on="point_id")
    vals = [c for c in mp.columns if c not in ("point_id", "year", "month", "okato", "w", "n_days")]
    m = weighted_mean(mp, ["okato", "year", "month"], vals)
    npts = mp.dropna(subset=["tmean"]).groupby(["okato", "year", "month"]).size().rename("n_points")
    m = m.merge(npts.reset_index(), on=["okato", "year", "month"], how="left")
    # ГТК Селянинова = 10·ΣP / Σt за сутки с t > 10 °C; при Σt < 100 °C (холодный месяц) не определён
    m["htc"] = (10 * m.prec_act / m.t_act).where(m.t_act >= 100)
    m = m.sort_values(["okato", "year", "month"])
    float_cols = m.select_dtypes("float").columns
    m[float_cols] = m[float_cols].astype("float32")
    save(m, "weather_region_month", cfg)

    # ----- широкая таблица «регион × сезон» -----
    mm = m.copy()
    cur = mm[mm.month <= 10].assign(season=mm.year, tag=mm.month.map(lambda x: f"{x:02d}"))
    prev = mm[mm.month >= 9].assign(season=mm.year + 1, tag=mm.month.map(lambda x: f"p{x:02d}"))
    both = pd.concat([cur, prev])
    mvars = [c for c in m.columns if c not in ("okato", "year", "month", "n_points")]
    wide = both.pivot_table(index=["okato", "season"], columns="tag", values=mvars, dropna=False)
    wide.columns = [f"{v}_{t}" for v, t in wide.columns]
    order = [f"{v}_{t}" for v in mvars for t in SEASON_TAGS if f"{v}_{t}" in wide.columns]
    wide = wide[order]

    # сезонные агрегаты (сумма/среднее по месяцам; NaN, если месяц не полон)
    def ssum(v, months):
        cols = [f"{v}_{x:02d}" for x in months]
        return wide[cols].sum(axis=1, min_count=len(cols))

    def smean(v, months):
        cols = [f"{v}_{x:02d}" for x in months]
        return wide[cols].mean(axis=1).where(wide[cols].notna().all(axis=1))

    s = pd.DataFrame(index=wide.index)
    s["gdd5_4_9"], s["gdd10_4_9"] = ssum("gdd5", range(4, 10)), ssum("gdd10", range(4, 10))
    s["prec_4_8"], s["et0_4_8"], s["cwb_4_8"] = ssum("prec", range(4, 9)), ssum("et0", range(4, 9)), \
        ssum("cwb", range(4, 9))
    s["prec_p09_03"] = wide[[f"prec_p{x:02d}" for x in range(9, 13)] + [f"prec_{x:02d}" for x in range(1, 4)]] \
        .sum(axis=1, min_count=7)
    s["tmean_4_8"] = smean("tmean", range(4, 9))
    s["hot30_5_8"], s["hot35_5_8"] = ssum("hot30", range(5, 9)), ssum("hot35", range(5, 9))
    s["frost0_4_5"], s["frost0_9_10"] = ssum("frost0", [4, 5]), ssum("frost0", [9, 10])
    s["htc_5_8"] = 10 * ssum("prec_act", range(5, 9)) / ssum("t_act", range(5, 9))
    dry = dry48.join(wcol, on="point_id").rename(columns={"year": "season"})
    s = s.join(weighted_mean(dry, ["okato", "season"], ["dry_spell_4_8"]).set_index(["okato", "season"]))
    wn = win.join(wcol, on="point_id")
    wcols = ["tsoil_min_win", "cold20_win", "snow_win", "thaw_win"]
    s = s.join(weighted_mean(wn, ["okato", "season"], wcols).set_index(["okato", "season"]))
    wide = wide.join(s)
    wide.index.names = ["okato", "year"]
    wide = wide.reset_index()

    # полнота сезона и обрезка: первый полный сезон — 2001 (данные с 2000-01-01)
    wide = wide[wide.year >= 2001]
    wide["season_complete"] = wide[[f"tmean_{t}" for t in SEASON_TAGS]].notna().all(axis=1)
    wide["weather_last_date"] = last_date

    feats = [c for c in wide.columns if c not in ("okato", "year", "season_complete", "weather_last_date")]
    norm_mask = wide.year.between(cfg.clim_start_year, cfg.train_end_year)
    norm = wide[norm_mask].groupby("okato")[feats].mean()
    anom = wide[feats] - norm.reindex(wide.okato).values
    anom.columns = [f"a_{c}" for c in feats]
    # климат региона (признаки «где»): годовые нормы по тем же годам
    clim = pd.DataFrame({
        "clim_tmean": norm[[f"tmean_{x:02d}" for x in range(1, 11)]].mean(axis=1),
        "clim_prec_4_8": norm["prec_4_8"], "clim_et0_4_8": norm["et0_4_8"], "clim_gdd5_4_9": norm["gdd5_4_9"],
        "clim_htc_5_8": norm["htc_5_8"],
    })
    wide = pd.concat([wide.reset_index(drop=True), anom.reset_index(drop=True)], axis=1)
    wide = wide.merge(clim, left_on="okato", right_index=True, how="left")
    wide["norm_years"] = f"{cfg.clim_start_year}-{cfg.train_end_year}"
    fc = wide.select_dtypes("float").columns
    wide[fc] = wide[fc].astype("float32")
    save(wide, "weather_region_season", cfg)
    write_stats("weather", {
        "last_date": last_date, "regions": wide.okato.nunique(), "seasons": [int(wide.year.min()), int(wide.year.max())],
        "features_raw": len(feats), "complete_seasons": int(wide.season_complete.sum()),
        "incomplete_seasons": wide.loc[~wide.season_complete, "year"].value_counts().to_dict(),
        "nan_share_feats": float(wide[feats].isna().mean().mean()),
    })
