"""Почвы по региону: data/clean/soil_region.parquet (ключ okato).

SoilGrids 2.0 (ISRIC, 250 м) в точках пашни, статистика mean. Слои 0–30 см (0–5, 5–15, 15–30, веса по мощности)
и 30–60 см. Среднее по точкам региона с весом доли пашни вокруг точки. −32768 (вода, город) — пропуск.
Единицы переведены из «mapped units» SoilGrids в привычные (см. UNITS).
Тип почвы — наиболее вероятный класс WRB (wrb_points.csv), доминирующий по сумме весов точек.
Слоёв влагоёмкости (wv0010/0033/1500) на сервере ISRIC нет — не включены.
Рельеф (`elev_*`, м над уровнем моря) — высота ячеек ERA5-Land/ERA5 (static_cells.csv, HSURF) в точках пашни;
`era5_soil_type` — доминирующий тип почвы ERA5 (код 1–7: от грубой к органической).
"""
from __future__ import annotations

import pandas as pd

from preprocess.common import RAW, Config, points, save, weighted_mean, write_stats

# свойство: (делитель, единица после перевода)
UNITS = {"clay": (10, "%"), "sand": (10, "%"), "silt": (10, "%"), "soc": (10, "г/кг"), "phh2o": (10, "pH"),
         "nitrogen": (100, "г/кг"), "cec": (10, "смоль(+)/кг"), "bdod": (100, "г/см³"), "cfvo": (10, "% объёма"),
         "ocd": (10, "кг/м³")}
LAYERS = {"0_30": {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15}, "30_60": {"30-60cm": 30}}


def build(cfg: Config) -> None:
    s = pd.read_csv(RAW / "soilgrids" / "soilgrids_points.csv")
    s = s[(s.stat == "mean") & (s.value_raw != -32768)]
    pts = points().set_index("point_id")
    rows = []
    for lay, thick in LAYERS.items():
        x = s[s.depth.isin(thick) & s.property.isin(UNITS)].copy()
        x["t"] = x.depth.map(thick)
        x["val"] = x.value_raw / x.property.map(lambda p: UNITS[p][0])
        x = x.assign(vt=x.val * x.t).groupby(["point_id", "property"])[["vt", "t"]].sum()
        x = (x.vt / x.t).unstack()
        x.columns = [f"{c}_{lay}" for c in x.columns]
        rows.append(x)
    pt = pd.concat(rows, axis=1)
    ocs = s[s.property == "ocs"].groupby("point_id").value_raw.mean().rename("ocs_0_30")  # т/га
    pt = pt.join(ocs).join(pts[["okato", "w"]], how="inner").reset_index()
    vals = [c for c in pt.columns if c not in ("point_id", "okato", "w")]
    reg = weighted_mean(pt, ["okato"], vals)
    reg["n_points"] = reg.okato.map(pt.groupby("okato").size())

    wrb = pd.read_csv(RAW / "soilgrids" / "wrb_points.csv")
    codes = pd.read_csv(RAW / "soilgrids" / "wrb_class_codes_alphabetical.csv", header=None, names=["code", "name"])
    wrb = wrb[wrb.layer == "MostProbable"].merge(codes, left_on="value_raw", right_on="code", how="left")
    wrb = wrb.join(pts[["okato", "w"]], on="point_id")
    ws = wrb.groupby(["okato", "name"]).w.sum().reset_index().sort_values(["okato", "w"], ascending=[True, False])
    tot = ws.groupby("okato").w.sum()
    dom = ws.drop_duplicates("okato").set_index("okato")
    reg["wrb_dominant"] = reg.okato.map(dom.name)
    reg["wrb_dominant_share"] = reg.okato.map((dom.w / tot).round(3))
    second = ws.groupby("okato").nth(1).set_index("okato")
    reg["wrb_second"] = reg.okato.map(second.name)
    # рельеф: высота ячейки ERA5-Land (0,1°; для ячеек над морем — ERA5 0,25°) в точках пашни; тип почвы ERA5
    era = RAW / "era5_om"
    el = []
    for model in ("copernicus_era5_land", "copernicus_era5"):
        cells = pd.read_csv(era / model / "cells.csv").set_index("point_id").cell
        st = pd.read_csv(era / model / "static_cells.csv").set_index("cell")
        st["HSURF"] = st.HSURF.where(st.HSURF > -100)        # −999 — заполнитель (море); Прикаспий ≈ −28 м — норма
        st["soil_type"] = st.soil_type.where(st.soil_type > 0)  # 0 — вода
        el.append(pd.DataFrame({"h": cells.map(st.HSURF), "st": cells.map(st.soil_type)}))
    el = el[0].combine_first(el[1]).join(pts[["okato", "w"]], how="inner")
    g = el.groupby("okato")
    reg["elev_mean"] = reg.okato.map(g.apply(lambda x: (x.h * x.w).sum() / x.w[x.h.notna()].sum(),
                                             include_groups=False))
    reg["elev_min"], reg["elev_max"] = reg.okato.map(g.h.min()), reg.okato.map(g.h.max())
    reg["elev_std"] = reg.okato.map(g.h.std()).fillna(0)
    reg["era5_soil_type"] = reg.okato.map(el.dropna(subset=["st"]).groupby(["okato", "st"]).w.sum().reset_index()
                                          .sort_values("w").drop_duplicates("okato", keep="last")
                                          .set_index("okato").st).astype("Int64")
    vals += ["elev_mean", "elev_min", "elev_max", "elev_std"]
    for c in vals:
        reg[c] = reg[c].astype("float32")
    save(reg, "soil_region", cfg)
    write_stats("soil", {"regions": len(reg), "nan_share": float(reg[vals].isna().mean().mean()),
                         "units": {k: v[1] for k, v in UNITS.items()} | {"ocs": "т/га"},
                         "wrb_dominant": reg.wrb_dominant.value_counts().to_dict()})
