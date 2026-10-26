"""Справочник субъектов РФ: data/clean/regions.parquet (89 строк, ключ okato).

Каноничный ключ `okato` — код из data/raw/geo/regions.csv (тот же, что у точек пашни, погоды и почв).
Особые случаи:
- Тюменская обл.: каноничный код 71001000000 («без ХМАО и ЯНАО», так устроены геометрия и точки);
  в ЕМИСС ряд «без АО» идёт с 2007 г., а «с АО» (71000000000) — с 2000 г. → `okato_with_ao`.
- Архангельская обл.: каноничный код 11000000000 («с НАО», ряд ЕМИСС с 2000 г.), полигон и точки — без НАО;
  ряд «без НАО» (11001000000) — `okato_without_ao`. НАО — отдельная строка 11100000000.
- Крым и Севастополь — данные ЕМИСС с 2014 г.; ДНР, ЛНР, Запорожская и Херсонская обл. — в урожайности нет.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from preprocess.common import Config, emiss, points, regions_raw, save, write_stats

MACRO = {"ЦФО": "Центр", "СЗФО": "Север и Северо-Запад", "ЮФО": "Юг", "СКФО": "Юг", "ПФО": "Поволжье",
         "УФО": "Урал и Сибирь", "СФО": "Урал и Сибирь", "ДФО": "Дальний Восток"}
NEW_SUBJECTS = {"21000000000", "43000000000", "23000000000", "39000000000"}
CRIMEA = {"35000000000", "67000000000"}
CITIES = {"45000000000", "40000000000", "67000000000"}
AO = {"11100000000", "71100000000", "71140000000", "77000000000"}
WITH_AO = {"71001000000": "71000000000", "11000000000": "11000000000"}
WITHOUT_AO = {"71001000000": "71001000000", "11000000000": "11001000000"}


def build(cfg: Config) -> pd.DataFrame:
    r = regions_raw().rename(columns={"gb_name": "geo_name", "gb_source": "geo_source"})
    r["macro_region"] = r.fo.map(MACRO)
    r["is_new_subject"] = r.okato.isin(NEW_SUBJECTS)
    r["crimea_from_2014"] = r.okato.isin(CRIMEA)
    r["is_city"] = r.okato.isin(CITIES)
    r["is_autonomous_okrug"] = r.okato.isin(AO)
    r["okato_with_ao"] = r.okato.map(WITH_AO)
    r["okato_without_ao"] = r.okato.map(WITHOUT_AO)
    r["ao_split"] = r.okato.isin(WITH_AO)
    r["geometry_excludes_ao"] = r.okato.isin(WITH_AO)

    # первый и последний год урожайности 31533 (все категории, любой культуры) — по коду, из которого берётся ряд
    y = emiss("31533")
    y = y[y.value.notna() & (y.farm_category_code == "1")]
    span = y.groupby("okato").year.agg(["min", "max"])
    src = r.okato.where(~r.okato.isin(WITH_AO), r.okato_with_ao)
    r["yield_first_year"] = src.map(span["min"]).astype("Int64")
    r["yield_last_year"] = src.map(span["max"]).astype("Int64")
    r["has_yield_data"] = r.yield_first_year.notna()

    # пашня по WorldCover 2021: оценка площади из отбора точек, центроид — среднее точек с весом доли пашни
    p = points()
    agg = p.groupby("okato").agg(cropland_km2_worldcover=("region_crop_km2_est", "first"),
                                 n_points=("point_id", "size"),
                                 n_points_fallback=("method", lambda s: int((s == "fallback_south").sum())))
    pw = p.assign(wlat=p.lat * p.w, wlon=p.lon * p.w).groupby("okato")[["wlat", "wlon", "w"]].sum()
    agg["cropland_centroid_lat"] = (pw.wlat / pw.w).round(4)
    agg["cropland_centroid_lon"] = (pw.wlon / pw.w).round(4)
    r = r.merge(agg, left_on="okato", right_index=True, how="left")
    r["cropland_from_worldcover"] = r.n_points_fallback < r.n_points
    r.loc[~r.cropland_from_worldcover, "cropland_km2_worldcover"] = np.nan  # fallback: пашни в WorldCover нет
    r = r.sort_values("okato").reset_index(drop=True)
    save(r, "regions", cfg)
    write_stats("regions", {"n": len(r), "with_yield": int(r.has_yield_data.sum()),
                            "no_yield": r.loc[~r.has_yield_data, "name_emiss"].tolist()})
    return r
