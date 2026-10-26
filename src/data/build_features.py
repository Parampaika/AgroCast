"""Признаки «регион × сезон» из погоды, NDVI и почв.

Запуск (после build_weather_daily.py и build_ndvi.py):
    uv run python -I -X utf8 src/data/build_features.py

Сезон Y = месяцы сентябрь–декабрь года Y−1 (префикс p: `prec_p09`) и январь–сентябрь года Y (`prec_05`).
Месячные признаки по каждой переменной (`<var>_<мм>`):
  tmean, tmax, tmin, prec, et0, cwb (prec − et0), rad, vpd, sm0_7, sm7_28, sm28_100 — средние/суммы;
  hot30 / hot35 — число дней с tmax > 30 / 35 °C; gdd5 — сумма (tmean − 5)+; frost — дни с tmin < −2 °C.
Зима (декабрь Y−1 – март Y): tsoil_min_win, cold20_win (дни tmin < −20), snow_win (средняя высота снега, м),
  thaw_win (дни tmax > 3 °C в январе–феврале).
NDVI: среднее за месяц (`ndvi_<мм>`, апрель–сентябрь) и максимум за май–август.
Почвы: средние по точкам региона, 0–30 см (clay, sand, soc, phh2o, nitrogen, cec, bdod) и ocs.
Климат региона: средние за 2000–2021 годовые T, P, ET0 (признаки «где», а не «какой год»).

Аномалии (`a_<признак>`) = значение − среднее региона за сезоны 2001–2021 (для 2026 сезон не завершён).
Выход: data/processed/features/region_season.parquet (okato, year, …).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import PROC_ROOT, ROOT  # noqa: E402

OUT = PROC_ROOT / "features"
OUT.mkdir(parents=True, exist_ok=True)
CLIM_YEARS = range(2001, 2022)

MEAN_VARS = ["tmean", "tmax", "tmin", "rad", "vpd", "sm0_7", "sm7_28", "sm28_100"]
SUM_VARS = ["prec", "et0", "cwb", "hot30", "hot35", "gdd5", "frost"]


def monthly(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["cwb"] = d.prec - d.et0
    d["hot30"] = (d.tmax > 30).astype(float)
    d["hot35"] = (d.tmax > 35).astype(float)
    d["gdd5"] = (d.tmean - 5).clip(lower=0)
    d["frost"] = (d.tmin < -2).astype(float)
    d["ym"] = d.date.dt.to_period("M")
    agg = {v: "mean" for v in MEAN_VARS} | {v: "sum" for v in SUM_VARS}
    m = d.groupby(["okato", "ym"]).agg(agg)
    m["ndays"] = d.groupby(["okato", "ym"]).size()
    m = m[m.ndays >= 25].drop(columns="ndays").reset_index()
    m["year"], m["month"] = m.ym.dt.year, m.ym.dt.month
    return m


def season_wide(m: pd.DataFrame) -> pd.DataFrame:
    cur = m[m.month <= 9].copy()
    cur["season"], cur["tag"] = cur.year, cur.month.map(lambda x: f"{x:02d}")
    prev = m[m.month >= 9].copy()
    prev["season"], prev["tag"] = prev.year + 1, prev.month.map(lambda x: f"p{x:02d}")
    both = pd.concat([cur, prev])
    vals = MEAN_VARS + SUM_VARS
    w = both.pivot_table(index=["okato", "season"], columns="tag", values=vals)
    w.columns = [f"{v}_{t}" for v, t in w.columns]
    return w


def winter(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["season"] = np.where(d.date.dt.month == 12, d.date.dt.year + 1, d.date.dt.year)
    d = d[d.date.dt.month.isin([12, 1, 2, 3])]
    g = d.groupby(["okato", "season"])
    w = pd.DataFrame({
        "tsoil_min_win": g.tsoil_min.min(),
        "cold20_win": g.tmin.apply(lambda s: (s < -20).sum()),
        "snow_win": g.snow_depth.mean(),
        "thaw_win": d[d.date.dt.month.isin([1, 2])].groupby(["okato", "season"]).tmax.apply(lambda s: (s > 3).sum()),
        "n_win": g.size(),
    })
    return w[w.n_win >= 110].drop(columns="n_win")


def ndvi_feats() -> pd.DataFrame:
    n = pd.read_parquet(PROC_ROOT / "ndvi" / "region_ndvi.parquet")
    n["season"], n["month"] = n.date.dt.year, n.date.dt.month
    n = n[n.month.between(4, 9)]
    w = n.pivot_table(index=["okato", "season"], columns="month", values="ndvi", aggfunc="mean")
    w.columns = [f"ndvi_{c:02d}" for c in w.columns]
    w["ndvi_max_5_8"] = n[n.month.between(5, 8)].groupby(["okato", "season"]).ndvi.max()
    return w


def soils() -> pd.DataFrame:
    s = pd.read_csv(ROOT / "data" / "raw" / "soilgrids" / "soilgrids_points.csv")
    s = s[(s.stat == "mean") & (s.value_raw != -32768)]
    pts = pd.read_csv(ROOT / "data" / "raw" / "geo" / "points.csv", dtype={"okato": str})
    s = s.merge(pts[["point_id", "okato"]], on="point_id")
    top = s[s.depth.isin(["0-5cm", "5-15cm", "15-30cm"])]
    thick = {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15}
    top = top.assign(w=top.depth.map(thick))
    top = top.assign(vw=top.value_raw * top.w)
    a = top.groupby(["okato", "property"]).apply(lambda g: g.vw.sum() / g.w.sum(), include_groups=False).unstack()
    a = a[["clay", "sand", "soc", "phh2o", "nitrogen", "cec", "bdod"]]
    a.columns = [f"soil_{c}" for c in a.columns]
    a["soil_ocs"] = s[s.property == "ocs"].groupby("okato").value_raw.mean()
    return a


def main():
    d = pd.read_parquet(PROC_ROOT / "weather" / "region_daily.parquet")
    m = monthly(d)
    w = season_wide(m).join(winter(d), how="left").join(ndvi_feats(), how="left")
    w.index.names = ["okato", "year"]
    w = w.reset_index()
    w = w[w.year.between(2001, 2026)]

    feats = [c for c in w.columns if c not in ("okato", "year")]
    clim = w[w.year.isin(CLIM_YEARS)].groupby("okato")[feats].mean()
    anom = w[feats] - clim.reindex(w.okato).values
    anom.columns = [f"a_{c}" for c in feats]
    w = pd.concat([w, anom], axis=1)

    # климат региона: годовые нормы
    d["year"] = d.date.dt.year
    yr = d[d.year.isin(CLIM_YEARS)].groupby(["okato", "year"]).agg(t=("tmean", "mean"), p=("prec", "sum"),
                                                                   e=("et0", "sum"))
    cl = yr.groupby("okato").mean().rename(columns={"t": "clim_t", "p": "clim_p", "e": "clim_et0"})
    w = w.merge(cl, left_on="okato", right_index=True, how="left")
    w = w.merge(soils(), left_on="okato", right_index=True, how="left")
    w.to_parquet(OUT / "region_season.parquet", index=False)
    last = d.date.max()
    print("признаков", w.shape[1] - 2, "строк", len(w), "регионов", w.okato.nunique(), "сезоны", w.year.min(),
          w.year.max(), "| последняя дата погоды", last.date())
    print("пропуски в a_* за 2025:", round(w[w.year == 2025].filter(like="a_").isna().mean().mean(), 3),
          "за 2026:", round(w[w.year == 2026].filter(like="a_").isna().mean().mean(), 3))


if __name__ == "__main__":
    main()
