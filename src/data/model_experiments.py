"""Эксперименты с погодной моделью: набор признаков, регуляризация, тренд, веса, ансамбль.

Запуск (после build_features.py):
    uv run python -I -X utf8 src/data/model_experiments.py

Схема — скользящая проверка t = 2012…2025 (обучение и тренд по сезонам ≤ t−1).
Выход: reports/tables/model_experiments.csv (MAE/MAPE по культурам и вариантам),
       data/processed/model/experiments_predictions.parquet.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent))
from common import MAIN, TAB  # noqa: E402
from model_weather import CROPS, OUT, STATIC, WINTER_CROPS, add_trend, feature_cols, load_panel  # noqa: E402

warnings.filterwarnings("ignore")
KEY_VARS = ["tmean", "tmax", "prec", "cwb", "sm7_28", "sm28_100", "hot30"]
TESTS = list(range(2012, 2026))


def reduced_cols(crop: str) -> list[str]:
    cols = [f"a_{v}_{m}" for v in KEY_VARS for m in CROPS[crop]]
    if crop in WINTER_CROPS:
        cols += ["a_tsoil_min_win", "a_cold20_win", "tsoil_min_win"]
    return cols + STATIC


def ridge(alpha):
    return lambda: make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=alpha))


def hgb(depth=3, leaf=25, lr=0.04, it=300, l2=1.0):
    return lambda: HistGradientBoostingRegressor(max_iter=it, learning_rate=lr, max_depth=depth, min_samples_leaf=leaf,
                                                 l2_regularization=l2, random_state=0)


VARIANTS = {
    "ridge300_full": (ridge(300), "full", False),
    "ridge100_full": (ridge(100), "full", False),
    "ridge1000_full": (ridge(1000), "full", False),
    "ridge300_red": (ridge(300), "red", False),
    "ridge100_red": (ridge(100), "red", False),
    "hgb_full": (hgb(), "full", False),
    "hgb_d2_full": (hgb(depth=2, leaf=40, lr=0.03, it=400, l2=3.0), "full", False),
    "hgb_d2_red": (hgb(depth=2, leaf=40, lr=0.03, it=400, l2=3.0), "red", False),
    "ridge300_full_w": (ridge(300), "full", True),
    "hgb_d2_full_w": (hgb(depth=2, leaf=40, lr=0.03, it=400, l2=3.0), "full", True),
}


def main():
    p = load_panel()
    recs = []
    for kind in ("lin", "lin15"):
        for t in TESTS:
            q = add_trend(p, t - 1, kind) if kind == "lin" else add_trend_lastn(p, t - 1, 15)
            for c in CROPS:
                qc = q[q.crop_code == c]
                tr = qc[(qc.year <= t - 1) & qc.r.notna()]
                te = qc[qc.year == t]
                if te.empty or len(tr) < 100:
                    continue
                base = {"okato": te.okato.values, "y": te.y.values, "trend_val": te.trend.values,
                        "area_tha": te.area_tha.values}
                recs.append(pd.DataFrame(base | {"variant": "trend_only", "yhat": te.trend.values}).assign(
                    crop_code=c, year=t, trend=kind))
                for name, (mk, fs, weighted) in VARIANTS.items():
                    cols = feature_cols(c) if fs == "full" else reduced_cols(c)
                    m = mk()
                    kw = {}
                    if weighted:
                        step = m.steps[-1][0] + "__sample_weight" if hasattr(m, "steps") else "sample_weight"
                        kw[step] = np.sqrt(tr.area_tha.values)
                    m.fit(tr[cols], tr.r, **kw)
                    rr = m.predict(te[cols])
                    recs.append(pd.DataFrame(base | {"variant": name, "yhat": te.trend.values * (1 + rr),
                                                     "r_hat": rr}).assign(crop_code=c, year=t, trend=kind))
            print(kind, t, flush=True)
    R = pd.concat(recs, ignore_index=True)
    # ансамбли
    piv = R.pivot_table(index=["trend", "crop_code", "okato", "year", "y", "trend_val", "area_tha"],
                        columns="variant", values="yhat").reset_index()
    for a, b in [("ridge300_full", "hgb_d2_full"), ("ridge300_full", "hgb_full"), ("ridge100_red", "hgb_d2_red")]:
        e = piv[["trend", "crop_code", "okato", "year", "y", "trend_val", "area_tha"]].copy()
        e["variant"], e["yhat"] = f"ens_{a}+{b}", (piv[a] + piv[b]) / 2
        R = pd.concat([R, e], ignore_index=True)
    R["crop"] = R.crop_code.map(MAIN)
    R.to_parquet(OUT / "experiments_predictions.parquet", index=False)

    R["ae"] = (R.yhat - R.y).abs()
    R["ape"] = R.ae / R.y * 100
    M = R.groupby(["trend", "variant", "crop"]).agg(MAE=("ae", "mean"), MAPE=("ape", "mean")).reset_index()
    tro = M[M.variant == "trend_only"].set_index(["trend", "crop"]).MAE
    M["skill"] = 1 - M.MAE / tro.reindex(pd.MultiIndex.from_frame(M[["trend", "crop"]])).values
    M.to_csv(TAB / "model_experiments.csv", index=False)
    pd.set_option("display.width", 250)
    for kind in ("lin", "lin15"):
        s = M[M.trend == kind]
        print(f"\n=== тренд {kind}: выигрыш по MAE против тренда")
        tab = s.pivot(index="variant", columns="crop", values="skill")
        tab["mean"] = tab.mean(axis=1)
        print(tab.sort_values("mean", ascending=False).round(3))
    s = M[M.variant == "trend_only"].pivot(index="trend", columns="crop", values="MAE")
    print("\nMAE тренда:\n", s.round(3))


def add_trend_lastn(p, last, n):
    out = []
    for (c, ok), g in p.groupby(["crop_code", "okato"]):
        tr = g[(g.year <= last) & (g.year > last - n)]
        if len(tr) < 6:
            continue
        b = np.polyfit(tr.year, tr.y, 1)
        out.append(g.assign(trend=np.polyval(b, g.year)))
    q = pd.concat(out)
    q = q[q.trend > 0.05 * q.groupby(["crop_code", "okato"]).y.transform("mean")]
    q["r"] = (q.y / q.trend - 1).clip(-0.8, 0.8)
    return q


if __name__ == "__main__":
    main()
