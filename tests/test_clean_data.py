"""Проверки чистого слоя data/clean/ (запуск: uv run pytest -q tests/test_clean_data.py).

Таблицы собираются заранее: uv run python -I -X utf8 src/preprocess/build_all.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

CLEAN = Path(__file__).resolve().parents[1] / "data" / "clean"
TRAIN_END = 2021
MAIN = {"1010400": "Пшеница озимая", "1010500": "Пшеница яровая", "1030100": "Ячмень яровой",
        "3080000": "Подсолнечник", "1080202": "Кукуруза на зерно", "3100000": "Соя"}
# медиана урожайности по субъектам (т/га, все категории) должна попадать в агрономически разумный коридор
MEDIAN_BAND = {"1010400": (1.5, 4.5), "1010500": (1.0, 3.0), "1030100": (1.2, 3.0), "3080000": (0.8, 2.0),
               "1080202": (2.0, 6.0), "3100000": (0.7, 2.0), "3060100": (20, 55), "4010000": (10, 25)}
# минимум субъектов с рядом ≥ 15 лет подряд (reports/eda_emiss.md, раздел 2)
MIN_RUN15 = {"1010400": 55, "1010500": 60, "1030100": 65, "3080000": 35, "1080202": 30, "3100000": 30}

KEYS = {
    "regions": ["okato"], "crops": ["crop_code"],
    "yield_panel": ["okato", "crop_code", "farm_category_code", "year"],
    "yield_operational": ["measure", "okato", "crop_code", "farm_category_code", "year", "period"],
    "weather_region_month": ["okato", "year", "month"], "weather_region_season": ["okato", "year"],
    "soil_region": ["okato"], "ndvi_region": ["okato", "date"], "ndvi_region_year": ["okato", "year"],
    "crop_calendar": ["okato", "crop_code"], "prices": ["okato", "product_id", "year"],
    "prices_crop_map": ["product_id", "crop_code"],
    "economics_aux": ["indicator_id", "okato", "item_code", "farm_category_code", "year"],
    "model_table": ["okato", "crop_code", "year"],
    "modis_extra_region": ["okato", "var", "date"], "modis_extra_region_year": ["okato", "year"], "weather_crop_window": ["okato", "crop_code", "year"],
}


def load(name: str) -> pd.DataFrame:
    p = CLEAN / f"{name}.parquet"
    if not p.exists():
        pytest.skip(f"нет {p.name}: сначала build_all.py")
    return pd.read_parquet(p)


@pytest.fixture(scope="module")
def panel():
    return load("yield_panel")


@pytest.fixture(scope="module")
def crops():
    return load("crops")


@pytest.fixture(scope="module")
def regions():
    return load("regions")


# ---------- ключи ----------

@pytest.mark.parametrize("name", list(KEYS))
def test_keys_unique_and_not_null(name):
    df = load(name)
    k = KEYS[name]
    assert len(df) > 0
    assert not df.duplicated(k).any(), f"{name}: дубли ключа {k}"
    for c in k:
        if c != "item_code":  # у показателей без разреза (энергомощности, себестоимость) позиции нет
            assert df[c].notna().all(), f"{name}: пустой {c}"


# ---------- справочники ----------

def test_regions(regions):
    assert len(regions) == 89
    assert regions.okato.str.fullmatch(r"\d{11}").all()
    assert regions.fo.notna().all() and regions.macro_region.notna().all()
    assert regions.is_new_subject.sum() == 4 and not regions[regions.is_new_subject].has_yield_data.any()
    assert set(regions[regions.crimea_from_2014].yield_first_year) == {2014}
    assert regions.has_yield_data.sum() >= 82
    assert regions.cropland_centroid_lat.between(41, 72).all()
    assert regions.cropland_centroid_lon.between(19, 180).all()


def test_crops(crops):
    assert set(MAIN) <= set(crops[crops.is_main].crop_code)
    assert crops.is_main.sum() == len(MAIN)
    assert crops.loc[crops.crop_code == "3080102", "base_crop_code"].item() == "3080000"
    assert crops.loc[crops.crop_code == "3080100", "area_alias_of"].item() == "3080000"
    assert crops.loc[crops.crop_code == "1010401", "components"].item() == "1010400,1010500"
    assert crops.loc[crops.crop_code == "1010400", "season_type"].item() == "озимая"
    assert crops.loc[crops.crop_code == "1010500", "season_type"].item() == "яровая"
    assert crops.group.notna().all()


# ---------- урожайность ----------

def test_yield_positive_and_plausible(panel, crops):
    y = panel.yield_t_ha.dropna()
    assert (y > 0).all()
    maxp = panel.crop_code.map(crops.set_index("crop_code").max_plausible_t_ha)
    assert (panel.yield_t_ha.isna() | (panel.yield_t_ha <= maxp)).all()
    assert np.allclose(panel.yield_t_ha.dropna(), panel.value_clean.dropna() / 10)


def test_yield_median_by_crop(panel):
    s = panel[(panel.region_level == "subject") & (panel.farm_category_code == "1")]
    for code, (lo, hi) in MEDIAN_BAND.items():
        med = s[s.crop_code == code].yield_t_ha.median()
        assert lo <= med <= hi, f"{code}: медиана {med:.2f} т/га вне [{lo}, {hi}]"


def test_cleaning_rules_applied(panel):
    bad = panel.flag_confidential | panel.flag_zero | panel.flag_negative | panel.flag_implausible \
        | (panel.flag_outlier_hi & ~panel.outlier_confirmed_by_calc)
    assert panel.loc[bad, "value_clean"].isna().all()
    # значения не удаляются: исходник сохраняется для всех, кроме скрытых (999999999 → NaN)
    assert panel.loc[panel.flag_zero, "value_raw"].eq(0).all()
    assert panel.loc[panel.flag_confidential, "value_raw"].isna().all()
    # заполненные — только интерполяция/компоненты, а наблюдения не изменены
    obs = panel.fill_method == "observed"
    assert np.allclose(panel.loc[obs, "yield_filled_t_ha"], panel.loc[obs, "yield_t_ha"])
    assert panel.loc[panel.is_interpolated, "yield_t_ha"].isna().all()


def test_shares_in_range(panel):
    h = panel.harvest_share.dropna()
    assert (h > 0).all()
    assert ((h >= 0.5) & (h <= 1.05)).mean() > 0.9  # согласованность урожайности, сбора и площади
    assert (panel.run_len <= panel.series_max_run).all()
    assert (panel.series_max_run <= panel.series_n_years).all()


def test_rf_series_continuous(panel):
    rf = panel[(panel.okato == "643") & (panel.farm_category_code == "1")]
    for code in MAIN:
        yrs = set(rf[(rf.crop_code == code) & rf.value_clean.notna()].year)
        assert set(range(2000, 2025)) <= yrs, f"РФ {code}: пропуски {set(range(2000, 2025)) - yrs}"


def test_coverage_main_crops(panel):
    s = panel[(panel.region_level == "subject") & (panel.farm_category_code == "1")]
    for code, n in MIN_RUN15.items():
        got = s[(s.crop_code == code) & (s.series_max_run >= 15)].okato.nunique()
        assert got >= n, f"{MAIN[code]}: рядов ≥15 лет {got} < {n}"
    assert s[s.value_clean.notna()].okato.nunique() >= 80


def test_operational():
    o = load("yield_operational")
    assert set(o.year) >= {2023, 2024, 2025, 2026}
    y = o[o.measure == "yield_oper_c_ha"].value_t_ha.dropna()
    assert (y >= 0).all() and y.median() < 60
    assert o[o.measure == "yield_oper_c_ha"].final_crop_code.notna().all()


# ---------- погода и утечка ----------

@pytest.fixture(scope="module")
def weather():
    return load("weather_region_season")


def test_weather_coverage_and_ranges(weather, regions):
    assert set(weather.okato) == set(regions.okato)
    w = weather[weather.season_complete]
    assert w.year.min() == 2001 and w.year.max() >= 2025
    assert w.tmean_07.between(5, 35).all()
    assert (w.prec_4_8 >= 0).all() and (w.gdd5_4_9 >= 0).all()
    assert w.hot30_07.between(0, 31).all() and w.dry_spell_4_8.between(0, 153).all()
    assert w.htc_5_8.dropna().between(0, 10).all()
    for c in ("sm0_7_05", "sm28_100_05"):
        assert w[c].between(0, 1).all()


@pytest.mark.parametrize("col", ["tmean_07", "prec_4_8", "htc_5_8", "sm28_100_03", "gdd5_4_9"])
def test_weather_norm_uses_train_years_only(weather, col):
    w = weather.copy()
    norm_implied = (w[col] - w[f"a_{col}"]).groupby(w.okato).agg(["min", "max"])
    assert (norm_implied["max"] - norm_implied["min"]).abs().max() < 1e-3, "норма должна быть константой региона"
    train = w[w.year.between(2001, TRAIN_END)].groupby("okato")[col].mean()
    assert np.allclose(norm_implied["min"].reindex(train.index), train, atol=1e-3)
    # аномалии в обучающих годах в среднем нулевые, а будущие годы на норму не влияют
    assert w[w.year.between(2001, TRAIN_END)].groupby("okato")[f"a_{col}"].mean().abs().max() < 1e-3


@pytest.fixture(scope="module")
def mt():
    return load("model_table")


def test_model_table_scope(mt):
    assert (mt.farm_category_code == "1").all()
    assert set(MAIN) <= set(mt.crop_code)
    assert (mt.train_end_year == TRAIN_END).all()


def test_trend_no_leakage(mt):
    """Тренд-признаки пересчитываются независимо только по годам < t и совпадают с таблицей."""
    m = mt[mt.crop_code.isin(MAIN)]
    sample = m[m.tr_lin10.notna()].sample(300, random_state=1)
    for _, r in sample.iterrows():
        h = m[(m.okato == r.okato) & (m.crop_code == r.crop_code) & (m.year < r.year) & m.y_hist.notna()]
        h10 = h[h.year >= r.year - 10]
        b, a = np.polyfit(h10.year, h10.y_hist, 1)
        assert abs(b * r.year + a - r.tr_lin10) < 1e-3
        h5 = h[h.year >= r.year - 5]
        if len(h5) >= 3:
            assert abs(h5.y_hist.mean() - r.tr_mean5) < 1e-3
        else:
            assert np.isnan(r.tr_mean5)
        if (h.year == r.year - 1).any():
            assert abs(h[h.year == r.year - 1].y_hist.item() - r.tr_lag1) < 1e-4


def test_window_norm_train_only():
    w = load("weather_crop_window")
    for col in ("win_prec", "win_gdd5", "win_htc"):
        norm = (w[col] - w[f"a_{col}"]).groupby([w.okato, w.crop_code]).agg(["min", "max"]).dropna()
        assert ((norm["max"] - norm["min"]).abs() < 1e-2).all()
        tr = w[w.year.between(2001, TRAIN_END)].groupby(["okato", "crop_code"])[f"a_{col}"].mean()
        assert tr.abs().max() < 1e-2


# ---------- остальные таблицы ----------

def test_soil(regions):
    s = load("soil_region")
    assert set(s.okato) == set(regions.okato)
    tex = s.clay_0_30 + s.sand_0_30 + s.silt_0_30
    assert tex.between(95, 105).all()
    assert s.phh2o_0_30.between(3.5, 9.5).all() and s.bdod_0_30.between(0.5, 2).all()
    assert s.wrb_dominant_share.between(0, 1).all() and s.wrb_dominant.notna().all()


def test_ndvi(regions):
    n = load("ndvi_region")
    assert set(n.okato) == set(regions.okato)
    assert n.ndvi.dropna().between(-0.2, 1).all()
    assert n.valid_weight_share.between(0, 1).all()
    y = load("ndvi_region_year")
    assert y.ndvi_max.dropna().between(0, 1).all()
    assert y.ndvi_peak_doy.dropna().between(97, 273).all()
    summer = n[n.date.dt.month.isin([6, 7])].ndvi.dropna()
    assert 0.4 < summer.median() < 0.9


def test_calendar(regions):
    c = load("crop_calendar")
    main = c[c.crop_code.isin(MAIN)]
    assert set(main.okato) == set(regions.okato)
    assert main.plant_doy_rf.between(1, 366).all() and main.maturity_doy_rf.between(1, 366).all()
    ww = main[main.crop_code == "1010400"]
    assert ww.sown_previous_year.mean() > 0.9  # озимая пшеница сеется осенью прошлого года
    sp = main[main.crop_code == "1010500"]
    assert sp.plant_month.between(3, 6).all()


def test_prices():
    p = load("prices")
    assert (p.price > 0).all() and (p.price_real > 0).all()
    assert p.price_source.isin(["region", "fo", "rf"]).all()
    base = p[p.year == 2021].deflator
    assert np.allclose(base, 1.0)
    for pid in ("wheat", "barley", "sunflower", "maize", "soy", "potato"):
        x = p[(p.product_id == pid) & (p.okato != "643") & p.year.between(1999, 2025)]
        assert x.groupby("year").okato.nunique().min() >= 85, pid
    rf = p[(p.okato == "643") & (p.product_id == "wheat")].set_index("year").price
    assert 2000 < rf.loc[2010] < 10000 and 8000 < rf.loc[2021] < 20000  # руб./т
    cm = load("prices_crop_map")
    assert set(MAIN) <= set(cm.crop_code)


def test_economics():
    e = load("economics_aux")
    assert {30964, 31632, 42380}.issubset(set(e.indicator_id))
    assert (e.loc[e.indicator_id == 42380, "coverage"] == "rf_only").all()
    f = e[(e.indicator_id == 30964) & (e.region_level == "subject")].value.dropna()
    assert (f >= 0).all() and f.median() < 500  # кг д. в. на 1 га


# ---------- MODIS LAI/FPAR, LST, GPP и рельеф ----------

MODIS_RANGES = {"lai": (0, 10), "fpar": (0, 1), "lst_day": (-60, 75), "lst_night": (-60, 75), "lst_diff": (-40, 50),
                "gpp": (0, 300)}


def test_modis_region(regions):
    r = load("modis_extra_region")
    assert set(r["var"]) == set(MODIS_RANGES)
    for v, (lo, hi) in MODIS_RANGES.items():
        x = r[r["var"] == v].value.dropna()
        assert x.between(lo, hi).all(), v
    assert r.valid_weight_share.between(0, 1).all()
    assert set(r.okato) == set(regions.okato)
    jul = r[r.date.dt.month == 7].groupby("var").value.median()
    assert 0.3 < jul["fpar"] < 0.8 and 15 < jul["lst_day"] < 40 and jul["lst_diff"] > 0 and 20 < jul["gpp"] < 120


def test_modis_year_columns():
    y = load("modis_extra_region_year")
    for v in ("lai", "fpar", "lst_day", "lst_night", "lst_diff", "gpp"):
        for c in ("max", "mean", "integral", "peak_doy", "04", "07", "10"):
            assert f"{v}_{c}" in y.columns, f"{v}_{c}"
    for v in ("lai", "fpar", "lst_day", "lst_night", "lst_diff"):
        assert f"{v}_a07" in y.columns and f"{v}_amean" in y.columns
    assert y.modis_n_points.between(1, 2).all()
    assert y.lai_peak_doy.dropna().between(91, 305).all()


@pytest.mark.parametrize("col", ["lai_mean", "fpar_07", "lst_day_07", "lst_night_mean", "lst_diff_06"])
def test_modis_norm_uses_train_years_only(col):
    y = load("modis_extra_region_year")
    v, f = col.rsplit("_", 1)
    a = f"{v}_a{f}"
    implied = (y[col] - y[a]).groupby(y.okato).agg(["min", "max"]).dropna()
    assert ((implied["max"] - implied["min"]).abs() < 1e-3).all(), "норма должна быть константой региона"
    tr = y[y.year <= TRAIN_END].groupby("okato")
    assert np.allclose(implied["min"], tr[col].mean().reindex(implied.index), atol=1e-3)
    assert tr[a].mean().abs().max() < 1e-3


def test_gpp_no_norm_without_train_years():
    y = load("modis_extra_region_year")
    assert y.loc[y.year <= TRAIN_END, "gpp_mean"].notna().groupby(y.okato).sum().max() < 5
    assert "gpp_amean" not in y.columns or y.gpp_amean.isna().all()


def test_elevation(regions):
    s = load("soil_region")
    assert s.elev_mean.between(-30, 2500).all() and s.elev_mean.notna().all()
    assert (s.elev_min <= s.elev_mean + 1e-3).all() and (s.elev_mean <= s.elev_max + 1e-3).all()
    ast = s.set_index("okato").elev_mean
    assert ast["12000000000"] < 0 and ast["90000000000"] > 300  # Прикаспий ниже уровня моря, Осетия — предгорья


def test_model_table_new_blocks(mt):
    for pref in ("lai_", "fpar_", "lst_day_", "lst_night_", "lst_diff_", "gpp_", "elev_"):
        assert any(c.startswith(pref) for c in mt.columns), pref
    assert {"lai_07", "lai_a07", "lst_day_06", "elev_mean", "modis_n_points"} <= set(mt.columns)
    assert mt[mt.year >= 2001].lai_07.notna().mean() > 0.8
