"""Сверка урожайности с валовым сбором, оценка урожайности 2025 по сбору и посевной, стык цен 31454/57693.

Запуск (после parse_emiss.py для 30950, 31328, 31533, 31454, 57693):
    uv run python -I -X utf8 src/data/eda_gross_prices.py

Доля убранной площади h = сбор / (урожайность × посевная): тыс. ц / (ц/га × тыс. га).
h > 1 — урожайность не согласуется со сбором и посевной; h заметно < 1 — гибель посевов.
Оценка 2025: y = сбор / (посевная × h̃), где h̃ — медиана h региона за 5 предыдущих лет.
Выход: reports/tables/harvest_share*.csv, data/processed/yield_proxy.parquet, reports/figures/*.png.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import (CAT_ALL, INK2, MAIN, MIN_AREA, PROC_ROOT, SERIES, TAB, area_reg, load, plt, rf_series,
                    savefig)

area_reg = area_reg()

KEYS = ["okato", "crop_code", "year"]


def subj(df, cat=CAT_ALL):
    return df[(df.region_level == "subject") & (df.farm_category_code == cat) & df.value.notna()
              & (df.value > 0)][KEYS + ["region", "fo", "value"]]


Y, G, A = subj(load("31533")), subj(load("30950")), subj(load("31328"))
J = (G.rename(columns={"value": "gross"})
     .merge(A[KEYS + ["value"]].rename(columns={"value": "sown"}), on=KEYS)
     .merge(Y[KEYS + ["value"]].rename(columns={"value": "yld"}), on=KEYS, how="left"))
J = J[J.crop_code.isin(MAIN)]
J["crop"] = J.crop_code.map(MAIN)
J["h"] = J.gross / (J.yld * J.sown)
J["yield_per_sown"] = J.gross / J.sown  # ц/га с посевной
J = J.join(area_reg, on=["crop_code", "okato"])

# ---------------------------------------------------------------- доля убранной площади
h = J[J.yld.notna() & J.year.between(2000, 2024)]
big = h[h.area_tha >= MIN_AREA]
tab = big.groupby("crop").h.describe(percentiles=[.05, .5, .95])[["count", "5%", "50%", "95%"]]
tab["share_h_gt_1.02"] = big.groupby("crop").h.apply(lambda s: (s > 1.02).mean())
tab["share_h_lt_0.8"] = big.groupby("crop").h.apply(lambda s: (s < 0.8).mean())
tab.round(3).to_csv(TAB / "harvest_share_by_crop.csv")
print("Доля убранной площади (регионы ≥5 тыс. га):\n", tab.round(3))

by_year = big.groupby(["year", "crop"]).h.median().unstack()
by_year.round(3).to_csv(TAB / "harvest_share_by_year.csv")
print(by_year.loc[[2010, 2012, 2018, 2020, 2021, 2022, 2023, 2024]].round(3))

bad = big[(big.h > 1.05) | (big.h < 0.5)].sort_values("h")
bad[["crop", "region", "year", "gross", "sown", "yld", "h", "area_tha"]].to_csv(TAB / "harvest_share_anomalies.csv",
                                                                                index=False)
print("аномалий h>1.05 или <0.5:", len(bad), "из", len(big))

fig, ax = plt.subplots(figsize=(10, 4))
core = ["Пшеница озимая", "Пшеница яровая", "Ячмень яровой", "Кукуруза на зерно", "Подсолнечник", "Соя"]
for k, c in enumerate(core):
    ax.plot(by_year.index, by_year[c], color=SERIES[k], label=c, marker="o", ms=3)
ax.axhline(1, color=INK2, lw=1)
ax.set_ylabel("сбор / (урожайность × посевная)")
ax.set_title("Медианная доля убранной площади по регионам (≥5 тыс. га), все категории")
ax.legend(frameon=False, fontsize=8, ncol=3)
savefig(fig, "harvest_share_by_year.png")

# ---------------------------------------------------------------- оценка урожайности по сбору
J = J.sort_values("year")
J["h_med5"] = (J.groupby(["crop_code", "okato"]).h
               .transform(lambda s: s.shift(1).rolling(5, min_periods=3).median()))
J["yld_proxy"] = J.yield_per_sown / J.h_med5
J["yld_proxy"] = J.yld_proxy.where(J.h_med5.notna(), J.yield_per_sown)

# качество прокси там, где урожайность известна
chk = J[J.yld.notna() & J.year.between(2015, 2024) & (J.area_tha >= MIN_AREA)].copy()
chk["ape"] = (chk.yld_proxy / chk.yld - 1).abs() * 100
chk["ape_raw"] = (chk.yield_per_sown / chk.yld - 1).abs() * 100
q = chk.groupby("crop").agg(n=("ape", "size"), MdAPE=("ape", "median"), p90=("ape", lambda s: s.quantile(.9)),
                            MdAPE_raw=("ape_raw", "median"))
q.round(2).to_csv(TAB / "yield_proxy_quality.csv")
print("Качество оценки урожайности по сбору/посевной (2015–2024):\n", q.round(2))

out = J[["okato", "region", "fo", "crop_code", "crop", "year", "gross", "sown", "yld", "h", "h_med5",
         "yield_per_sown", "yld_proxy"]].copy()
out["yld_proxy_t_ha"] = out.yld_proxy / 10
out.to_parquet(PROC_ROOT / "yield_proxy.parquet", index=False)
y25 = out[out.year == 2025]
print("2025: регионов с оценкой урожайности:\n", y25.groupby("crop").okato.nunique())

# РФ 2025 по прокси: сумма сборов / сумма (посевная × h̃)
rf25 = y25.dropna(subset=["h_med5"]).groupby("crop").apply(
    lambda g: (g.gross.sum() / (g.sown * g.h_med5).sum()) / 10, include_groups=False)
rf24 = rf_series(load("31533")[lambda d: d.farm_category_code == CAT_ALL])
rf24 = rf24[rf24.crop_code.isin(MAIN) & rf24.year.isin([2023, 2024])].pivot_table(
    index="crop_code", columns="year", values="value") / 10
rf24.index = rf24.index.map(MAIN)
rfc = rf24.join(rf25.rename("2025_proxy")).round(2)
rfc.to_csv(TAB / "rf_yield_2025_proxy.csv")
print(rfc)

# ---------------------------------------------------------------- цены: стык 31454 и 57693
P1 = load("31454")
P2 = load("57693")
PAIRS = {"Пшеница": ("Пшеница", "Пшеница"), "Ячмень": ("Ячмень", "Ячмень"), "Кукуруза": ("Кукуруза", "Кукуруза"),
         "Подсолнечник": ("Семена подсолнечника", "Семена подсолнечника"), "Соя": ("Бобы соевые", "Бобы соевые"),
         "Сахарная свёкла": ("Свекла сахарная", "Корнеплоды свеклы сахарной"), "Картофель": ("Картофель", "Картофель"),
         "Рапс": ("Семена рапса", "Семена рапса")}
rows, cov = [], []
for name, (a, b) in PAIRS.items():
    for src, df, col, prod in (("31454", P1, "s_OKPD", a), ("57693", P2, "s_OKPD2", b)):
        x = df[(df[col] == prod) & (df.period == "январь-декабрь") & df.value.notna()]
        r = rf_series(x).groupby("year").value.mean()
        for yr, v in r.items():
            rows.append({"crop": name, "source": src, "year": int(yr), "price_rub_t": v})
        s = x[x.region_level == "subject"]
        cov.append({"crop": name, "source": src, "n_regions": s.okato.nunique(),
                    "years": f"{int(s.year.min())}–{int(s.year.max())}" if len(s) else "—"})
PR = pd.DataFrame(rows)
PR.pivot_table(index="year", columns="crop", values="price_rub_t").round(0).to_csv(TAB / "prices_rf_1999_2026.csv")
pd.DataFrame(cov).to_csv(TAB / "prices_coverage_31454_57693.csv", index=False)
print(pd.DataFrame(cov))

# 2026 — годовой цены ещё нет; берём январь-сентябрь
fig, ax = plt.subplots(figsize=(10, 4.2))
for k, c in enumerate(["Пшеница", "Ячмень", "Кукуруза", "Подсолнечник", "Соя"]):
    s = PR[PR.crop == c].sort_values("year")
    ax.plot(s.year, s.price_rub_t / 1000, color=SERIES[k], label=c, marker="o", ms=3)
ax.axvline(2016.5, color=INK2, lw=1, ls="--")
ax.text(2016.6, ax.get_ylim()[1] * 0.95, "31454 | 57693", color=INK2, fontsize=8)
ax.set_ylabel("тыс. руб./т")
ax.set_title("Средние цены производителей по РФ за год (январь–декабрь)")
ax.legend(frameon=False, fontsize=8, ncol=5)
savefig(fig, "prices_rf_1999_2025.png")
