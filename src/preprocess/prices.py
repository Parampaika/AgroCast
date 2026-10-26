"""Цены производителей «регион × продукт × год»: data/clean/prices.parquet и prices_crop_map.parquet.

Источники: ЕМИСС 31454 (ОКПД, 1999–2016) и 57693 (ОКПД2, 2017–2026), руб./т, годовая цена — период
«январь-декабрь». Годы не пересекаются, стык — по году 2016/2017 (продукты сопоставлены по названию, коды
ОКПД ↔ ОКПД2 — в PRODUCTS). Для неполного года (2026: «январь-сентябрь») берётся последний накопленный
период, флаг `is_partial_year`.
Иерархия подстановки: цена субъекта → среднее по субъектам ФО в тот же год → РФ; `price_source`.
Реальные цены: дефлятор — индекс цен производителей всей с/х продукции РФ (ОКПД/ОКПД2 «01»), цепочка
месячных индексов «к декабрю предыдущего года» из 31110 (до 2016) и 57740 (с 2017), среднегодовой уровень;
`price_real` — в рублях базового года (`--price-base-year`, по умолчанию 2021).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from preprocess.common import RF, Config, emiss, fo_map, regions_raw, save, write_stats
from preprocess.yield_panel import harmonize_regions

# product_id: (название, коды 31454, коды 57693, культуры 31533)
PRODUCTS = {
    "wheat": ("Пшеница", ["01.11.01"], ["01.11.1"], ["1010400", "1010500", "1010401"]),
    "grain_total": ("Зерновые и зернобобовые культуры", ["01.11.02"], ["01.11.12.001.АГ"], ["1000001"]),
    "maize": ("Кукуруза", ["01.11.13"], ["01.11.2", "01.11.20"], ["1080202"]),
    "barley": ("Ячмень", ["01.11.15"], ["01.11.31"], ["1030100", "1030200", "1030201"]),
    "rye": ("Рожь", ["01.11.16.101"], ["01.11.32"], ["1020200", "1020300", "1020201"]),
    "oats": ("Овёс", ["01.11.16.130"], ["01.11.33"], ["1060000"]),
    "buckwheat": ("Гречиха", ["01.11.17.110"], ["01.11.49.110"], ["1120000"]),
    "millet": ("Просо", ["01.11.17.120"], ["01.11.42"], ["1110000"]),
    "triticale": ("Тритикале", [], ["01.11.49.120"], ["1140001"]),
    "pulses": ("Зернобобовые культуры", ["01.11.22"], ["01.11.7"], ["2000000"]),
    "peas": ("Горох", ["01.11.22.110"], ["01.11.75"], ["2010000"]),
    "soy": ("Бобы соевые", ["01.11.31"], ["01.11.81"], ["3100000", "3100009"]),
    "rapeseed": ("Семена рапса", ["01.11.33.101"], ["01.11.93"],
                 ["3130000", "3130100", "3130200", "3130001", "3130101", "3130201"]),
    "sunflower": ("Семена подсолнечника", ["01.11.33.110"], ["01.11.95"], ["3080000", "3080102"]),
    "sugar_beet": ("Сахарная свёкла", ["01.11.51.000"], ["01.13.71.110"], ["3060100"]),
    "potato": ("Картофель", ["01.11.21"], ["01.13.51"], ["4010000"]),
    "vegetables": ("Овощи", ["01.12.1"], ["01.13.01.001.АГ"], ["4020301"]),
    "wheat_durum": ("Пшеница твёрдая", ["01.11.11.104"], ["01.11.11"], []),
    "wheat_cl3": ("Пшеница мягкая 3 класса", ["01.11.12.101"], ["01.11.12.006.АГ"], []),
    "wheat_cl4": ("Пшеница мягкая 4 класса", ["01.11.12.102"], ["01.11.12.007.АГ"], []),
    "wheat_cl5": ("Пшеница мягкая 5 класса", ["01.11.12.105"], ["01.11.12.008.АГ"], []),
}
MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь",
          "декабрь"]


def _annual(d: pd.DataFrame, code_col: str, src: int) -> pd.DataFrame:
    """Годовая цена: «январь-декабрь», иначе последний накопленный период года (неполный год)."""
    d = d[d.period.str.startswith("январь-") | (d.period == "январь")].copy()
    d["n_months"] = d.period.map(lambda s: MONTHS.index(s.split("-")[-1]) + 1)
    d = d[d.value.notna() & (d.value > 0)]
    d = d.sort_values("n_months").drop_duplicates(["okato", code_col, "year"], keep="last")
    code2pid = {c: pid for pid, (_, a, b, _) in PRODUCTS.items() for c in (a if src == 31454 else b)}
    d["product_id"] = d[code_col].map(code2pid)
    d = d[d.product_id.notna()]
    d = d.rename(columns={code_col: "product_code_src"})
    d["source_indicator"] = src
    return d[["okato", "okato_src", "region_level", "product_id", "product_code_src", "year", "value", "n_months",
              "source_indicator"]]


def deflator(cfg: Config) -> pd.DataFrame:
    """Среднегодовой уровень цен с/х продукции РФ, база = cfg.price_base_year.

    Уровень месяца = уровень декабря прошлого года × индекс «к декабрю предыдущего года» (этот ряд полный;
    в ряду «к предыдущему месяцу» 31110 пропущен один месяц 2001 г.).
    """
    parts = []
    for ind, col in (("31110", "s_OKPD_code"), ("57740", "s_OKPD2_code")):
        d = emiss(ind)
        d = d[(d.s_POK_code == "4") & (d[col] == "01") & d.okato.isin(["643", "643004.АГ"]) & d.value.notna()]
        d = d.assign(m=d.period.map(MONTHS.index) + 1)
        d = d.sort_values("okato").drop_duplicates(["year", "m"], keep="first")  # 643 приоритетнее
        parts.append(d[["year", "m", "value"]])
    m = pd.concat(parts).sort_values(["year", "m"]).drop_duplicates(["year", "m"]).reset_index(drop=True)
    gaps = len(pd.date_range(f"{m.year.min()}-01-01", f"{m.year.max()}-{m.m.iloc[-1]:02d}-01", freq="MS")) - len(m)
    dec = 1.0
    levels = []
    for y, grp in m.groupby("year"):
        lv = dec * grp.value.values / 100
        levels.append(pd.DataFrame({"year": y, "m": grp.m.values, "level": lv}))
        if 12 in grp.m.values:
            dec = lv[list(grp.m.values).index(12)]
    lv = pd.concat(levels)
    y = lv.groupby("year").agg(level=("level", "mean"), n_months=("m", "size")).reset_index()
    base = y.loc[y.year == cfg.price_base_year, "level"]
    y["deflator"] = y.level / (base.iloc[0] if len(base) else np.nan)
    y.attrs["gaps"] = gaps
    return y


def build(cfg: Config) -> None:
    a = harmonize_regions(emiss("31454"))
    b = harmonize_regions(emiss("57693"))
    b = b[b.s_OKEI.str.startswith("Тонна", na=False)]
    p = pd.concat([_annual(a[a.year <= 2016], "s_OKPD_code", 31454), _annual(b[b.year >= 2017], "s_OKPD2_code", 57693)])
    # при смене кода внутри 57693 (кукуруза 01.11.2 → 01.11.20 с 2024) оставляем один ряд на продукт
    p = p.sort_values("n_months").drop_duplicates(["okato", "product_id", "year"], keep="last")

    regs = regions_raw()
    fo = fo_map()
    subj = p[p.region_level == "subject"]
    rf = p[p.okato == RF].set_index(["product_id", "year"])
    years = range(int(p.year.min()), int(p.year.max()) + 1)
    grid = pd.MultiIndex.from_product([regs.okato, list(PRODUCTS), years], names=["okato", "product_id", "year"])
    g = pd.DataFrame(index=grid).reset_index()
    g["fo"] = g.okato.map(fo)
    g = g.merge(subj[["okato", "product_id", "year", "value", "n_months", "source_indicator", "product_code_src",
                      "okato_src"]].rename(columns={"value": "price_region"}),
                on=["okato", "product_id", "year"], how="left")
    sf = subj.assign(fo=subj.okato.map(fo)).groupby(["fo", "product_id", "year"]) \
        .agg(price_fo=("value", "mean"), n_fo_subjects=("value", "size")).reset_index()
    g = g.merge(sf, on=["fo", "product_id", "year"], how="left")
    g["price_rf"] = [rf.value.get((pid, y), np.nan) for pid, y in zip(g.product_id, g.year)]
    g["price"] = g.price_region.fillna(g.price_fo).fillna(g.price_rf)
    g["price_source"] = np.select([g.price_region.notna(), g.price_fo.notna(), g.price_rf.notna()],
                                  ["region", "fo", "rf"], default=None)
    rf_months = rf.n_months
    g["n_months"] = g.n_months.fillna(pd.Series([rf_months.get((pid, y), np.nan) for pid, y in
                                                 zip(g.product_id, g.year)], index=g.index))
    g["is_partial_year"] = g.n_months < 12
    g["source_indicator"] = np.where(g.year <= 2016, 31454, 57693)
    g = g[g.price.notna()].copy()

    d = deflator(cfg)
    g = g.merge(d[["year", "deflator"]], on="year", how="left")
    g["price_real"] = g.price / g.deflator
    g["price_base_year"] = cfg.price_base_year
    g["product_name"] = g.product_id.map({k: v[0] for k, v in PRODUCTS.items()})
    g["unit"] = "руб./т"
    g["year"] = g.year.astype("int16")
    g = g[["okato", "fo", "product_id", "product_name", "year", "price", "price_source", "price_region", "price_fo",
           "n_fo_subjects", "price_rf", "price_real", "deflator", "price_base_year", "is_partial_year", "n_months",
           "source_indicator", "product_code_src", "okato_src", "unit"]]
    # РФ отдельной строкой (okato 643) — для сводных расчётов
    rfr = rf.reset_index()
    rfr = rfr.assign(okato=RF, fo=None, price=rfr.value, price_source="rf", price_rf=rfr.value,
                     is_partial_year=rfr.n_months < 12)
    rfr = rfr.merge(d[["year", "deflator"]], on="year", how="left")
    rfr["price_real"] = rfr.price / rfr.deflator
    rfr["price_base_year"] = cfg.price_base_year
    rfr["product_name"] = rfr.product_id.map({k: v[0] for k, v in PRODUCTS.items()})
    rfr["unit"] = "руб./т"
    out = pd.concat([g, rfr.reindex(columns=g.columns)], ignore_index=True)
    out = out.sort_values(["okato", "product_id", "year"]).reset_index(drop=True)
    save(out, "prices", cfg)

    cm = pd.DataFrame([(pid, v[0], v[1], v[2], c) for pid, v in PRODUCTS.items() for c in v[3]],
                      columns=["product_id", "product_name", "okpd_31454", "okpd2_57693", "crop_code"])
    cm["okpd_31454"] = cm.okpd_31454.str.join(",")
    cm["okpd2_57693"] = cm.okpd2_57693.str.join(",")
    save(cm, "prices_crop_map", cfg)

    # стык 2016/2017 по РФ: отношение цены 2017 к 2016 (проверка на скачок из-за смены классификатора)
    rr = rfr.pivot_table(index="product_id", columns="year", values="price")
    stitch = (rr.get(2017) / rr.get(2016)).round(3).dropna().to_dict() if 2016 in rr and 2017 in rr else {}
    defl = d.set_index("year")
    write_stats("prices", {
        "rows": len(out), "products": len(PRODUCTS), "years": [int(out.year.min()), int(out.year.max())],
        "source_share": out[out.okato != RF].price_source.value_counts(normalize=True).round(3).to_dict(),
        "stitch_ratio_2017_2016_rf": stitch, "deflator_month_gaps": int(d.attrs.get("gaps", 0)),
        "deflator": defl.deflator.round(3).to_dict(), "deflator_n_months": defl.n_months.to_dict(),
    })
