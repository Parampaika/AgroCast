"""Таблица для моделирования: data/clean/model_table.parquet («субъект × культура × год», без обучения моделей).

Состав:
- цель и контекст из yield_panel (уровень субъектов, категория `--category`, по умолчанию «все категории»);
- тренд-признаки `tr_*` — только по годам < t (скользящие, до t−1): лаги, средние, линейные тренды
  по всем прошлым годам и по последним 10; ряд для трендов — `yield_t_ha` (после чистки) и досчитанные
  из компонентов значения того же года, но НЕ интерполированные (интерполяция берёт значение t+1);
- погода: сезонные агрегаты, климат и аномалии к норме `a_*` из weather_region_season (норма — годы ≤ train_end_year);
- погода в окне культуры `win_*` (от месяца посева до месяца созревания по GGCMI) и их аномалии `a_win_*`;
  отдельно, на все годы и все пары «регион × культура» с календарём, — data/clean/weather_crop_window.parquet;
- почвы `soil_*`, NDVI за год `ndvi_*` (данные текущего сезона — доступны только по ходу сезона), календарь `cal_*`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from preprocess.common import CLEAN, Config, load, log, save, write_stats

TAGS = [f"p{m:02d}" for m in range(9, 13)] + [f"{m:02d}" for m in range(1, 11)]
WIN_SUM = ["prec", "et0", "cwb", "gdd5", "gdd10", "hot30", "hot35", "frost0", "prec_act", "t_act"]
WIN_MEAN = ["tmean", "tmax", "sm28_100", "sm7_28"]


def _ols_pred(x: np.ndarray, y: np.ndarray, t: float) -> float:
    xm, ym = x.mean(), y.mean()
    sxx = ((x - xm) ** 2).sum()
    if sxx == 0:
        return float(ym)
    b = ((x - xm) * (y - ym)).sum() / sxx
    return float(ym + b * (t - xm))


def trend_features(p: pd.DataFrame) -> pd.DataFrame:
    """Для каждой строки (ряд × год t) — признаки только по годам < t."""
    out = []
    for _, g in p.groupby(["okato", "crop_code"], sort=False):
        g = g.sort_values("year")
        yrs = g.year.to_numpy(float)
        y = g.y_hist.to_numpy(float)
        ok = np.isfinite(y)
        rows = np.full((len(g), 10), np.nan)
        for i, t in enumerate(yrs):
            m = ok & (yrs < t)
            xs, ys = yrs[m], y[m]
            if len(xs):
                rows[i, 0] = ys[-1] if xs[-1] == t - 1 else np.nan               # lag1
                rows[i, 1] = ys[xs == t - 2][0] if (xs == t - 2).any() else np.nan  # lag2
                w3, w5 = ys[xs >= t - 3], ys[xs >= t - 5]
                rows[i, 2] = w3.mean() if len(w3) >= 2 else np.nan
                rows[i, 3] = w5.mean() if len(w5) >= 3 else np.nan
                rows[i, 4] = len(xs)
                if len(xs) >= 5:
                    rows[i, 5] = _ols_pred(xs, ys, t)
                m10 = xs >= t - 10
                rows[i, 6] = m10.sum()
                if m10.sum() >= 5:
                    rows[i, 7] = _ols_pred(xs[m10], ys[m10], t)
                rows[i, 8] = xs[-1]
                rows[i, 9] = np.median(ys[-10:])
        out.append(pd.DataFrame(rows, index=g.index, columns=[
            "tr_lag1", "tr_lag2", "tr_mean3", "tr_mean5", "tr_n_past", "tr_lin_all", "tr_n_10", "tr_lin10",
            "tr_last_year", "tr_median10"]))
    f = pd.concat(out)
    f["tr_n_past"] = f.tr_n_past.fillna(0).astype("int16")
    f["tr_n_10"] = f.tr_n_10.fillna(0).astype("int16")
    f["tr_last_year"] = f.tr_last_year.astype("Int16")
    return f


def window_features(cal: pd.DataFrame, w: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Погода в окне «посев → созревание» культуры (месяцы сезона Y; для озимых — с осени Y−1)."""
    recs = []
    wk = w.set_index(["okato", "year"])
    for _, c in cal.dropna(subset=["plant_month", "maturity_month"]).iterrows():
        pm, mm = int(c.plant_month), int(c.maturity_month)
        if c.sown_previous_year:
            tags = [f"p{m:02d}" for m in range(max(pm, 9), 13)] + [f"{m:02d}" for m in range(1, mm + 1)]
        else:
            tags = [f"{m:02d}" for m in range(pm, min(mm, 10) + 1)]
        if c.okato not in wk.index.get_level_values(0):
            continue
        x = wk.loc[c.okato]
        r = pd.DataFrame(index=x.index)
        for v in WIN_SUM:
            cols = [f"{v}_{t}" for t in tags]
            r[f"win_{v}"] = x[cols].sum(axis=1, min_count=len(cols))
        for v in WIN_MEAN:
            cols = [f"{v}_{t}" for t in tags]
            r[f"win_{v}"] = x[cols].mean(axis=1).where(x[cols].notna().all(axis=1))
        r["win_htc"] = 10 * r.win_prec_act / r.win_t_act
        r = r.drop(columns=["win_prec_act", "win_t_act"])
        r["win_months"] = len(tags)
        r["okato"], r["crop_code"] = c.okato, c.crop_code
        recs.append(r.reset_index())
    win = pd.concat(recs, ignore_index=True)
    feats = [c for c in win.columns if c.startswith("win_") and c != "win_months"]
    tr = win[win.year.between(cfg.clim_start_year, cfg.train_end_year)]
    norm = tr.groupby(["okato", "crop_code"])[feats].mean()
    a = win[feats].values - norm.reindex(pd.MultiIndex.from_frame(win[["okato", "crop_code"]])).values
    win[[f"a_{c}" for c in feats]] = a
    return win


def build(cfg: Config) -> None:
    p = load("yield_panel")
    p = p[(p.region_level == "subject") & (p.farm_category_code == cfg.category)].copy()
    if cfg.crops:
        p = p[p.crop_code.isin(cfg.crops)]
    # строки, где есть хоть что-то о культуре в регионе (урожайность, площадь или сбор)
    p = p[p.value_raw.notna() | p.area_kha.notna() | p.gross_tc.notna() | p.flag_confidential].copy()
    p["y_hist"] = p.yield_filled_t_ha.where(p.fill_method.isin(["observed", "derived_components"]))
    log(f"model_table: трендовые признаки по {p.groupby(['okato', 'crop_code']).ngroups} рядам")
    p = p.join(trend_features(p))
    p["target_dev_tr_lin10"] = p.yield_t_ha / p.tr_lin10 - 1
    p["area_lag1"] = p.sort_values("year").groupby(["okato", "crop_code"]).area_kha.shift()
    keep = ["okato", "region", "fo", "crop_code", "crop_name", "crop_group", "is_main", "farm_category_code", "year",
            "yield_t_ha", "yield_filled_t_ha", "fill_method", "yield_calc_t_ha", "harvest_share", "area_kha",
            "area_lag1", "gross_kt", "flag_confidential", "flag_outlier_hi", "flag_outlier_lo", "flag_calc_mismatch",
            "run_len", "series_max_run", "y_hist"]
    m = p[keep + [c for c in p.columns if c.startswith(("tr_", "target_"))]].copy()

    w = load("weather_region_season")
    a_cols = [c for c in w.columns if c.startswith("a_")]
    seas = ["gdd5_4_9", "gdd10_4_9", "prec_4_8", "et0_4_8", "cwb_4_8", "prec_p09_03", "tmean_4_8", "hot30_5_8",
            "hot35_5_8", "frost0_4_5", "frost0_9_10", "htc_5_8", "dry_spell_4_8", "tsoil_min_win", "cold20_win",
            "snow_win", "thaw_win"]
    clim = [c for c in w.columns if c.startswith("clim_")]
    m = m.merge(w[["okato", "year", "season_complete"] + seas + clim + a_cols]
                .rename(columns={"season_complete": "weather_season_complete"}), on=["okato", "year"], how="left")

    cal = load("crop_calendar")
    win = window_features(cal, w, cfg)
    save(win.sort_values(["okato", "crop_code", "year"]).reset_index(drop=True), "weather_crop_window", cfg)
    m = m.merge(win, on=["okato", "crop_code", "year"], how="left")
    c2 = cal[["okato", "crop_code", "plant_doy_rf", "maturity_doy_rf", "season_length_rf", "sown_previous_year",
              "ggcmi_proxy"]]
    c2.columns = ["okato", "crop_code"] + [f"cal_{c}" for c in c2.columns[2:]]
    m = m.merge(c2, on=["okato", "crop_code"], how="left")

    s = load("soil_region")
    sc = [c for c in s.columns if c not in ("okato", "n_points")]
    m = m.merge(s[["okato"] + sc].rename(columns={c: f"soil_{c}" for c in sc}), on="okato", how="left")
    if (CLEAN / "ndvi_region_year.parquet").exists():
        n = load("ndvi_region_year")
        nc = [c for c in n.columns if c.startswith("ndvi_") and c != "ndvi_peak_date"]
        m = m.merge(n[["okato", "year"] + nc], on=["okato", "year"], how="left")
    m["train_end_year"] = cfg.train_end_year
    m["is_train_year"] = m.year <= cfg.train_end_year
    fc = m.select_dtypes("float64").columns
    m[fc] = m[fc].astype("float32")
    m = m.sort_values(["crop_code", "okato", "year"]).reset_index(drop=True)
    save(m, "model_table", cfg)
    write_stats("model_table", {
        "rows": len(m), "cols": m.shape[1], "category": cfg.category, "train_end_year": cfg.train_end_year,
        "rows_with_target": int(m.yield_t_ha.notna().sum()),
        "rows_main_with_target": int((m.yield_t_ha.notna() & m.is_main).sum()),
        "share_weather_present": float(m.a_tmean_06.notna().mean()) if "a_tmean_06" in m else None,
        "share_ndvi_present": float(m.ndvi_max.notna().mean()) if "ndvi_max" in m else None,
        "share_tr_lin10": float(m.tr_lin10.notna().mean()),
    })
