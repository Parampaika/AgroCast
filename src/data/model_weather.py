"""Первая модель «урожайность = тренд × (1 + погодное отклонение)» и сравнение с бейзлайнами.

Запуск (после build_features.py и eda_gross_prices.py):
    uv run python -I -X utf8 src/data/model_weather.py

Цель: r = y / тренд − 1, тренд — линейный по годам обучения отдельно для каждого региона
(варианты: все годы обучения с 2001 / последние 10 лет). Модель на аномалиях погоды за месяцы,
важные для культуры, плюс климат и почвы региона: HistGradientBoosting и Ridge.
Проверка:
  fixed   — обучение на сезонах ≤ 2021, прогноз 2022–2025;
  rolling — для каждого t = 2012…2025 обучение на сезонах ≤ t−1 (тренд тоже), прогноз t.
2025 — урожайность, восстановленная по валовому сбору и посевной (yield_proxy.parquet), без подсолнечника.
Выход: reports/tables/model_*.csv, data/processed/model/predictions.parquet, reports/figures/model_*.png.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

sys.path.insert(0, str(Path(__file__).parent))
from common import (CAT_ALL, INK2, MAIN, MIN_AREA, PROC_ROOT, SERIES, TAB, area_reg, load, plt,  # noqa: E402
                    savefig)

warnings.filterwarnings("ignore", category=RuntimeWarning)
OUT = PROC_ROOT / "model"
OUT.mkdir(parents=True, exist_ok=True)

CROPS = {  # код → месяцы сезона
    "1010400": ["p09", "p10", "p11", "03", "04", "05", "06", "07"],
    "1010500": ["04", "05", "06", "07", "08"],
    "1030100": ["04", "05", "06", "07", "08"],
    "1080202": ["04", "05", "06", "07", "08", "09"],
    "3080000": ["04", "05", "06", "07", "08", "09"],
    "3100000": ["04", "05", "06", "07", "08", "09"],
    "3060100": ["04", "05", "06", "07", "08", "09"],
    "4010000": ["04", "05", "06", "07", "08"],
    "1060000": ["04", "05", "06", "07", "08"],
}
WINTER_CROPS = {"1010400"}
VARS = ["tmean", "tmax", "tmin", "prec", "et0", "cwb", "rad", "vpd", "sm0_7", "sm7_28", "sm28_100", "hot30", "hot35",
        "gdd5", "frost"]
STATIC = ["clim_t", "clim_p", "clim_et0", "soil_clay", "soil_sand", "soil_soc", "soil_phh2o", "soil_nitrogen",
          "soil_cec", "soil_bdod", "soil_ocs"]
NDVI = ["a_ndvi_05", "a_ndvi_06", "a_ndvi_07", "a_ndvi_08", "a_ndvi_max_5_8"]
Y_FIRST = 2001


def feature_cols(crop: str, ndvi: bool = False) -> list[str]:
    cols = [f"a_{v}_{m}" for v in VARS for m in CROPS[crop]]
    if crop in WINTER_CROPS:
        cols += ["a_tsoil_min_win", "a_cold20_win", "a_snow_win", "a_thaw_win", "tsoil_min_win"]
    cols += STATIC
    if ndvi:
        cols += NDVI
    return cols


def load_panel() -> pd.DataFrame:
    y = load("31533")
    y = y[(y.region_level == "subject") & (y.farm_category_code == CAT_ALL) & y.value.notna() & (y.value > 0)
          & y.crop_code.isin(CROPS)][["okato", "region", "fo", "crop_code", "year", "value"]]
    y["year"] = y.year.astype(int)
    y["y"] = y.value / 10
    y["src"] = "31533"
    px = pd.read_parquet(PROC_ROOT / "yield_proxy.parquet")
    px = px[(px.year == 2025) & px.crop_code.isin(CROPS) & px.yld_proxy.notna()]
    px = px.assign(y=px.yld_proxy / 10, src="proxy_30950", value=px.yld_proxy)[
        ["okato", "region", "fo", "crop_code", "year", "value", "y", "src"]]
    p = pd.concat([y.drop(columns="value"), px.drop(columns="value")], ignore_index=True)
    p = p[p.year >= Y_FIRST]
    p = p.join(area_reg(), on=["crop_code", "okato"])
    p = p[p.area_tha >= MIN_AREA]
    f = pd.read_parquet(PROC_ROOT / "features" / "region_season.parquet")
    return p.merge(f, on=["okato", "year"], how="left")


def fit_trend(g: pd.DataFrame, last: int, kind: str):
    tr = g[g.year <= last]
    if kind == "lin10":
        tr = tr[tr.year > last - 10]
    if len(tr) < 6:
        return None
    b = np.polyfit(tr.year, tr.y, 1)
    return b


def add_trend(p: pd.DataFrame, last: int, kind: str) -> pd.DataFrame:
    """Тренд, оценённый по сезонам ≤ last, — на все строки панели."""
    out = []
    for (c, ok), g in p.groupby(["crop_code", "okato"]):
        b = fit_trend(g, last, kind)
        if b is None:
            continue
        g = g.assign(trend=np.polyval(b, g.year))
        out.append(g)
    q = pd.concat(out)
    q = q[q.trend > 0.05 * q.groupby(["crop_code", "okato"]).y.transform("mean")]
    q["r"] = (q.y / q.trend - 1).clip(-0.8, 0.8)
    return q


class Ensemble:
    """Среднее прогнозов Ridge и бустинга — лучший вариант по model_experiments.py (тренд lin)."""

    def __init__(self):
        self.models = [_hgb(), _ridge()]

    def fit(self, X, y):
        for m in self.models:
            m.fit(X, y)
        return self

    def predict(self, X):
        return np.mean([m.predict(X) for m in self.models], axis=0)


def _hgb():
    return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.04, max_depth=3, min_samples_leaf=25,
                                         l2_regularization=1.0, random_state=0)


def _ridge():
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=300.0))


def make_models():
    return {"hgb": _hgb(), "ridge": _ridge(), "ens": Ensemble()}


def run(p: pd.DataFrame, tests: list[int], scheme: str, kind: str, ndvi: bool = False) -> pd.DataFrame:
    recs = []
    for t in tests:
        last = 2021 if scheme == "fixed" else t - 1
        q = add_trend(p, last, kind)
        for c in CROPS:
            cols = feature_cols(c, ndvi)
            qc = q[q.crop_code == c]
            tr = qc[(qc.year <= last) & qc.r.notna()]
            te = qc[qc.year == t]
            if te.empty or len(tr) < 100:
                continue
            for name, m in make_models().items():
                m.fit(tr[cols], tr.r)
                te_r = m.predict(te[cols])
                for (_, row), rr in zip(te.iterrows(), te_r):
                    recs.append({"scheme": scheme, "trend": kind, "ndvi": ndvi, "model": name, "crop_code": c,
                                 "okato": row.okato, "fo": row.fo, "year": t, "y": row.y, "src": row.src,
                                 "area_tha": row.area_tha, "trend_val": row.trend, "r_hat": rr,
                                 "yhat": row.trend * (1 + rr)})
            # бейзлайны в той же выборке
            hist = p[(p.crop_code == c) & (p.year < t)]
            for _, row in te.iterrows():
                h = hist[hist.okato == row.okato].set_index("year").y
                base = {"trend_only": row.trend,
                        "last_year": h.get(t - 1, np.nan),
                        "mean5": h[h.index >= t - 5].mean() if (h.index >= t - 5).sum() >= 3 else np.nan}
                for name, v in base.items():
                    recs.append({"scheme": scheme, "trend": kind, "ndvi": ndvi, "model": name, "crop_code": c,
                                 "okato": row.okato, "fo": row.fo, "year": t, "y": row.y, "src": row.src,
                                 "area_tha": row.area_tha, "trend_val": row.trend, "r_hat": np.nan, "yhat": v})
        print(scheme, kind, "ndvi" if ndvi else "", t, flush=True)
    return pd.DataFrame(recs)


def metrics(g: pd.DataFrame) -> pd.Series:
    g = g.dropna(subset=["yhat"])
    e = g.yhat - g.y
    return pd.Series({"n": len(g), "MAE": e.abs().mean(), "RMSE": np.sqrt((e ** 2).mean()),
                      "MAPE": (e.abs() / g.y).mean() * 100, "bias": e.mean(),
                      "wMAPE": np.average(e.abs() / g.y, weights=g.area_tha) * 100})


def rf_level(g: pd.DataFrame) -> pd.Series:
    g = g.dropna(subset=["yhat"])
    yh = np.average(g.yhat, weights=g.area_tha)
    y = np.average(g.y, weights=g.area_tha)
    return pd.Series({"y": y, "yhat": yh, "ape": abs(yh / y - 1) * 100})


def main():
    p = load_panel()
    print("панель:", len(p), "строк;", p.groupby("crop_code").okato.nunique().rename(MAIN).to_dict(), flush=True)
    res = []
    res.append(run(p, [2022, 2023, 2024, 2025], "fixed", "lin"))
    res.append(run(p, [2022, 2023, 2024, 2025], "fixed", "lin10"))
    res.append(run(p, list(range(2012, 2026)), "rolling", "lin"))
    res.append(run(p, list(range(2012, 2026)), "rolling", "lin10"))
    res.append(run(p, list(range(2012, 2026)), "rolling", "lin10", ndvi=True))
    R = pd.concat(res, ignore_index=True)
    R["crop"] = R.crop_code.map(MAIN)
    R.to_parquet(OUT / "predictions.parquet", index=False)

    keys = ["scheme", "trend", "ndvi", "crop", "model"]
    M = R.groupby(keys).apply(metrics, include_groups=False).reset_index()
    M.to_csv(TAB / "model_metrics.csv", index=False)
    My = R.groupby(keys + ["year"]).apply(metrics, include_groups=False).reset_index()
    My.to_csv(TAB / "model_metrics_by_year.csv", index=False)
    RF = R.groupby(keys + ["year"]).apply(rf_level, include_groups=False).reset_index()
    RF.to_csv(TAB / "model_rf_level.csv", index=False)

    pd.set_option("display.width", 250)
    for sch, kind, nd in [("fixed", "lin", False), ("fixed", "lin10", False), ("rolling", "lin", False),
                          ("rolling", "lin10", False), ("rolling", "lin10", True)]:
        s = M[(M.scheme == sch) & (M.trend == kind) & (M.ndvi == nd)]
        print(f"\n=== {sch} / тренд {kind} / ndvi={nd}: MAE т/га")
        print(s.pivot(index="crop", columns="model", values="MAE").round(3))
        print("MAPE %")
        print(s.pivot(index="crop", columns="model", values="MAPE").round(1))
    s = RF[(RF.scheme == "rolling") & (RF.trend == "lin10") & (~RF.ndvi)]
    print("\nРФ (сумма по модельным регионам), rolling lin10, MAPE %:")
    print(s.groupby(["crop", "model"]).ape.mean().unstack().round(1))

    # график: rolling lin10, MAE модели против бейзлайнов
    s = M[(M.scheme == "rolling") & (M.trend == "lin10") & (~M.ndvi)]
    piv = s.pivot(index="crop", columns="model", values="MAPE")
    order = ["last_year", "mean5", "trend_only", "ridge", "hgb"]
    labels = {"last_year": "прошлый год", "mean5": "среднее 5 лет", "trend_only": "тренд 10 лет",
              "ridge": "тренд × погода (ridge)", "hgb": "тренд × погода (бустинг)"}
    piv = piv[order].sort_values("trend_only")
    fig, ax = plt.subplots(figsize=(10, 5.5))
    h = 0.16
    for k, mth in enumerate(order):
        ax.barh(np.arange(len(piv)) - (k - len(order) / 2 + 0.5) * h, piv[mth], height=h * 0.85, color=SERIES[k],
                label=labels[mth])
    ax.set_yticks(range(len(piv)), piv.index)
    ax.invert_yaxis()
    ax.set_xlabel("MAPE по субъектам, % (скользящая проверка 2012–2025)")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.grid(axis="y", visible=False)
    ax.set_title("Погодная модель против простых бейзлайнов")
    savefig(fig, "model_vs_baselines_rolling.png")


if __name__ == "__main__":
    main()
