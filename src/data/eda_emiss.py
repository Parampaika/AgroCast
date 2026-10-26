"""EDA выгрузок ЕМИСС: покрытие, согласованность, трендовые бейзлайны, остаточная дисперсия.

Запуск (после parse_emiss.py):
    uv run python -I -X utf8 src/data/eda_emiss.py

Пишет таблицы в reports/tables/, графики в reports/figures/, ключевые числа — в stdout.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed" / "emiss"
FIG = ROOT / "reports" / "figures"
TAB = ROOT / "reports" / "tables"
FIG.mkdir(parents=True, exist_ok=True)
TAB.mkdir(parents=True, exist_ok=True)

# Палитра (категориальная, фиксированный порядок) и последовательная шкала
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
SEQ = LinearSegmentedColormap.from_list("seq", ["#f0efec", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
DIV = LinearSegmentedColormap.from_list("div", ["#2a78d6", "#f0efec", "#e34948"])
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 9,
    "axes.titlesize": 10, "axes.titleweight": "bold", "lines.linewidth": 2,
})

CAT_ALL, CAT_SHO = "1", "2"
CATS = {CAT_ALL: "все категории", CAT_SHO: "с/х организации"}

# Основные культуры: код 31533 → короткое имя
MAIN = {
    "1010400": "Пшеница озимая",
    "1010500": "Пшеница яровая",
    "1010401": "Пшеница (оз.+яр.)",
    "1030100": "Ячмень яровой",
    "1080202": "Кукуруза на зерно",
    "3080000": "Подсолнечник",
    "3100000": "Соя",
    "3060100": "Сахарная свёкла",
    "4010000": "Картофель",
    "3130200": "Рапс яровой",
    "1060000": "Овёс",
    "1020200": "Рожь озимая",
    "2010000": "Горох",
    "1120000": "Гречиха",
}
CORE = ["1010400", "1010500", "1030100", "1080202", "3080000", "3100000", "3060100", "4010000"]

TRAIN_END, TEST_YEARS = 2021, [2022, 2023, 2024]
Y0, Y1 = 2000, 2024
MIN_AREA = 5.0  # тыс. га, средняя посевная 2017–2021 — порог «значимого» региона


def load(ind: str) -> pd.DataFrame:
    return pd.read_parquet(PROC / f"{ind}.parquet")


def rf_series(df: pd.DataFrame) -> pd.DataFrame:
    """РФ: код 643 до 2022, «без новых субъектов» 643004.АГ с 2023."""
    a = df[(df.okato == "643") & (df.year <= 2022)]
    b = df[(df.okato == "643004.АГ") & (df.year >= 2023)]
    return pd.concat([a, b])


def longest_run(years: np.ndarray) -> int:
    if len(years) == 0:
        return 0
    ys = np.sort(np.unique(years))
    best = cur = 1
    for i in range(1, len(ys)):
        cur = cur + 1 if ys[i] == ys[i - 1] + 1 else 1
        best = max(best, cur)
    return best


def savefig(fig, name):
    fig.savefig(FIG / name, dpi=150, bbox_inches="tight")
    plt.close(fig)


out: dict[str, object] = {}

# ---------------------------------------------------------------- загрузка
Y = load("31533")
Y = Y[Y.value.notna()]
Ysub = Y[Y.region_level == "subject"].copy()
Ysub["t_ha"] = Ysub.value / 10
A = load("31328")
Asub = A[(A.region_level == "subject") & A.value.notna()]
reg = pd.read_csv(ROOT / "data" / "raw" / "geo" / "regions.csv", dtype={"okato": str})

out["31533_years"] = (int(Y.year.min()), int(Y.year.max()))
out["31533_subjects"] = Ysub.okato.nunique()
out["31533_crops"] = Y.crop_code.nunique()
out["2025_crops"] = sorted(Y[Y.year == 2025].crop.unique())
out["zeros_31533"] = int((Ysub.value == 0).sum())

# ---------------------------------------------------------------- площади: топ культур
area_mean = (Asub[(Asub.farm_category_code == CAT_ALL) & Asub.year.between(2020, 2024)]
             .groupby(["crop_code", "year"]).value.sum().groupby("crop_code").mean())
crop_names = Y.drop_duplicates("crop_code").set_index("crop_code").crop
crop_names = crop_names.combine_first(A.drop_duplicates("crop_code").set_index("crop_code").crop)

# Агрегаты и группы культур, которые не нужны в рейтинге
AGG = {"1000001", "17", "1040000", "2000000", "3200000", "3200001", "3000000", "4000000", "4020302",
       "5000000", "6", "8200000", "1010401", "1030201", "1020201", "5001500", "6000000", "5000601",
       "1070100", "8000100", "4020301", "3130000"}
area_rank = (area_mean.drop([c for c in area_mean.index if c in AGG], errors="ignore")
             .sort_values(ascending=False).rename("area_2020_24_tha").to_frame())
area_rank["crop"] = crop_names.reindex(area_rank.index)

# ---------------------------------------------------------------- покрытие
for cat in (CAT_ALL, CAT_SHO):
    d = Ysub[(Ysub.farm_category_code == cat) & (Ysub.value > 0)]
    m = d.pivot_table(index="crop_code", columns="year", values="okato", aggfunc="nunique").fillna(0)
    m.index = [crop_names.get(c, c) for c in m.index]
    m = m.loc[m.sum(axis=1).sort_values(ascending=False).index]
    m.to_csv(TAB / f"coverage_crop_year_cat{cat}.csv")
    top = m.head(40)
    fig, ax = plt.subplots(figsize=(11, 10))
    im = ax.imshow(top.values, aspect="auto", cmap=SEQ, vmin=0, vmax=85)
    ax.set_yticks(range(len(top)), [s[:55] for s in top.index], fontsize=7)
    ax.set_xticks(range(len(top.columns)), top.columns.astype(int), rotation=90, fontsize=7)
    ax.grid(False)
    ax.set_title(f"31533, урожайность: число субъектов с данными, {CATS[cat]} (топ-40 культур)")
    fig.colorbar(im, ax=ax, shrink=0.6, label="субъектов")
    savefig(fig, f"coverage_crop_year_cat{cat}.png")

# регион × год: сколько из CORE культур есть
d = Ysub[(Ysub.farm_category_code == CAT_ALL) & Ysub.crop_code.isin(CORE) & (Ysub.value > 0)]
m = d.pivot_table(index="region", columns="year", values="crop_code", aggfunc="nunique").fillna(0)
fo = Ysub.drop_duplicates("region").set_index("region").fo
m = m.loc[sorted(m.index, key=lambda r: (str(fo.get(r)), -m.loc[r].sum()))]
m.to_csv(TAB / "coverage_region_year_core.csv")
fig, ax = plt.subplots(figsize=(10, 15))
im = ax.imshow(m.values, aspect="auto", cmap=SEQ, vmin=0, vmax=len(CORE))
ax.set_yticks(range(len(m)), [f"{fo.get(r, '')} · {r[:38]}" for r in m.index], fontsize=6)
ax.set_xticks(range(len(m.columns)), m.columns.astype(int), rotation=90, fontsize=7)
ax.grid(False)
ax.set_title(f"Сколько из {len(CORE)} основных культур есть в 31533 (все категории)")
fig.colorbar(im, ax=ax, shrink=0.4, label="культур")
savefig(fig, "coverage_region_year_core.png")

# Длина непрерывного ряда по культуре × региону × категории
area_reg = (Asub[(Asub.farm_category_code == CAT_ALL) & Asub.year.between(2017, 2021)]
            .groupby(["crop_code", "okato"]).value.mean().rename("area_tha"))
area_2024 = (Asub[(Asub.farm_category_code == CAT_ALL) & (Asub.year == 2024)]
             .groupby(["crop_code", "okato"]).value.sum().rename("area_2024"))
runs = (Ysub[(Ysub.value > 0) & Ysub.year.between(Y0, Y1)]
        .groupby(["crop_code", "farm_category_code", "okato"]).year
        .agg(n_years="nunique", run=lambda s: longest_run(s.values), y_min="min", y_max="max").reset_index())
runs = runs.join(area_reg, on=["crop_code", "okato"]).join(area_2024, on=["crop_code", "okato"])
runs.to_parquet(TAB / "series_runs.parquet")

rows = []
for c in list(MAIN) + [x for x in area_rank.index[:25] if x not in MAIN]:
    r = runs[runs.crop_code == c]
    for cat in (CAT_ALL, CAT_SHO):
        rc = r[r.farm_category_code == cat]
        ok = rc[rc.run >= 15]
        tot24 = area_2024.loc[c].sum() if c in area_2024.index.get_level_values(0) else np.nan
        rows.append({
            "crop_code": c, "crop": crop_names.get(c, c), "cat": CATS[cat],
            "regions_any": rc.okato.nunique(),
            "regions_run15": ok.okato.nunique(),
            "regions_run15_area5": ok[ok.area_tha >= MIN_AREA].okato.nunique(),
            "share_area2024_run15": ok.area_2024.sum() / tot24 if tot24 else np.nan,
            "median_run": rc.run.median(),
        })
run_tab = pd.DataFrame(rows)
run_tab.to_csv(TAB / "series_run15_by_crop.csv", index=False)
area_rank = area_rank.join(
    run_tab[run_tab["cat"] == CATS[CAT_ALL]].set_index("crop_code")[["regions_run15", "regions_run15_area5", "share_area2024_run15"]])
area_rank.to_csv(TAB / "top_crops_by_area.csv")

# ---------------------------------------------------------------- RF ряды
rf = rf_series(Y[Y.farm_category_code == CAT_ALL])
fig, axes = plt.subplots(2, 4, figsize=(13, 5.5), sharex=True)
for ax, c in zip(axes.flat, CORE):
    s = rf[rf.crop_code == c].sort_values("year")
    ax.plot(s.year, s.value / 10, color=SERIES[0], marker="o", ms=3)
    tr = s[s.year <= TRAIN_END]
    if len(tr) > 3:
        b = np.polyfit(tr.year, tr.value / 10, 1)
        xx = np.arange(tr.year.min(), 2025)
        ax.plot(xx, np.polyval(b, xx), color=INK2, lw=1, ls="--")
    ax.axvspan(2021.5, 2024.5, color=GRID, alpha=0.6, lw=0)
    ax.set_title(MAIN[c])
    ax.set_ylabel("т/га")
fig.suptitle("Урожайность по РФ (все категории), т/га; пунктир — линейный тренд по 2000–2021, серым — тест 2022–2024",
             fontsize=10)
fig.tight_layout()
savefig(fig, "rf_yield_core.png")

# ---------------------------------------------------------------- согласованность
cons = {}
# (а) Агрегация: урожайность РФ vs средневзвешенная по субъектам с весами посевной площади
for c in CORE:
    ys = Ysub[(Ysub.farm_category_code == CAT_ALL) & (Ysub.crop_code == c)][["okato", "year", "value"]]
    ar = Asub[(Asub.farm_category_code == CAT_ALL) & (Asub.crop_code == c)][["okato", "year", "value"]]
    j = ys.merge(ar, on=["okato", "year"], suffixes=("_y", "_a"))
    w = j.groupby("year").apply(lambda g: np.average(g.value_y, weights=g.value_a) if g.value_a.sum() > 0 else np.nan,
                                include_groups=False)
    r = rf[rf.crop_code == c].set_index("year").value
    diff = ((w - r) / r * 100).dropna()
    cons[MAIN[c]] = {"aggr_median_abs_pct": diff.abs().median(), "aggr_max_abs_pct": diff.abs().max()}

# (б) Выбросы: скачки год к году и отклонения от медианы региона
d = Ysub[Ysub.crop_code.isin(MAIN) & Ysub.farm_category_code.isin([CAT_ALL, CAT_SHO])].sort_values("year").copy()
g = d.groupby(["crop_code", "farm_category_code", "okato"]).value
d["med"] = g.transform("median")
d["prev"] = g.shift(1)
d["ratio_med"] = d.value / d.med
d["ratio_prev"] = d.value / d.prev
flag = d[(d.value == 0) | (d.ratio_med > 3) | (d.ratio_med < 1 / 3)
         | (d.ratio_prev > 3) | (d.ratio_prev < 1 / 3)].copy()
flag["crop"] = flag.crop_code.map(MAIN)
flag = flag.join(area_reg, on=["crop_code", "okato"])
flag[["crop", "farm_category", "region", "year", "value", "prev", "med", "ratio_prev", "ratio_med", "area_tha"]] \
    .sort_values(["crop", "region", "year"]).to_csv(TAB / "outliers_main_crops.csv", index=False)
out["outliers_total"] = len(flag)
out["outliers_area5"] = int((flag.area_tha >= MIN_AREA).sum())
out["outliers_share"] = len(flag) / len(d)

# (в) Оперативные данные (на 1 ноября, с/х организации) vs итоговая урожайность
op = load("33978")
op = op[(op.period == "на 1 ноября") & (op.region_level == "subject")]
OPMAP = {"Подсолнечник": "3080000", "Сахарная свекла": "3060100", "Картофель": "4010000",
         "Зерновые и зернобобовые культуры (без кукурузы)": "1000001"}
op["crop_code"] = op.crop.map(OPMAP)
fin = Ysub[Ysub.farm_category_code == CAT_SHO][["okato", "crop_code", "year", "value"]]
j = op.merge(fin, on=["okato", "crop_code", "year"], suffixes=("_op", "_fin"))
j = j[(j.value_op > 0) & (j.value_fin > 0)]
j["err_pct"] = (j.value_op / j.value_fin - 1) * 100
op_tab = j.groupby(["crop", "year"]).err_pct.agg(n="size", median="median",
                                                 mae=lambda s: s.abs().median()).reset_index()
op_tab.to_csv(TAB / "oper_vs_final.csv", index=False)
fig, axes = plt.subplots(1, 4, figsize=(13, 3.4))
for ax, (cr, gg) in zip(axes, j.groupby("crop")):
    for k, (yr, g2) in enumerate(gg.groupby("year")):
        ax.scatter(g2.value_fin / 10, g2.value_op / 10, s=14, color=SERIES[k], label=str(yr),
                   edgecolor=SURF, linewidth=0.6)
    lim = [0, max(gg.value_fin.max(), gg.value_op.max()) / 10 * 1.05]
    ax.plot(lim, lim, color=INK2, lw=1)
    ax.set_title(cr.replace(" культуры", "").replace("(без кукурузы)", "(б/кукур.)")[:34])
    ax.set_xlabel("итог 31533, т/га")
axes[0].set_ylabel("оперативно на 1 ноября, т/га")
axes[0].legend(frameon=False, fontsize=8)
fig.suptitle("33978 (оперативные, с/х организации) против итоговой 31533 по субъектам", fontsize=10)
fig.tight_layout()
savefig(fig, "oper_vs_final.png")

# (г) Валовой сбор 30950 / (урожайность × посевная) — если валовой сбор уже есть за 2000+
G = load("30950")
G = G[(G.region_level == "subject") & (G.farm_category_code == CAT_ALL) & (G.year >= 2000)]
out["30950_years"] = sorted(load("30950").year.dropna().unique().astype(int).tolist())
if len(G):
    j = (G[["okato", "crop_code", "year", "value"]]
         .merge(Ysub[Ysub.farm_category_code == CAT_ALL][["okato", "crop_code", "year", "value"]],
                on=["okato", "crop_code", "year"], suffixes=("_g", "_y"))
         .merge(Asub[Asub.farm_category_code == CAT_ALL][["okato", "crop_code", "year", "value"]]
                .rename(columns={"value": "value_a"}), on=["okato", "crop_code", "year"]))
    # тыс. ц → harvested share = сбор / (урожайность × посевная)
    j["harv_share"] = j.value_g * 10 / (j.value_y * j.value_a)
    j.to_csv(TAB / "gross_vs_yield_area.csv", index=False)
    out["harv_share_summary"] = j.harv_share.describe().to_dict()

# ---------------------------------------------------------------- бейзлайны


def theil(x, y):
    sl, ic, *_ = stats.theilslopes(y, x)
    return sl, ic


def forecasts(s: pd.Series, t: int) -> dict[str, float]:
    """s: урожайность по годам (т/га); t — целевой год."""
    fix = s[s.index <= TRAIN_END]
    past = s[s.index < t]
    res = {}
    b = np.polyfit(fix.index, fix.values, 1)
    res["тренд лин. 2000–2021"] = np.polyval(b, t)
    f10 = fix[fix.index >= TRAIN_END - 9]
    if len(f10) >= 7:
        res["тренд лин. 10 лет"] = np.polyval(np.polyfit(f10.index, f10.values, 1), t)
    sl, ic = theil(fix.index.values.astype(float), fix.values)
    res["тренд Тейла–Сена"] = ic + sl * t
    res["тренд лин. скользящий (до t−1)"] = np.polyval(np.polyfit(past.index, past.values, 1), t)
    if t - 1 in s.index:
        res["прошлый год"] = s[t - 1]
    p5 = s[(s.index >= t - 5) & (s.index < t)]
    if len(p5) >= 3:
        res["среднее 5 лет"] = p5.mean()
    return res


def eligible(r: pd.Series, crop: str) -> bool:
    min_train = 12 if crop == "1010401" else 15  # пшеница всего — только с 2007
    tr = r[(r.index >= Y0) & (r.index <= TRAIN_END)]
    return len(tr) >= min_train and all(t in r.index for t in TEST_YEARS)


recs = []
for cat in (CAT_ALL, CAT_SHO):
    dd = Ysub[(Ysub.farm_category_code == cat) & Ysub.crop_code.isin(MAIN) & (Ysub.value > 0)]
    for (c, ok), g in dd.groupby(["crop_code", "okato"]):
        s = g.set_index("year").t_ha.sort_index()
        s.index = s.index.astype(int)
        s = s[s.index.isin(range(Y0, Y1 + 1))]
        if not eligible(s, c):
            continue
        ar = area_reg.get((c, ok), np.nan)
        for t in TEST_YEARS:
            for m, v in forecasts(s, t).items():
                recs.append({"cat": CATS[cat], "crop_code": c, "crop": MAIN[c], "okato": ok, "year": t,
                             "method": m, "y": s[t], "yhat": v, "area_tha": ar})
B = pd.DataFrame(recs)
B["err"] = B.yhat - B.y
B["ape"] = (B.err.abs() / B.y) * 100
B.to_parquet(TAB / "baseline_predictions.parquet")


def metrics(g):
    w = g.area_tha.fillna(0)
    return pd.Series({
        "n_reg": g.okato.nunique(), "MAE": g.err.abs().mean(), "RMSE": np.sqrt((g.err ** 2).mean()),
        "MAPE": g.ape.mean(), "MdAPE": g.ape.median(), "bias": g.err.mean(),
        "wMAPE_area": np.average(g.ape, weights=w) if w.sum() > 0 else np.nan,
        "mean_y": g.y.mean(),
    })


Bs = B[B.area_tha >= MIN_AREA]
met = Bs.groupby(["cat", "crop", "method"]).apply(metrics, include_groups=False).reset_index()
met.to_csv(TAB / "baseline_metrics.csv", index=False)
met_all = B.groupby(["cat", "crop", "method"]).apply(metrics, include_groups=False).reset_index()
met_all.to_csv(TAB / "baseline_metrics_all_regions.csv", index=False)
met_year = Bs.groupby(["cat", "crop", "method", "year"]).apply(metrics, include_groups=False).reset_index()
met_year.to_csv(TAB / "baseline_metrics_by_year.csv", index=False)

# RF-уровень
recs = []
for c in MAIN:
    s = rf[rf.crop_code == c].set_index("year").value.sort_index() / 10
    s.index = s.index.astype(int)
    s = s[s.index >= Y0]
    if not eligible(s, c):
        continue
    for t in TEST_YEARS:
        for m, v in forecasts(s, t).items():
            recs.append({"crop": MAIN[c], "year": t, "method": m, "y": s[t], "yhat": v})
R = pd.DataFrame(recs)
R["ape"] = (R.yhat - R.y).abs() / R.y * 100
R.pivot_table(index="crop", columns="method", values="ape", aggfunc="mean").round(1) \
    .to_csv(TAB / "baseline_rf_mape.csv")

# график MAPE
mm = met[met["cat"] == CATS[CAT_ALL]].pivot(index="crop", columns="method", values="MAPE")
order = ["прошлый год", "среднее 5 лет", "тренд лин. 2000–2021", "тренд лин. 10 лет"]
mm = mm[[o for o in order if o in mm.columns]].sort_values("тренд лин. 2000–2021")
fig, ax = plt.subplots(figsize=(10, 6))
h = 0.2
for k, mth in enumerate(mm.columns):
    ax.barh(np.arange(len(mm)) + (k - len(mm.columns) / 2 + 0.5) * h, mm[mth], height=h * 0.85,
            color=SERIES[k], label=mth)
ax.set_yticks(range(len(mm)), mm.index)
ax.set_xlabel("MAPE, % (регионы с посевной ≥ 5 тыс. га, 2022–2024)")
ax.legend(frameon=False, fontsize=8, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=4)
ax.invert_yaxis()
ax.grid(axis="y", visible=False)
ax.set_title("Бейзлайны урожайности по субъектам, все категории хозяйств", pad=28)
savefig(fig, "baseline_mape.png")

# ---------------------------------------------------------------- остаточная дисперсия
vrows = []
for cat in (CAT_ALL, CAT_SHO):
    dd = Ysub[(Ysub.farm_category_code == cat) & Ysub.crop_code.isin(MAIN) & (Ysub.value > 0)
              & Ysub.year.between(Y0, Y1)]
    for (c, ok), g in dd.groupby(["crop_code", "okato"]):
        s = g.set_index("year").t_ha.sort_index()
        need = 15 if c == "1010401" else 20
        if len(s) < need:
            continue
        x = s.index.values.astype(float)
        b = np.polyfit(x, s.values, 1)
        fit = np.polyval(b, x)
        res = s.values - fit
        b2 = np.polyfit(x, s.values, 2)
        res2 = s.values - np.polyval(b2, x)
        vrows.append({
            "cat": CATS[cat], "crop_code": c, "crop": MAIN[c], "okato": ok, "region": g.region.iloc[0],
            "fo": g.fo.iloc[0], "n": len(s), "mean": s.mean(),
            "r2_trend": 1 - res.var() / s.values.var(),
            "r2_trend_quad": 1 - res2.var() / s.values.var(),
            "resid_sd": res.std(ddof=2), "resid_cv": res.std(ddof=2) / s.mean(),
            "slope_t_ha_yr": b[0], "area_tha": area_reg.get((c, ok), np.nan),
            "resid": pd.Series(res / fit, index=s.index.astype(int)),
        })
V = pd.DataFrame(vrows)
# согласованность аномалий внутри ФО: корреляция с средним аномалий других регионов того же ФО
coh = []
for i, r in V.iterrows():
    peers = V[(V["cat"] == r["cat"]) & (V.crop_code == r.crop_code) & (V.fo == r.fo) & (V.okato != r.okato)
              & (V.area_tha >= MIN_AREA)]
    if len(peers) < 2:
        coh.append(np.nan)
        continue
    pm = pd.concat(list(peers.resid), axis=1).mean(axis=1)
    jj = pd.concat([r.resid, pm], axis=1).dropna()
    coh.append(jj.corr().iloc[0, 1] if len(jj) >= 10 else np.nan)
V["fo_coherence_r"] = coh
V.drop(columns="resid").to_csv(TAB / "residual_variance_series.csv", index=False)

Vs = V[V.area_tha >= MIN_AREA]
var_crop = Vs.groupby(["cat", "crop"]).agg(
    n_reg=("okato", "size"), r2_trend_median=("r2_trend", "median"),
    resid_share_median=("r2_trend", lambda s: 1 - s.median()),
    resid_cv_median=("resid_cv", "median"), resid_sd_median=("resid_sd", "median"),
    fo_coherence_r2_median=("fo_coherence_r", lambda s: (s ** 2).median()),
).reset_index()
var_crop.to_csv(TAB / "residual_variance_by_crop.csv", index=False)
var_fo = (Vs[Vs["cat"] == CATS[CAT_ALL]].pivot_table(index="crop", columns="fo", values="resid_cv", aggfunc="median"))
var_fo.to_csv(TAB / "residual_cv_crop_fo.csv")
fig, ax = plt.subplots(figsize=(9, 5.5))
im = ax.imshow(var_fo.values * 100, cmap=SEQ, aspect="auto", vmin=0, vmax=35)
ax.set_xticks(range(len(var_fo.columns)), var_fo.columns)
ax.set_yticks(range(len(var_fo)), var_fo.index)
ax.grid(False)
for (i, k), v in np.ndenumerate(var_fo.values):
    if not np.isnan(v):
        ax.text(k, i, f"{v * 100:.0f}", ha="center", va="center", fontsize=7,
                color="white" if v * 100 > 20 else INK)
fig.colorbar(im, ax=ax, label="CV остатка, %")
ax.set_title("Межгодовой разброс после снятия линейного тренда (медиана по регионам ФО), %")
savefig(fig, "residual_cv_crop_fo.png")

# пример: ряды по крупным регионам
EX = [("1010400", "03000000000"), ("1010400", "07000000000"), ("1010500", "52000000000"),
      ("1080202", "03000000000"), ("3080000", "60000000000"), ("3100000", "10000000000")]
fig, axes = plt.subplots(2, 3, figsize=(12, 6))
for ax, (c, ok) in zip(axes.flat, EX):
    s = Ysub[(Ysub.farm_category_code == CAT_ALL) & (Ysub.crop_code == c) & (Ysub.okato == ok)].sort_values("year")
    if s.empty:
        ax.set_visible(False)
        continue
    ax.plot(s.year, s.t_ha, color=SERIES[0], marker="o", ms=3, label="факт")
    tr = s[s.year <= TRAIN_END]
    b = np.polyfit(tr.year, tr.t_ha, 1)
    xx = np.arange(2000, 2025)
    ax.plot(xx, np.polyval(b, xx), color=SERIES[1], lw=1.5, ls="--", label="тренд 2000–2021")
    ax.axvspan(2021.5, 2024.5, color=GRID, alpha=0.6, lw=0)
    ax.set_title(f"{MAIN[c]} — {s.region.iloc[0][:28]}")
    ax.set_ylabel("т/га")
axes.flat[0].legend(frameon=False, fontsize=8)
fig.tight_layout()
savefig(fig, "examples_region_series.png")

# ---------------------------------------------------------------- цены и удобрения
P = load("57693")
P = P[P.value.notna()]
p_tab = (P[P.region_level == "subject"].groupby("s_OKPD2")
         .agg(n_reg=("okato", "nunique"), y0=("year", "min"), y1=("year", "max"),
              okei=("s_OKEI", "first")).sort_values("n_reg", ascending=False))
p_tab.to_csv(TAB / "prices_57693_products.csv")
yr_periods = P[P.region_level == "subject"].groupby("year").period.apply(lambda s: ", ".join(sorted(s.unique(), key=len)[-2:]))
out["57693_last_periods"] = yr_periods.tail(3).to_dict()
PRICE_CROPS = ["Пшеница", "Ячмень", "Кукуруза", "Семена подсолнечника", "Бобы соевые", "Корнеплоды свеклы сахарной",
               "Картофель", "Семена рапса", "Овес", "Рожь", "Гречиха"]
pr = rf_series(P[(P.period == "январь-декабрь") & P.s_OKPD2.isin(PRICE_CROPS)])
pr.pivot_table(index="year", columns="s_OKPD2", values="value").round(0).to_csv(TAB / "prices_rf_annual.csv")

F = load("30964")
F = F[F.value.notna()]
f_tab = (F[F.region_level == "subject"].groupby("crop")
         .agg(n_reg=("okato", "nunique"), y0=("year", "min"), y1=("year", "max")))
f_tab.to_csv(TAB / "fertilizer_30964_coverage.csv")
fr = rf_series(F).pivot_table(index="year", columns="crop", values="value")
fr.to_csv(TAB / "fertilizer_rf.csv")

# ---------------------------------------------------------------- печать
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 30)
print(out)
print("\nТоп по площади:\n", area_rank.head(25).round(2))
print("\nРяды ≥15 лет:\n", run_tab.round(2).to_string())
print("\nАгрегация:\n", pd.DataFrame(cons).T.round(2))
print("\nОперативные vs итог:\n", op_tab.round(1))
print("\nМетрики (≥5 тыс. га):\n", met.round(3).to_string())
print("\nRF MAPE:\n", R.pivot_table(index="crop", columns="method", values="ape", aggfunc="mean").round(1))
print("\nОстаточная дисперсия:\n", var_crop.round(3).to_string())
print("\nCV по ФО:\n", (var_fo * 100).round(0))
print("\nЦены:\n", p_tab.head(30))
print("\nУдобрения:\n", f_tab)
