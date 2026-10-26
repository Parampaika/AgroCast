"""Панель урожайности «регион × культура × год × категория хозяйств» и оперативные данные.

Вход: ЕМИСС 31533 (урожайность, ц/га на убранную площадь), 31328 (посевная площадь, тыс. га),
30950 (валовой сбор, тыс. ц); оперативные 33978, 34165, 33784 (2023–2026).
Выход: data/clean/yield_panel.parquet, data/clean/yield_operational.parquet.

Ничего не удаляется: исходное значение — `value_raw` (ц/га), правила чистки — флаги `flag_*`,
результат правил — `value_clean` (ц/га) и `yield_t_ha`; `yield_filled_t_ha` дополнительно закрывает
одиночные пропуски (линейно) и досчитывает «всего» из компонентов (озимая + яровая) по площадям.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from preprocess.common import CAT_ALL, RF, Config, emiss, fo_map, load, regions_raw, save, write_stats

YEAR_MIN = 2000
OUTLIER_K = 3.0          # «больше чем в 3 раза от медианы ряда» (reports/eda_emiss.md, п. 3, 7)
H_LOW, H_HIGH = 0.5, 1.05  # допустимая доля убранной площади h = сбор / (урожайность × посевная)
KEY = ["okato", "crop_code", "farm_category_code", "year"]

# оперативные ряды → код культуры итоговой урожайности; смещение «на 1 ноября» против итогов 31533 (СХО),
# медиана (опер./итог − 1) за 2023–2024 из reports/eda_emiss.md, п. 3
OPER_TO_FINAL = {"1070102": "1000001", "3060500": "3060100", "3080100": "3080000", "3080000": "3080000",
                 "4010000": "4010000", "4020301": "4020301", "1000001": "1000001", "4020300": "4020300"}
OPER_BIAS_PCT = {"1070102": -3.2, "3060500": -7.0, "3080100": -1.5, "3080000": -1.5, "4010000": 0.2}
PERIOD_DATE = {"на 1 июля": "07-01", "на 1 августа": "08-01", "на 1 сентября": "09-01",
               "на 1 октября": "10-01", "на 1 ноября": "11-01"}


def harmonize_regions(d: pd.DataFrame) -> pd.DataFrame:
    """Приводит территории ЕМИСС к каноничным кодам: 89 субъектов (regions.csv), ФО и РФ.

    РФ: код 643 до 2022 г., с 2023 г. — 643004.АГ («без новых субъектов»), склеены в «643».
    Тюменская обл. (71001…): ряд «без АО»; лет/культур, которых в нём нет (до 2007 г.), — из ряда «с АО»
    (71000…), флаг `okato_src` показывает исходный код.
    """
    canon = set(regions_raw().okato)
    d = d.copy()
    d["okato_src"] = d["okato"]
    rf = d[d.okato.isin(["643", "643004.АГ"])].copy()
    # приоритет: 643 до 2022 г., 643004.АГ с 2023 г.; если нужного кода в году нет — второй
    rf["_prio"] = np.where((rf.okato == "643") == (rf.year <= 2022), 0, 1)
    rf["okato"], rf["region_level"] = RF, "rf"
    dims = [c for c in rf.columns if c.endswith("_code")] + ["okato", "year", "period"]
    rf = rf.sort_values("_prio").drop_duplicates([c for c in dims if c in rf.columns]).drop(columns="_prio")
    fo = d[d.region_level == "fo"].copy()
    subj = d[d.okato.isin(canon)].copy()
    subj["region_level"] = "subject"
    tyu = d[d.okato == "71000000000"].copy()
    tyu["okato"], tyu["region_level"] = "71001000000", "subject"
    keycols = [c for c in d.columns if c not in ("okato_src", "value", "confidential", "region", "region_level", "fo",
                                                 "alt_codelist", "dup_conflict", "value_t_ha", "unit", "period")
               and not c.startswith("attr_")]
    have = subj[subj.okato == "71001000000"][keycols].drop_duplicates()
    tyu = tyu.merge(have, on=keycols, how="left", indicator=True)
    tyu = tyu[tyu._merge == "left_only"].drop(columns="_merge")
    out = pd.concat([subj, tyu, fo, rf], ignore_index=True)
    out["fo"] = out.okato.map(fo_map())
    return out


def _series_stats(df: pd.DataFrame, col: str, by: list[str]) -> pd.DataFrame:
    """Длина непрерывного ряда (подряд идущие годы с непустым col), число лет и максимальный отрезок в ряду."""
    df = df.sort_values(by + ["year"])
    ok = df[col].notna()
    g = df.groupby(by, sort=False)
    brk = ((~ok) | (g.year.diff() != 1)).fillna(True).astype(bool)
    block = brk.cumsum()
    run = ok.groupby(block).transform("sum")
    df["run_len"] = run.where(ok, 0).astype("int16")
    df["series_n_years"] = ok.groupby([df[b] for b in by]).transform("sum").astype("int16")
    df["series_max_run"] = df.groupby(by).run_len.transform("max").astype("int16")
    return df


def build_panel(cfg: Config) -> pd.DataFrame:
    crops = load("crops")
    y = harmonize_regions(emiss("31533"))
    a = harmonize_regions(emiss("31328"))
    g = harmonize_regions(emiss("30950"))
    yield_codes = set(crops.loc[crops.has_yield, "crop_code"])

    y = y[y.year >= YEAR_MIN].rename(columns={"value": "value_raw", "confidential": "flag_confidential"})
    y = y[KEY + ["okato_src", "region_level", "fo", "value_raw", "flag_confidential", "farm_category"]]
    g = g[(g.year >= YEAR_MIN) & g.crop_code.isin(yield_codes)]
    g = g.rename(columns={"value": "gross_tc", "confidential": "gross_confidential", "okato_src": "okato_src_gross"})
    g = g[KEY + ["gross_tc", "gross_confidential", "okato_src_gross", "region_level", "fo", "farm_category"]]
    p = y.merge(g, on=KEY, how="outer", suffixes=("", "_g"))
    for c in ("region_level", "fo", "farm_category"):
        p[c] = p[c].fillna(p[f"{c}_g"])
    p = p.drop(columns=[c for c in p.columns if c.endswith("_g")])
    p["okato_src"] = p.okato_src.fillna(p.okato_src_gross)
    p = p.drop(columns="okato_src_gross")
    p["flag_confidential"] = p.flag_confidential.fillna(False).astype(bool)
    p["gross_confidential"] = p.gross_confidential.fillna(False).astype(bool)

    # посевная площадь: код площади культуры (для «после доработки» — основная), плюс алиасы кодов 31328
    a = a[a.year >= YEAR_MIN]
    alias = crops.dropna(subset=["area_alias_of"]).set_index("crop_code").area_alias_of
    a_main = a[~a.crop_code.isin(alias.index)]
    a_alias = a[a.crop_code.isin(alias.index)].assign(crop_code=lambda x: x.crop_code.map(alias))
    a_alias = a_alias.merge(a_main[["okato", "crop_code", "farm_category_code", "year"]], how="left", indicator=True,
                            on=["okato", "crop_code", "farm_category_code", "year"])
    a_alias = a_alias[a_alias._merge == "left_only"].drop(columns="_merge").assign(area_from_alias=True)
    a = pd.concat([a_main.assign(area_from_alias=False), a_alias])
    a = a.rename(columns={"crop_code": "area_code", "value": "area_kha", "confidential": "area_confidential"})
    a = a[["okato", "area_code", "farm_category_code", "year", "area_kha", "area_confidential", "area_from_alias"]]
    a = a.drop_duplicates(["okato", "area_code", "farm_category_code", "year"])
    p["area_code"] = p.crop_code.map(crops.set_index("crop_code").area_code)
    p = p.merge(a, on=["okato", "area_code", "farm_category_code", "year"], how="left")
    p["area_confidential"] = p.area_confidential.fillna(False).astype(bool)
    p["area_from_alias"] = p.area_from_alias.fillna(False).astype(bool)

    # ---- флаги по урожайности ----
    by = ["okato", "crop_code", "farm_category_code"]
    v = p.value_raw
    p["flag_zero"] = v == 0
    p["flag_negative"] = v < 0
    pos = v.where(v > 0)
    med = pos.groupby([p[b] for b in by]).transform("median")
    p["series_median"] = med
    p["flag_outlier_hi"] = (v > OUTLIER_K * med).fillna(False)
    p["flag_outlier_lo"] = ((v > 0) & (v < med / OUTLIER_K)).fillna(False)
    maxp = p.crop_code.map(crops.set_index("crop_code").max_plausible_t_ha)
    p["flag_implausible"] = (v / 10 > maxp).fillna(False)
    p = p.sort_values(by + ["year"]).reset_index(drop=True)
    prev = p.groupby(by).value_raw.shift()
    prev_year = p.groupby(by).year.shift()
    ratio = (v / prev).where((prev > 0) & (v > 0) & (prev_year == p.year - 1))
    p["flag_jump"] = ((ratio > OUTLIER_K) | (ratio < 1 / OUTLIER_K)).fillna(False)

    # ---- расчётная урожайность и согласованность (по исходному значению) ----
    p["gross_kt"] = p.gross_tc / 10
    area_ok = p.area_kha.where(p.area_kha > 0)
    p["yield_calc_t_ha"] = (p.gross_tc / area_ok / 10).where(p.gross_tc > 0)
    p["harvest_share"] = (p.gross_tc / (v.where(v > 0) * area_ok)).where(p.gross_tc > 0)
    p["flag_calc_mismatch"] = ((p.harvest_share < H_LOW) | (p.harvest_share > H_HIGH)).fillna(False)
    # «×3 от медианы» ловит и реальный рост культуры в регионе (подсолнечник и соя в Сибири: первые годы
    # 0,5–1 т/га, потом 2–2,5 т/га). Такой выброс подтверждается сбором и площадью — его не удаляем.
    p["outlier_confirmed_by_calc"] = p.flag_outlier_hi & p.harvest_share.between(H_LOW, H_HIGH)

    drop = p.flag_zero | p.flag_negative | (p.flag_outlier_hi & ~p.outlier_confirmed_by_calc) | p.flag_implausible
    p["value_clean"] = v.where(~drop)
    p["yield_t_ha"] = p.value_clean / 10

    # ---- заполнение: «всего» из компонентов, затем одиночные пропуски ----
    p["yield_filled_t_ha"] = p.yield_t_ha
    p["fill_method"] = np.where(p.yield_t_ha.notna(), "observed", None)
    comp = crops.dropna(subset=["components"]).set_index("crop_code").components.str.split(",")
    for total, parts in comp.items():
        sub = p[p.crop_code.isin(parts)][["okato", "farm_category_code", "year", "crop_code", "yield_t_ha", "area_kha"]]
        if sub.empty:
            continue
        w = sub.pivot_table(index=["okato", "farm_category_code", "year"], columns="crop_code",
                            values=["yield_t_ha", "area_kha"], dropna=False)
        ya = w["yield_t_ha"].reindex(columns=parts)
        aa = w["area_kha"].reindex(columns=parts).fillna(0)
        valid = (ya.notna() | (aa == 0)).all(axis=1) & (aa.sum(axis=1) > 0)
        der = ((ya.fillna(0) * aa).sum(axis=1) / aa.sum(axis=1)).where(valid).rename("der").reset_index()
        der["crop_code"] = total
        p = p.merge(der, on=["okato", "farm_category_code", "year", "crop_code"], how="left")
        m = p.yield_filled_t_ha.isna() & p.der.notna()
        p.loc[m, "yield_filled_t_ha"] = p.loc[m, "der"]
        p.loc[m, "fill_method"] = "derived_components"
        p = p.drop(columns="der")
    p = p.sort_values(by + ["year"]).reset_index(drop=True)
    gb = p.groupby(by)
    prv, nxt = gb.yield_filled_t_ha.shift(1), gb.yield_filled_t_ha.shift(-1)
    py, ny = gb.year.shift(1), gb.year.shift(-1)
    single = p.yield_filled_t_ha.isna() & prv.notna() & nxt.notna() & (py == p.year - 1) & (ny == p.year + 1)
    p.loc[single, "yield_filled_t_ha"] = (prv + nxt)[single] / 2
    p.loc[single, "fill_method"] = "interpolated"
    p["is_interpolated"] = p.fill_method == "interpolated"
    p["is_derived"] = p.fill_method == "derived_components"

    p["year"] = p.year.astype(int)
    p = _series_stats(p, "value_clean", by)

    c = crops.set_index("crop_code")
    p["crop_name"] = p.crop_code.map(c.crop_name)
    p["crop_group"] = p.crop_code.map(c.group)
    p["is_main"] = p.crop_code.map(c.is_main).fillna(False).astype(bool)
    reg = regions_raw().set_index("okato").name_emiss
    p["region"] = p.okato.map(reg)
    names = emiss("31533")[["okato", "region"]].drop_duplicates("okato").set_index("okato").region
    p["region"] = p.region.fillna(p.okato.map(names))
    p.loc[p.okato == RF, "region"] = "Российская Федерация"
    cols = ["okato", "region", "region_level", "fo", "okato_src", "crop_code", "crop_name", "crop_group", "is_main",
            "farm_category_code", "farm_category", "year",
            "value_raw", "value_clean", "yield_t_ha", "yield_filled_t_ha", "fill_method", "is_interpolated",
            "is_derived", "area_kha", "area_code", "area_from_alias", "area_confidential", "gross_tc", "gross_kt",
            "gross_confidential", "yield_calc_t_ha", "harvest_share", "series_median",
            "flag_confidential", "flag_zero", "flag_negative", "flag_outlier_hi", "flag_outlier_lo", "flag_jump",
            "flag_implausible", "flag_calc_mismatch", "outlier_confirmed_by_calc", "run_len", "series_n_years", "series_max_run"]
    p = p[cols].sort_values(KEY).reset_index(drop=True)
    p["year"] = p.year.astype("int16")
    return p


def build_operational(cfg: Config) -> pd.DataFrame:
    parts = []
    for ind, measure in (("33978", "yield_oper_c_ha"), ("34165", "gross_oper_kt"), ("33784", "harvested_area_kha")):
        d = harmonize_regions(emiss(ind))
        if "farm_category_code" not in d:
            d["farm_category_code"], d["farm_category"] = "2", "Сельскохозяйственные организации (по показателю)"
        d["indicator_id"], d["measure"] = int(ind), measure
        parts.append(d[["okato", "okato_src", "region_level", "fo", "crop_code", "crop", "farm_category_code",
                        "farm_category", "year", "period", "indicator_id", "measure", "unit", "value",
                        "confidential"]])
    o = pd.concat(parts, ignore_index=True)
    o["period_date"] = pd.to_datetime(o.year.astype(str) + "-" + o.period.map(PERIOD_DATE))
    o["final_crop_code"] = o.crop_code.map(OPER_TO_FINAL)
    o["value_t_ha"] = (o.value / 10).where(o.measure == "yield_oper_c_ha")
    o["bias_vs_final_pct"] = o.crop_code.map(OPER_BIAS_PCT).where(o.measure == "yield_oper_c_ha")
    o["value_t_ha_bias_adj"] = o.value_t_ha / (1 + o.bias_vs_final_pct / 100)
    o["bias_note"] = np.where(
        o.measure == "yield_oper_c_ha",
        "СХО; смещение оценено на «на 1 ноября» 2023–2024 против 31533 (СХО); зерновые — без кукурузы против итога "
        "с кукурузой; на ранние срезы переносится условно", None)
    o["is_latest_period"] = o.period_date == o.groupby(["indicator_id", "year"]).period_date.transform("max")
    o["year"] = o.year.astype("int16")
    return o.sort_values(["measure", "okato", "crop_code", "farm_category_code", "period_date"]).reset_index(drop=True)


def build(cfg: Config) -> None:
    p = build_panel(cfg)
    save(p, "yield_panel", cfg)
    s = p[p.region_level == "subject"]
    flags = [c for c in p.columns if c.startswith("flag_")] + ["outlier_confirmed_by_calc", "is_interpolated", "is_derived", "area_from_alias"]
    write_stats("yield_panel", {
        "rows": len(p), "rows_subject": len(s), "years": [int(p.year.min()), int(p.year.max())],
        "subjects_with_yield": int(s[s.value_clean.notna()].okato.nunique()),
        "crops_with_yield": int(s[s.value_clean.notna()].crop_code.nunique()),
        "flags_all_levels": {f: int(p[f].sum()) for f in flags},
        "flags_subject_cat1": {f: int(s[s.farm_category_code == CAT_ALL][f].sum()) for f in flags},
        "value_raw_nonnull": int(p.value_raw.notna().sum()), "value_clean_nonnull": int(p.value_clean.notna().sum()),
        "filled_nonnull": int(p.yield_filled_t_ha.notna().sum()),
        "fill_method": p.fill_method.value_counts().to_dict(),
        "yield_calc_2025_subject_cat1": int(s[(s.year == 2025) & (s.farm_category_code == CAT_ALL)]
                                            .yield_calc_t_ha.notna().sum()),
        "main_coverage_subject_cat1_run15": s[(s.farm_category_code == CAT_ALL) & s.is_main & (s.series_max_run >= 15)]
        .groupby("crop_name").okato.nunique().to_dict(),
    })
    o = build_operational(cfg)
    save(o, "yield_operational", cfg)
    write_stats("yield_operational", {"rows": len(o), "by_measure_year": {f"{m} {y}": int(n) for (m, y), n in
                                                          o.groupby(["measure", "year"]).size().items()}})
