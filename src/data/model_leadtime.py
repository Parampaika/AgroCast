"""Прогноз по ходу сезона: точность и разброс сценариев в зависимости от даты прогноза.

Запуск (после model_weather.py):
    uv run python -I -X utf8 src/data/model_leadtime.py [hgb|ridge] [lin|lin10]

Для даты прогноза D (1 апреля, 1 мая, 1 июня, 1 июля, 1 августа, конец сезона) месяцы до D известны,
а месяцы начиная с D заменяются аномалиями каждого прошлого сезона (2001…t−1) — это погодные сценарии,
как в калькуляторе. Прогноз = тренд × (1 + среднее по сценариям); интервал — 10–90 % по сценариям.
Проверка скользящая: t = 2012…2025, обучение и тренд по сезонам ≤ t−1.
Выход: reports/tables/leadtime_metrics.csv, data/processed/model/leadtime_predictions.parquet,
       reports/figures/leadtime_mae.png.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import MAIN, SERIES, TAB, plt, savefig  # noqa: E402
from model_weather import CROPS, OUT, VARS, WINTER_CROPS, add_trend, feature_cols, load_panel, make_models  # noqa: E402

CUTOFFS = {"1 апр": 4, "1 мая": 5, "1 июня": 6, "1 июля": 7, "1 авг": 8, "1 сен": 9, "конец": 13}


def month_num(tag: str) -> int:
    """'p09' → 9 − 12 = −3 (прошлый год), '05' → 5."""
    return int(tag[1:]) - 12 if tag.startswith("p") else int(tag)


def unknown_cols(crop: str, cutoff: int) -> list[str]:
    cols = [f"a_{v}_{m}" for v in VARS for m in CROPS[crop] if month_num(m) >= cutoff]
    if crop in WINTER_CROPS and cutoff <= 3:
        cols += ["a_tsoil_min_win", "a_cold20_win", "a_snow_win", "a_thaw_win", "tsoil_min_win"]
    return cols


def main(model_name: str = "hgb", kind: str = "lin10"):
    p = load_panel()
    recs = []
    for t in range(2012, 2026):
        q = add_trend(p, t - 1, kind)
        for c in CROPS:
            cols = feature_cols(c)
            qc = q[q.crop_code == c]
            tr = qc[(qc.year <= t - 1) & qc.r.notna()]
            te = qc[qc.year == t]
            if te.empty or len(tr) < 100:
                continue
            m = make_models()[model_name]
            m.fit(tr[cols], tr.r)
            for cname, cut in CUTOFFS.items():
                unk = unknown_cols(c, cut)
                if not unk:
                    preds = np.repeat(m.predict(te[cols])[:, None], 1, axis=1)
                else:
                    scen_years = sorted(tr.year.unique())
                    preds = []
                    for sy in scen_years:
                        X = te[cols].copy()
                        src = qc[qc.year == sy].set_index("okato")[unk]
                        # сценарий — аномалии того же региона в сезон sy; если региона нет — среднее по сезону
                        repl = src.reindex(te.okato)
                        repl = repl.fillna(src.mean())
                        X[unk] = repl.values
                        preds.append(m.predict(X))
                    preds = np.column_stack(preds)
                for i, (_, row) in enumerate(te.iterrows()):
                    pr = preds[i]
                    recs.append({"crop": MAIN[c], "okato": row.okato, "year": t, "cutoff": cname, "y": row.y,
                                 "trend_val": row.trend, "area_tha": row.area_tha,
                                 "yhat": row.trend * (1 + pr.mean()),
                                 "q10": row.trend * (1 + np.quantile(pr, 0.1)),
                                 "q90": row.trend * (1 + np.quantile(pr, 0.9))})
        print(t, flush=True)
    L = pd.DataFrame(recs)
    L.to_parquet(OUT / f"leadtime_predictions_{model_name}_{kind}.parquet", index=False)
    L["ae"] = (L.yhat - L.y).abs()
    L["ape"] = L.ae / L.y * 100
    L["in80"] = (L.y >= L.q10) & (L.y <= L.q90)
    L["width80"] = (L.q90 - L.q10) / L.trend_val * 100
    tr_only = (L.trend_val - L.y).abs()
    L["ae_trend"] = tr_only
    M = L.groupby(["crop", "cutoff"]).agg(MAE=("ae", "mean"), MAPE=("ape", "mean"), MAE_trend=("ae_trend", "mean"),
                                          cover80=("in80", "mean"), width80_pct=("width80", "median")).reset_index()
    M["skill_vs_trend"] = 1 - M.MAE / M.MAE_trend
    M["cutoff"] = pd.Categorical(M.cutoff, list(CUTOFFS))
    M = M.sort_values(["crop", "cutoff"])
    M.to_csv(TAB / f"leadtime_metrics_{model_name}_{kind}.csv", index=False)
    pd.set_option("display.width", 250)
    print(M.pivot(index="crop", columns="cutoff", values="skill_vs_trend").round(3))
    print(M.pivot(index="crop", columns="cutoff", values="MAPE").round(1))
    print(M.pivot(index="crop", columns="cutoff", values="cover80").round(2))
    print(M.pivot(index="crop", columns="cutoff", values="width80_pct").round(1))

    fig, ax = plt.subplots(figsize=(9, 4.5))
    piv = M.pivot(index="cutoff", columns="crop", values="skill_vs_trend")
    show = ["Пшеница озимая", "Пшеница яровая", "Ячмень яровой", "Кукуруза на зерно", "Подсолнечник", "Соя"]
    for k, cr in enumerate(show):
        if cr in piv:
            ax.plot(range(len(piv)), piv[cr] * 100, color=SERIES[k], marker="o", ms=4, label=cr)
    ax.axhline(0, color="#52514e", lw=1)
    ax.set_xticks(range(len(piv)), piv.index)
    ax.set_ylabel("выигрыш против тренда по MAE, %")
    ax.set_title("Насколько погода улучшает прогноз в зависимости от даты (скользящая проверка 2012–2025)")
    ax.legend(frameon=False, fontsize=8, ncol=3)
    savefig(fig, f"leadtime_skill_{model_name}_{kind}.png")


if __name__ == "__main__":
    main(*sys.argv[1:])
