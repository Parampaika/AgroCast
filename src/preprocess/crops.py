"""Справочник культур: data/clean/crops.parquet (ключ crop_code — код ЕМИСС).

Объединяет коды из урожайности (31533), посевных площадей (31328) и валового сбора (30950).
Склейки и смены кодов:
- «в весе после доработки» (3080102, 3100009, 3130201, …) — отдельный показатель той же культуры:
  `base_crop_code` указывает на основную культуру, площадь берётся у неё;
- «Подсолнечник на зерно» (3080100) — в 31328 с 2022 г. параллельно «Подсолнечнику» (3080000),
  площадь берётся с 3080000, 3080100 — `area_alias_of`;
- «Пшеница озимая и яровая» (1010401), «рожь», «ячмень», «рапс» всего — с 2007 г.;
  компоненты (`components`) позволяют досчитать ряд до 2007 г. (в yield_panel с флагом is_derived).
Флаг `is_main` — рекомендация отчёта reports/eda_emiss.md (п. 7), а не фильтр.
"""
from __future__ import annotations

import pandas as pd

from preprocess.common import Config, emiss, save, write_stats

AFTER_PROCESSING = {  # «в весе после доработки» → основная культура
    "3010102": "3010100", "3010401": "3010400", "3020101": "3020100", "3080102": "3080000",
    "3100009": "3100000", "3110001": "3110000", "3120001": "3120000", "3130001": "3130000",
    "3130101": "3130100", "3130201": "3130200", "3200001": "3200000",
}
AREA_ALIAS = {"3080100": "3080000", "3010101": "3010300"}  # коды площади 31328 → код ряда урожайности
COMPONENTS = {"1010401": ["1010400", "1010500"], "1020201": ["1020200", "1020300"],
              "1030201": ["1030100", "1030200"], "3130000": ["3130100", "3130200"]}
AGGREGATES = {"1000001", "1040000", "1070100", "17", "2000000", "3000000", "3200000", "3200001", "4000000",
              "5000000", "6", "8200000", "4020300", "4020302", "8000100", "8040201", "1010401", "1020201",
              "1030201", "3130000", "3130001", "4020301"}
MAIN = ["1010400", "1010500", "1030100", "3080000", "1080202", "3100000"]
PRIORITY = {"1010400": 1, "1010500": 1, "1030100": 1, "3080000": 1, "1080202": 1, "3100000": 2,
            "3060100": 3, "4010000": 3, "3130200": 3, "1010401": 3, "1060000": 3}
WINTER = {"1010400", "1020200", "1030200", "3130100", "3130101", "1010800", "1040000"}
MIXED = {"1010401", "1020201", "1030201", "3130000", "3130001", "1140001", "1000001", "1070100", "2000000"}
# GGCMI Phase 3: культура календаря; proxy=True — у GGCMI нет такой культуры, взят близкий аналог
GGCMI = {"1010400": ("wwh", False), "1010500": ("swh", False), "1010401": ("wwh", True),
         "1010800": ("wwh", True), "1140001": ("wwh", True), "1040000": ("wwh", True),
         "1020200": ("rye", False), "1020201": ("rye", True), "1020300": ("rye", True),
         "1030100": ("bar", False), "1030201": ("bar", True), "1030200": ("wwh", True),
         "1060000": ("bar", True), "17": ("swh", True), "1000001": ("wwh", True), "1070100": ("wwh", True),
         "1080202": ("mai", False), "1080700": ("mai", True), "1110000": ("mil", False), "1120000": ("mil", True),
         "1130000": ("ri1", False), "2080000": ("sor", False), "2010000": ("pea", False), "2000000": ("pea", True),
         "3080000": ("sun", False), "3080102": ("sun", False), "3100000": ("soy", False),
         "3100009": ("soy", False), "3060100": ("sgb", False), "4010000": ("pot", False),
         "3130000": ("rap", False), "3130001": ("rap", False), "3130100": ("rap", True),
         "3130101": ("rap", True), "3130200": ("rap", False), "3130201": ("rap", False)}
# правдоподобная урожайность, т/га (выше — ошибка ввода; используется во флаге flag_implausible)
MAX_T_HA = {"зерновые": 15.0, "зернобобовые": 8.0, "масличные": 6.0, "технические": 90.0, "картофель": 70.0,
            "овощи и бахчевые": 150.0, "кормовые": 100.0, "плодово-ягодные": 60.0, "итого": 100.0}


def group_of(code: str, name: str) -> str:
    n = name.lower()
    if code in ("6", "8200000"):
        return "итого"
    if code == "4010000":
        return "картофель"
    if code == "3060600":  # свёкла столовая
        return "овощи и бахчевые"
    if code.startswith("8"):
        return "плодово-ягодные"
    if code.startswith(("5", "6", "7")) or code == "1080700":
        return "кормовые"
    if code.startswith("4"):
        return "овощи и бахчевые"
    if code.startswith("2"):
        return "зернобобовые"
    if code.startswith(("1",)) or code == "17":
        return "зерновые"
    if code.startswith(("306", "301010", "3010300", "302")) and "кудряш" not in n:
        return "технические"
    if code.startswith("3"):
        return "масличные" if code != "3000000" else "технические"
    return "прочие"


def season_of(code: str, name: str) -> str:
    n = name.lower()
    if code in MIXED or "озимая и яровая" in n or "озимый и яровой" in n:
        return "смешанная"
    if code in WINTER or "озим" in n:
        return "озимая"
    if "многолетн" in n or code.startswith("8"):
        return "многолетняя"
    if code in ("6", "8200000", "3000000", "4000000", "5000000", "3200000", "3200001"):
        return "н/д"
    return "яровая"


def build(cfg: Config) -> pd.DataFrame:
    frames = []
    for ind, col in (("31533", "has_yield"), ("31328", "has_area"), ("30950", "has_gross")):
        d = emiss(ind)
        d = d[d.value.notna() & d.region_level.isin(["subject", "rf", "rf_part"])]
        g = d.groupby("crop_code").agg(name=("crop", "first"), y0=("year", "min"), y1=("year", "max"),
                                       n_reg=("okato", "nunique"))
        g.columns = [f"{c}_{ind}" for c in g.columns]
        frames.append(g)
    c = pd.concat(frames, axis=1)
    c.index.name = "crop_code"
    c = c.reset_index()
    c["crop_name"] = c.name_31533.fillna(c.name_31328).fillna(c.name_30950)
    c = c.drop(columns=[x for x in c.columns if x.startswith("name_")])
    c["has_yield"] = c.y0_31533.notna()
    c["has_area"] = c.y0_31328.notna()
    c["has_gross"] = c.y0_30950.notna()
    c["base_crop_code"] = c.crop_code.map(AFTER_PROCESSING).fillna(c.crop_code)
    c["after_processing"] = c.crop_code.isin(AFTER_PROCESSING)
    c["area_alias_of"] = c.crop_code.map(AREA_ALIAS)
    c["area_code"] = c.base_crop_code  # код площади 31328 для расчётной урожайности и весов
    c["components"] = c.crop_code.map(lambda x: ",".join(COMPONENTS.get(x, [])) or None)
    c["is_aggregate"] = c.crop_code.isin(AGGREGATES)
    c["group"] = [group_of(a, b) for a, b in zip(c.crop_code, c.crop_name)]
    c["season_type"] = [season_of(a, b) for a, b in zip(c.crop_code, c.crop_name)]
    c["is_main"] = c.crop_code.isin(MAIN)
    c["priority"] = c.crop_code.map(PRIORITY).astype("Int64")
    c["ggcmi_crop"] = c.crop_code.map(lambda x: GGCMI.get(x, (None, None))[0])
    c["ggcmi_proxy"] = c.crop_code.map(lambda x: GGCMI.get(x, (None, None))[1])
    c["max_plausible_t_ha"] = c.group.map(MAX_T_HA)
    # бобовые и масличные с весом зелёной массы/сена — выше; плодово-ягодные учитываются как есть
    c.loc[c.crop_name.str.contains("зелен|силос|зеленый корм", case=False, na=False), "max_plausible_t_ha"] = 150.0
    c.loc[c.crop_code.isin(["1080202"]), "max_plausible_t_ha"] = 16.0
    c.loc[c.crop_code.isin(["3060100", "5000101"]), "max_plausible_t_ha"] = 90.0
    c.loc[c.crop_code.str.startswith(("30101", "30103", "30201", "30203", "30204")), "max_plausible_t_ha"] = 4.0
    c["unit_yield"] = "ц/га"
    for k in ("y0", "y1", "n_reg"):
        for ind in ("31533", "31328", "30950"):
            c[f"{k}_{ind}"] = c[f"{k}_{ind}"].astype("Int64")
    c = c.sort_values("crop_code").reset_index(drop=True)
    save(c, "crops", cfg)
    write_stats("crops", {"n": len(c), "with_yield": int(c.has_yield.sum()), "main": MAIN,
                          "groups": c.group.value_counts().to_dict()})
    return c
