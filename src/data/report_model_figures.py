"""Итоговые таблицы и графики для reports/model_weather.md.

Запуск (после model_weather.py, model_experiments.py, model_leadtime.py ens lin):
    uv run python -I -X utf8 src/data/report_model_figures.py

1. Сводка скользящей проверки (тренд lin): прошлый год, среднее 5 лет, тренд, ансамбль погоды.
2. Перестановочная важность групп признаков (переменная — все её месяцы; месяц — все переменные),
   модель обучена на сезонах ≤ 2021, оценка на 2022–2025.
3. Калибровка интервалов: сценарный 10–90 % интервал × эмпирические квантили ошибки модели в конце сезона
   (по остальным годам), доля попаданий по датам прогноза.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import MAIN, SEQ, SERIES, TAB, INK, plt, savefig  # noqa: E402
from model_weather import (CROPS, OUT, VARS, WINTER_CROPS, Ensemble, add_trend, feature_cols,  # noqa: E402
                           load_panel)

ENS = "ens_ridge300_full+hgb_full"


def summary():
    e = pd.read_parquet(OUT / "experiments_predictions.parquet")
    e = e[(e.trend == "lin") & e.variant.isin(["trend_only", ENS])]
    b = pd.read_parquet(OUT / "predictions.parquet")
    b = b[(b.scheme == "rolling") & (b.trend == "lin") & (~b.ndvi) & b.model.isin(["last_year", "mean5"])]
    b = b.rename(columns={"model": "variant"})[["crop", "okato", "year", "y", "yhat", "variant", "area_tha"]]
    a = pd.concat([e[["crop", "okato", "year", "y", "yhat", "variant", "area_tha"]], b])
    a = a.dropna(subset=["yhat"])
    a["ae"] = (a.yhat - a.y).abs()
    a["ape"] = a.ae / a.y * 100
    names = {"last_year": "прошлый год", "mean5": "среднее 5 лет", "trend_only": "линейный тренд",
             ENS: "тренд × погода"}
    a["variant"] = a.variant.map(names)
    M = a.groupby(["crop", "variant"]).agg(MAE=("ae", "mean"), MAPE=("ape", "mean"), n=("ae", "size")).reset_index()
    M.to_csv(TAB / "model_summary_rolling.csv", index=False)
    mae = M.pivot(index="crop", columns="variant", values="MAE")[list(names.values())]
    mape = M.pivot(index="crop", columns="variant", values="MAPE")[list(names.values())]
    best_simple = mae[["прошлый год", "среднее 5 лет", "линейный тренд"]].min(axis=1)
    out = mae.round(3).astype(str) + " / " + mape.round(1).astype(str)
    out["выигрыш к лучшему простому, %"] = ((1 - mae["тренд × погода"] / best_simple) * 100).round(1)
    out.to_csv(TAB / "model_summary_rolling_table.csv")
    print(out.to_string())

    piv = mape.sort_values("линейный тренд")
    fig, ax = plt.subplots(figsize=(9.5, 5))
    h = 0.2
    for k, col in enumerate(piv.columns):
        ax.barh(np.arange(len(piv)) + (k - 1.5) * h, piv[col], height=h * 0.85, color=SERIES[k], label=col)
    ax.set_yticks(range(len(piv)), piv.index)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("MAPE по субъектам, % (скользящая проверка 2012–2025, прогноз в конце сезона)")
    ax.legend(frameon=False, fontsize=8, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=4)
    ax.set_title("Модель «тренд × погода» против простых бейзлайнов", pad=28)
    savefig(fig, "model_vs_baselines.png")


def importance():
    p = load_panel()
    q = add_trend(p, 2021, "lin")
    rng = np.random.default_rng(0)
    rows = []
    for c in ["1010400", "1010500", "1030100", "1080202", "3080000", "3100000", "3060100"]:
        cols = feature_cols(c)
        qc = q[q.crop_code == c]
        tr, te = qc[(qc.year <= 2021) & qc.r.notna()], qc[qc.year >= 2022]
        m = Ensemble().fit(tr[cols], tr.r)
        base = np.mean(np.abs(m.predict(te[cols]) - te.r))
        groups = {f"var:{v}": [x for x in cols if x.startswith(f"a_{v}_")] for v in VARS}
        groups |= {f"month:{mm}": [x for x in cols if x.startswith("a_") and x.endswith(f"_{mm}")] for mm in CROPS[c]}
        if c in WINTER_CROPS:
            groups["var:зима"] = ["a_tsoil_min_win", "a_cold20_win", "a_snow_win", "a_thaw_win", "tsoil_min_win"]
        groups["var:почва+климат"] = [x for x in cols if x.startswith(("soil_", "clim_"))]
        for g, gc in groups.items():
            if not gc:
                continue
            inc = []
            for _ in range(5):
                X = te[cols].copy()
                perm = rng.permutation(len(X))
                X[gc] = X[gc].values[perm]  # переставляем всю группу вместе
                inc.append(np.mean(np.abs(m.predict(X) - te.r)) - base)
            rows.append({"crop": MAIN[c], "group": g, "dMAE_r": np.mean(inc), "base_MAE_r": base})
    I = pd.DataFrame(rows)
    I["rel"] = I.dMAE_r / I.base_MAE_r * 100
    I.to_csv(TAB / "model_importance.csv", index=False)
    v = I[I.group.str.startswith("var:")].assign(g=lambda d: d.group.str[4:]).pivot(index="g", columns="crop",
                                                                                     values="rel")
    labels = {"tmean": "T средняя", "tmax": "T макс", "tmin": "T мин", "prec": "осадки", "et0": "ET0",
              "cwb": "P − ET0", "rad": "радиация", "vpd": "дефицит влажности", "sm0_7": "влага 0–7",
              "sm7_28": "влага 7–28", "sm28_100": "влага 28–100", "hot30": "дни > 30 °C", "hot35": "дни > 35 °C",
              "gdd5": "сумма T > 5", "frost": "заморозки", "зима": "зима (почва, морозы)",
              "почва+климат": "почва и климат"}
    v.index = [labels.get(i, i) for i in v.index]
    v = v.loc[v.max(axis=1).sort_values(ascending=False).index]
    fig, ax = plt.subplots(figsize=(9, 6))
    im = ax.imshow(v.clip(lower=0).values, cmap=SEQ, aspect="auto")
    ax.set_xticks(range(len(v.columns)), v.columns, rotation=30, ha="right")
    ax.set_yticks(range(len(v)), v.index)
    ax.grid(False)
    for (i, k), val in np.ndenumerate(v.values):
        if not np.isnan(val) and val >= 1:
            ax.text(k, i, f"{val:.0f}", ha="center", va="center", fontsize=7,
                    color="white" if val > np.nanmax(v.values) * 0.6 else INK)
    fig.colorbar(im, ax=ax, label="рост ошибки при перемешивании, %")
    ax.set_title("Какие погодные переменные важны (перестановочная важность, тест 2022–2025)")
    savefig(fig, "model_importance_vars.png")
    print(v.round(1).to_string())
    mo = I[I.group.str.startswith("month:")].assign(g=lambda d: d.group.str[6:]).pivot(index="crop", columns="g",
                                                                                        values="rel")
    print(mo.round(1).to_string())


def intervals():
    L = pd.read_parquet(OUT / "leadtime_predictions_ens_lin.parquet")
    end = L[L.cutoff == "конец"].assign(ratio=lambda d: d.y / d.yhat)
    rows = []
    for (crop, yr), g in L.groupby(["crop", "year"]):
        pool = end[(end.crop == crop) & (end.year != yr)].ratio
        lo, hi = pool.quantile(0.1), pool.quantile(0.9)
        for cut, gg in g.groupby("cutoff"):
            # ширина сценариев и ошибки модели складываются в квадратуре (в долях прогноза)
            s_lo, s_hi = 1 - gg.q10 / gg.yhat, gg.q90 / gg.yhat - 1
            lo_c = gg.yhat * (1 - np.sqrt(s_lo ** 2 + (1 - lo) ** 2))
            hi_c = gg.yhat * (1 + np.sqrt(s_hi ** 2 + (hi - 1) ** 2))
            rows.append(pd.DataFrame({"crop": crop, "year": yr, "cutoff": cut,
                                      "in80": (gg.y >= lo_c) & (gg.y <= hi_c),
                                      "width_pct": (hi_c - lo_c) / gg.yhat * 100}))
    C = pd.concat(rows)
    order = ["1 апр", "1 мая", "1 июня", "1 июля", "1 авг", "1 сен", "конец"]
    cov = C.groupby(["crop", "cutoff"]).agg(cover80=("in80", "mean"), width=("width_pct", "median")).reset_index()
    cov["cutoff"] = pd.Categorical(cov.cutoff, order)
    cov.to_csv(TAB / "intervals_calibrated.csv", index=False)
    print(cov.pivot(index="crop", columns="cutoff", values="cover80").round(2))
    print(cov.pivot(index="crop", columns="cutoff", values="width").round(0))


if __name__ == "__main__":
    summary()
    importance()
    intervals()
