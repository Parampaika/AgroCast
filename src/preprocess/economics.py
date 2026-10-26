"""Вспомогательные экономические и агротехнические показатели: data/clean/economics_aux.parquet (длинный формат).

Показатели ЕМИСС, которые уже скачаны и пригодятся экономической части (все — по с/х организациям):
30963/30964 — минеральные удобрения всего и на 1 га посева (по группам культур), 30965/30966 — органические,
31632 — энергомощности на 100 га посева, 33410 — наличие техники, 42380/42381 — себестоимость продукции
растениеводства (только РФ). Территории приведены к каноничным кодам (как в yield_panel).
`coverage`: «subjects» — есть данные по субъектам, «rf_only» — только по РФ; `n_subjects` — число субъектов
с данными в этом году по этой позиции.
"""
from __future__ import annotations

import pandas as pd

from preprocess.common import ROOT, Config, emiss, save, write_stats
from preprocess.yield_panel import harmonize_regions

IDS = ["30963", "30964", "30965", "30966", "31632", "33410", "42380", "42381"]
ITEM_COLS = {"crop_code": "crop", "S_TEXNIC_code": "S_TEXNIC"}


def build(cfg: Config) -> None:
    inv = pd.read_csv(ROOT / "data" / "interim" / "emiss" / "inventory.tsv", sep="\t", dtype={"id": str})
    names = dict(zip(inv["id"], inv["title"]))
    parts = []
    for ind in IDS:
        d = harmonize_regions(emiss(ind))
        d["item_code"], d["item_name"] = None, None
        for c, n in ITEM_COLS.items():
            if c in d:
                d["item_code"], d["item_name"] = d[c], d[n]
        if "farm_category_code" not in d:
            d["farm_category_code"], d["farm_category"] = "2", "Сельскохозяйственные организации (по показателю)"
        d["indicator_id"] = int(ind)
        d["indicator_name"] = names.get(ind, "")
        parts.append(d[["indicator_id", "indicator_name", "okato", "okato_src", "region_level", "fo", "year",
                        "item_code", "item_name", "farm_category_code", "farm_category", "unit", "value",
                        "confidential"]])
    e = pd.concat(parts, ignore_index=True)
    e = e[e.value.notna() | e.confidential]
    subj = e[e.region_level == "subject"]
    n = subj.groupby(["indicator_id", "item_code", "farm_category_code", "year"], dropna=False).okato.nunique() \
        .rename("n_subjects").reset_index()
    e = e.merge(n, on=["indicator_id", "item_code", "farm_category_code", "year"], how="left")
    e["n_subjects"] = e.n_subjects.fillna(0).astype("int16")
    has_subj = subj.groupby("indicator_id").size()
    e["coverage"] = e.indicator_id.map(lambda i: "subjects" if has_subj.get(i, 0) > 0 else "rf_only")
    e["year"] = e.year.astype("int16")
    e = e.sort_values(["indicator_id", "okato", "item_code", "farm_category_code", "year"]).reset_index(drop=True)
    save(e, "economics_aux", cfg)
    write_stats("economics", {
        "rows": len(e),
        "by_indicator": {str(k): {"rows": int(len(g)), "years": [int(g.year.min()), int(g.year.max())],
                                  "subjects": int(g[g.region_level == "subject"].okato.nunique()),
                                  "coverage": g.coverage.iloc[0], "unit": g.unit.iloc[0]}
                         for k, g in e.groupby("indicator_id")},
    })
