"""Прогноз урожайности 2026 по погоде сезона (до 22.10.2026) и сверка с оперативными данными ЕМИСС.

Запуск (после model_weather.py):
    uv run python -I -X utf8 src/data/forecast_2026.py [hgb|ridge] [lin|lin10]

Модель обучается на всех сезонах ≤ 2025 (2025 — урожайность, восстановленная по сбору), тренд — по ≤ 2025.
Сверка: 33978 «намолочено с 1 га» в СХО на 1 октября. Оперативный срез — это не итог: к 1 октября убрано
не всё, и СХО ≠ все категории. Поэтому сначала по 2023–2025 считается медианное отношение
итог (все категории; 2025 — по сбору) / оперативный срез на 1 октября для каждого региона, и 2026 сравнивается
с «оперативным × это отношение». Зерно: модельная оценка для «зерновых без кукурузы» —
среднее по пшенице оз./яр., ячменю и овсу с весами посевной 2025 г.
Выход: reports/tables/forecast_2026*.csv, reports/figures/forecast_2026_vs_oper.png.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import CAT_ALL, INK2, MAIN, PROC_ROOT, SERIES, SURF, TAB, load, plt, savefig  # noqa: E402
from model_weather import CROPS, add_trend, feature_cols, load_panel, make_models  # noqa: E402

GRAIN = ["1010400", "1010500", "1030100", "1060000"]
OPER = {"Подсолнечник": "3080000", "Сахарная свекла": "3060100", "Картофель": "4010000",
        "Зерновые и зернобобовые культуры (без кукурузы)": "GRAIN"}


def sown(year: int) -> pd.Series:
    a = load("31328")
    a = a[(a.region_level == "subject") & (a.farm_category_code == CAT_ALL) & (a.year == year) & a.value.notna()]
    return a.groupby(["crop_code", "okato"]).value.sum()


def main(model_name: str = "hgb", kind: str = "lin10"):
    p = load_panel()
    f = pd.read_parquet(PROC_ROOT / "features" / "region_season.parquet")
    q = add_trend(p, 2025, kind)
    # строки 2026: тренд по ≤ 2025, признаки 2026
    tr_par = q.groupby(["crop_code", "okato"]).apply(
        lambda g: np.polyfit(g.year[g.year > (2015 if kind == "lin10" else 0)],
                             g.y[g.year > (2015 if kind == "lin10" else 0)], 1), include_groups=False)
    base = q.drop_duplicates(["crop_code", "okato"])[["crop_code", "okato", "region", "fo", "area_tha"]]
    base = base.assign(year=2026).merge(f, on=["okato", "year"], how="left")
    base["trend"] = [np.polyval(tr_par[(c, o)], 2026) for c, o in zip(base.crop_code, base.okato)]

    preds = []
    for c in CROPS:
        cols = feature_cols(c)
        tr = q[(q.crop_code == c) & q.r.notna()]
        m = make_models()[model_name]
        m.fit(tr[cols], tr.r)
        b = base[base.crop_code == c].copy()
        b["r_hat"] = m.predict(b[cols])
        b["yhat"] = b.trend * (1 + b.r_hat)
        preds.append(b[["crop_code", "okato", "region", "fo", "area_tha", "trend", "r_hat", "yhat"]])
    P = pd.concat(preds)
    P["crop"] = P.crop_code.map(MAIN)
    P.round(3).to_csv(TAB / "forecast_2026_regions.csv", index=False)

    # РФ по модельным регионам, веса — посевная 2025
    w25 = sown(2025)
    P["w"] = [w25.get((c, o), np.nan) for c, o in zip(P.crop_code, P.okato)]
    P["w"] = P.w.fillna(P.area_tha)
    hist = p[p.year.isin([2023, 2024, 2025])].copy()
    hist["w"] = [w25.get((c, o), np.nan) for c, o in zip(hist.crop_code, hist.okato)]
    hist["w"] = hist.w.fillna(hist.area_tha)
    rf = P.groupby("crop").apply(lambda g: pd.Series({
        "trend_2026": np.average(g.trend, weights=g.w), "forecast_2026": np.average(g.yhat, weights=g.w),
        "n_regions": len(g)}), include_groups=False)
    for yr in (2023, 2024, 2025):
        h = hist[hist.year == yr]
        rf[f"y_{yr}"] = h.groupby(h.crop_code.map(MAIN)).apply(lambda g: np.average(g.y, weights=g.w),
                                                                include_groups=False)
    rf["vs_trend_pct"] = (rf.forecast_2026 / rf.trend_2026 - 1) * 100
    rf.round(3).to_csv(TAB / "forecast_2026_rf.csv")
    pd.set_option("display.width", 250)
    print(rf.round(2))

    # ---------- сверка с оперативными данными
    op = load("33978")
    op = op[(op.region_level == "subject") & (op.period == "на 1 октября")][["okato", "crop", "year", "value"]]
    op["key"] = op.crop.map(OPER)
    op["oper"] = op.value / 10
    fin = p[["okato", "crop_code", "year", "y"]].rename(columns={"crop_code": "key"})
    # итоговое «зерно без кукурузы» как среднее GRAIN с весами посевной того же года
    g = p[p.crop_code.isin(GRAIN)].copy()
    sw = {yr: sown(yr) for yr in (2023, 2024, 2025)}
    g["w"] = [sw.get(yr, w25).get((c, o), np.nan) for yr, c, o in zip(g.year, g.crop_code, g.okato)]
    g = g.dropna(subset=["w"])
    gfin = g.groupby(["okato", "year"]).apply(lambda d: np.average(d.y, weights=d.w), include_groups=False)
    gfin = gfin.rename("y").reset_index().assign(key="GRAIN")
    fin = pd.concat([fin, gfin])
    cal = op[op.year.isin([2023, 2024, 2025])].merge(fin, on=["okato", "key", "year"])
    cal["ratio"] = cal.y / cal.oper
    ratio = cal.groupby(["key", "okato"]).ratio.median()
    ratio_all = cal.groupby("key").ratio.median()
    print("медианное отношение итог / оперативный на 1 октября (2023–2025):\n", ratio_all.round(3))

    # модельный прогноз «зерна» 2026
    pg = P[P.crop_code.isin(GRAIN)].copy()
    pg["w2"] = [w25.get((c, o), np.nan) for c, o in zip(pg.crop_code, pg.okato)]
    pgrain = pg.dropna(subset=["w2"]).groupby("okato").apply(
        lambda d: pd.Series({"yhat": np.average(d.yhat, weights=d.w2), "trend": np.average(d.trend, weights=d.w2)}),
        include_groups=False).reset_index().assign(key="GRAIN")
    pm = pd.concat([P.rename(columns={"crop_code": "key"})[["okato", "key", "yhat", "trend"]], pgrain])
    o26 = op[op.year == 2026].merge(pm, on=["okato", "key"])
    o26["ratio"] = [ratio.get((k, o), ratio_all.get(k)) for k, o in zip(o26.key, o26.okato)]
    o26["oper_adj"] = o26.oper * o26.ratio
    o26 = o26.dropna(subset=["oper_adj"])
    o26.round(3).to_csv(TAB / "forecast_2026_vs_oper.csv", index=False)

    def summ(d, col):
        e = (d[col] / d.oper_adj - 1) * 100
        return pd.Series({"n": len(d), "MdAPE_vs_oper_adj": e.abs().median(), "median_err_pct": e.median()})
    s = o26.groupby("crop").apply(lambda d: pd.concat([summ(d, "yhat").add_prefix("model_"),
                                                       summ(d, "trend").add_prefix("trend_")]),
                                  include_groups=False)
    s.round(2).to_csv(TAB / "forecast_2026_vs_oper_summary.csv")
    print("2026: модель и тренд против оперативных × отношение:\n", s.round(1))

    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, (cr, d) in zip(axes, [(c, o26[o26.crop == c]) for c in
                                  ["Зерновые и зернобобовые культуры (без кукурузы)", "Подсолнечник",
                                   "Сахарная свекла"]]):
        ax.scatter(d.oper_adj, d.trend, s=16, color=SERIES[1], label="тренд", edgecolor=SURF, linewidth=0.6)
        ax.scatter(d.oper_adj, d.yhat, s=16, color=SERIES[0], label="тренд × погода", edgecolor=SURF, linewidth=0.6)
        lim = [0, max(d.oper_adj.max(), d.yhat.max(), d.trend.max()) * 1.05]
        ax.plot(lim, lim, color=INK2, lw=1)
        ax.set_title(cr.replace(" культуры (без кукурузы)", " (без кукурузы)"))
        ax.set_xlabel("оперативные 1.10.2026 × поправка, т/га")
    axes[0].set_ylabel("прогноз, т/га")
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Прогноз 2026 по погоде сезона против оперативных данных ЕМИСС (33978, СХО)", fontsize=10)
    fig.tight_layout()
    savefig(fig, "forecast_2026_vs_oper.png")


if __name__ == "__main__":
    main(*sys.argv[1:])
