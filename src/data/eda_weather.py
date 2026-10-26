"""Связь отклонения урожайности от тренда с месячными погодными аномалиями и NDVI; покрытие погоды и NDVI.

Запуск (после build_features.py):
    uv run python -I -X utf8 src/data/eda_weather.py

Отклонение r = y / тренд − 1, тренд — линейный по 2001–2024 в каждом регионе (описательный анализ, не прогноз).
Корреляция Пирсона r с аномалией признака, по всем парам «регион × год» культуры.
Выход: reports/tables/weather_corr.csv, reports/figures/weather_corr_*.png, reports/tables/ndvi_coverage.csv.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import DIV, INK, MAIN, PROC_ROOT, TAB, plt, savefig  # noqa: E402
from model_weather import add_trend, load_panel  # noqa: E402

SHOW = ["1010400", "1010500", "1030100", "1080202", "3080000", "3100000", "3060100", "4010000"]
MONTHS = ["p09", "p10", "p11", "p12", "01", "02", "03", "04", "05", "06", "07", "08", "09"]
VARS = {"cwb": "водный баланс P−ET0", "hot30": "дни с Tmax > 30 °C", "sm28_100": "влажность почвы 28–100 см",
        "tmean": "средняя температура", "prec": "осадки"}


def main():
    p = load_panel()
    p = p[p.year <= 2024]
    q = add_trend(p, 2024, "lin")
    rows = []
    for c in SHOW:
        qc = q[q.crop_code == c]
        for v in VARS:
            for m in MONTHS:
                col = f"a_{v}_{m}"
                if col in qc and qc[col].notna().sum() > 100:
                    rows.append({"crop": MAIN[c], "var": v, "month": m, "corr": qc.r.corr(qc[col]), "n": qc[col].notna().sum()})
        for col in ["a_ndvi_05", "a_ndvi_06", "a_ndvi_07", "a_ndvi_08", "a_ndvi_max_5_8", "a_tsoil_min_win",
                    "a_cold20_win", "a_snow_win"]:
            rows.append({"crop": MAIN[c], "var": col, "month": "", "corr": qc.r.corr(qc[col]), "n": qc[col].notna().sum()})
    C = pd.DataFrame(rows)
    C.to_csv(TAB / "weather_corr.csv", index=False)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), sharey=True)
    for ax, v in zip(axes, ["cwb", "hot30", "sm28_100"]):
        piv = C[C["var"] == v].pivot(index="crop", columns="month", values="corr")
        piv = piv.reindex(index=[MAIN[c] for c in SHOW], columns=[m for m in MONTHS if m in piv.columns])
        im = ax.imshow(piv.values, cmap=DIV.reversed() if v != "hot30" else DIV.reversed(), vmin=-0.6, vmax=0.6,
                       aspect="auto")
        ax.set_xticks(range(len(piv.columns)), [m.replace("p", "пр.") for m in piv.columns], fontsize=7, rotation=90)
        ax.set_yticks(range(len(piv)), piv.index)
        ax.grid(False)
        for (i, k), val in np.ndenumerate(piv.values):
            if not np.isnan(val) and abs(val) >= 0.25:
                ax.text(k, i, f"{val:.2f}".replace("0.", ".").replace("-.", "−."), ha="center", va="center",
                        fontsize=6, color=INK)
        ax.set_title(VARS[v])
    fig.colorbar(im, ax=axes, shrink=0.8, label="корреляция с отклонением от тренда")
    fig.suptitle("Отклонение урожайности от тренда и месячные аномалии погоды (субъекты, 2001–2024)", fontsize=10)
    savefig(fig, "weather_corr_months.png")

    nd = C[C["var"].str.startswith(("a_ndvi", "a_tsoil", "a_cold", "a_snow"))].pivot(index="crop", columns="var",
                                                                                      values="corr")
    pd.set_option("display.width", 250)
    print(nd.round(2))
    top = C[C["var"].isin(VARS)].assign(a=lambda d: d["corr"].abs()).sort_values("a", ascending=False)
    print(top.groupby("crop").head(4).sort_values(["crop", "a"], ascending=[True, False]).round(2).to_string(index=False))

    # покрытие NDVI: доля годных значений по месяцам
    n = pd.read_parquet(PROC_ROOT / "ndvi" / "point_ndvi.parquet")
    n["month"] = n.date.dt.month
    cov = n.groupby("month").ndvi.apply(lambda s: s.notna().mean()).round(3)
    cov.to_csv(TAB / "ndvi_coverage.csv")
    print("NDVI: доля годных значений по месяцам\n", cov.to_dict())


if __name__ == "__main__":
    main()
