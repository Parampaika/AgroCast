"""Графики отчёта в едином стиле (style.py). Каждый строится из таблиц проекта.

Функция графика получает путь для PNG и возвращает True, если график построен,
и False, если данных ещё нет (тогда в отчёте будет заглушка).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch

from report import sources as S
from report.style import (AQUA, BLUE, CAT, CMAP_DIV, CMAP_SEQ, CROP_COLOR, CROP_NAME, CROP_ORDER,
                          CROP_SHORT, DATE_LABEL, DATE_ORDER, GRID, INK, INK2, MONTH, MUTED, NAME_KEY,
                          NEUTRAL, ORANGE, ORD5, RED, SEQ, VIOLET, annotate_heat, feature_label)

W = 6.3  # ширина полосы набора, дюймы


def _save(fig, out: Path) -> bool:
    fig.savefig(out)
    plt.close(fig)
    return True


def _crop_axis(keys):
    return [CROP_SHORT.get(k, k) for k in keys]


# ---------------------------------------------------------------- данные и пайплайн

def pipeline(out: Path) -> bool:
    fig, ax = plt.subplots(figsize=(W, 3.9))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 62)
    ax.axis("off")

    def box(x, y, w, h, title, body, color, fill="#f4f8fd"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.2",
                                    lw=1.1, ec=color, fc=fill))
        ax.text(x + w / 2, y + h - 1.6, title, ha="center", va="top", fontsize=7.8, weight="bold", color=INK)
        ax.text(x + w / 2, y + h - 5.0, body, ha="center", va="top", fontsize=6.2, color=INK2, linespacing=1.3)

    def arrow(x0, y0, x1, y1):
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.0, shrinkA=0, shrinkB=0))

    srcs = [("ЕМИСС / Росстат", "74 показателя: урожайность,\nплощади, сборы, цены, удобрения"),
            ("Погода", "ERA5 и ERA5-Land, 450 точек\nпашни, почасово; NASA POWER"),
            ("Почвы и рельеф", "SoilGrids 2.0 (11 свойств),\nвысоты ERA5-Land, WRB"),
            ("Спутник MODIS", "NDVI, LAI, FPAR, LST, GPP\n8–16 дней, 2000–2026"),
            ("Справочники", "календари GGCMI, FAOSTAT,\nUSDA PSD, Госреестр сортов")]
    for i, (t, b) in enumerate(srcs):
        box(0.5, 50.5 - i * 12, 26, 10, t, b, NEUTRAL, fill="#fafaf8")
    ax.plot([28, 29.5, 29.5, 28], [60.5, 60.5, 2.5, 2.5], color=MUTED, lw=1.0)
    arrow(29.5, 55.5, 33, 55.5)
    ax.text(15, -1.5, "источники", ha="center", fontsize=7, color=MUTED, style="italic")
    layers = [("raw — сырые выгрузки", "скрипты загрузки с докачкой и логами", SEQ[1]),
              ("interim — разбор", "SDMX → длинные таблицы, выборки", SEQ[2]),
              ("processed — исследование", "сутки погоды, ET0 FAO-56, NDVI, признаки", SEQ[4]),
              ("clean — чистый слой", "18+ таблиц, флаги качества, 50 тестов", SEQ[5]),
              ("model_table", "субъект × культура × год: 81 тыс. × 683", SEQ[7])]
    for i, (t, b, c) in enumerate(layers):
        y = 51 - i * 12
        box(33, y, 33, 9, t, b, c, fill="#f4f8fd" if i < 4 else "#e6f0fc")
        if i:
            arrow(49.5, y + 12, 49.5, y + 9)
    ax.text(49.5, -1.5, "слои данных: поток строго сверху вниз", ha="center", fontsize=7, color=MUTED, style="italic")
    outs = [("Перебор моделей", "скользящая проверка,\n5 дат, Optuna, ансамбли", BLUE),
            ("Оптимизация посевов", "погодные сценарии, CVaR,\nограничения севооборота", ORANGE),
            ("Сайт «Агрокаст»", "карта, калькулятор урожая,\nплан посевов", AQUA)]
    for i, (t, b, c) in enumerate(outs):
        y = 42 - i * 17
        box(73.5, y, 26, 11, t, b, c, fill="#ffffff")
        arrow(66.3, 7.5, 73.3, y + 5.5)
    ax.text(86.5, -1.5, "результаты", ha="center", fontsize=7, color=MUTED, style="italic")
    return _save(fig, out)


def data_volume(out: Path) -> bool:
    st = _stats()
    if not st:
        return False
    names = {"era5_om": "ERA5 / ERA5-Land", "emiss": "ЕМИСС (SDMX)", "spei": "SPEI", "nasa_power": "NASA POWER",
             "rosstat": "Росстат (Wayback)", "modis_ndvi": "MODIS NDVI", "faostat": "FAOSTAT",
             "modis_lai": "MODIS LAI/FPAR", "modis_lst": "MODIS LST", "modis_gpp": "MODIS GPP",
             "usda_psd": "USDA PSD", "crop_calendar_ggcmi": "Календари GGCMI", "soilgrids": "SoilGrids",
             "gossortrf": "Госреестр сортов", "geo": "Границы и точки", "worldcover": "WorldCover",
             "mcx_news": "Минсельхоз (новости)", "mapspam2020": "MapSPAM"}
    d = pd.DataFrame([{"src": names.get(k, k), "gb": v["bytes"] / 2**30, "files": v["files"]}
                      for k, v in st["raw_sources"].items() if v["bytes"] > 0]).sort_values("gb")
    fig, ax = plt.subplots(figsize=(W, 3.5))
    y = np.arange(len(d))
    ax.barh(y, d.gb, color=BLUE, height=0.62)
    ax.set_xscale("log")
    ax.set_yticks(y, d.src)
    ax.grid(axis="y", visible=False)
    for yi, (g, n) in enumerate(zip(d.gb, d.files)):
        lab = f"{g:.2f} ГБ" if g >= 0.01 else f"{g * 1024:.1f} МБ"
        ax.text(g * 1.12, yi, f"{lab} · {n:,} файл.".replace(",", " "), va="center", fontsize=7, color=INK2)
    ax.set_xlim(d.gb.min() / 2, d.gb.max() * 12)
    ax.set_xlabel("объём сырых данных, ГБ (логарифмическая шкала)")
    ax.set_title("Сырые данные по источникам")
    return _save(fig, out)


def coverage(out: Path) -> bool:
    t = S._read_csv(S.TABLES / "coverage_crop_year_cat1.csv", index_col=0)
    if t is None:
        return False
    keep = ["Пшеница озимая", "Пшеница яровая", "Ячмень яровой", "Подсолнечник", "Кукуруза на зерно", "Соя",
            "Сахарная свёкла", "Картофель", "Овёс", "Рапс яровой"]
    t = t.loc[[k for k in keep if k in t.index]]
    t = t.loc[:, [c for c in t.columns if int(c) <= 2024]]
    fig, ax = plt.subplots(figsize=(W, 2.9))
    im = ax.imshow(t.values, aspect="auto", cmap=CMAP_SEQ, vmin=0, vmax=85)
    ax.set_yticks(range(len(t)), t.index)
    ax.set_xticks(range(0, t.shape[1], 2), t.columns[::2])
    ax.grid(False)
    annotate_heat(ax, t.values, thresh=85, fontsize=5.6)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=7)
    ax.set_title("Число субъектов с данными об урожайности (ЕМИСС 31533, все категории хозяйств)")
    return _save(fig, out)


def weather_corr(out: Path) -> bool:
    t = S._read_csv(S.TABLES / "weather_corr.csv")
    if t is None:
        return False
    crops = ["Пшеница озимая", "Пшеница яровая", "Ячмень яровой", "Подсолнечник", "Кукуруза на зерно", "Соя",
             "Сахарная свёкла"]
    months = ["p09", "p10", "p11", "p12", "01", "02", "03", "04", "05", "06", "07", "08"]
    fig, axes = plt.subplots(1, 2, figsize=(W, 2.9), sharey=True)
    for ax, var, title in zip(axes, ["tmax", "cwb"], ["Температура (макс.)", "Водный баланс P − ET0"]):
        q = t[(t["var"] == var) & t.crop.isin(crops)].pivot(index="crop", columns="month", values="corr")
        q = q.reindex(index=crops, columns=[m for m in months if m in q.columns])
        im = ax.imshow(q.values, cmap=CMAP_DIV, vmin=-0.5, vmax=0.5, aspect="auto")
        ax.set_xticks(range(q.shape[1]), [MONTH[m].rstrip("¹") for m in q.columns], rotation=90)
        ax.set_yticks(range(len(crops)), [CROP_SHORT[NAME_KEY[c]] for c in crops])
        ax.grid(False)
        annotate_heat(ax, q.values * 100, fmt="{:.0f}", thresh=50, fontsize=5.8)
        ax.set_title(title)
    cb = fig.colorbar(im, ax=axes, fraction=0.025, pad=0.01)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=7)
    fig.text(0.0, -0.03, "Корреляция (×100) отклонения урожайности от тренда с месячной аномалией; "
             "первые четыре месяца — осень и зима перед сезоном.", fontsize=7, color=INK2)
    return _save(fig, out)


# ---------------------------------------------------------------- первая модель и перебор

def first_model(out: Path) -> bool:
    t = S.first_model_table()
    if t is None:
        return False
    t = t[t.crop.isin(CROP_NAME.values()) | t.crop.isin(["Овёс", "Картофель"])]
    cols = ["прошлый год", "среднее 5 лет", "линейный тренд", "тренд × погода"]
    colors = [ORD5[0], ORD5[1], ORD5[2], ORD5[4]]
    t = t.sort_values("тренд × погода")
    fig, ax = plt.subplots(figsize=(W, 3.0))
    y = np.arange(len(t))
    h = 0.19
    for i, (c, col) in enumerate(zip(cols, colors)):
        ax.barh(y + (1.5 - i) * h, t[c], height=h * 0.92, color=col, label=c)
    ax.set_yticks(y, [CROP_SHORT.get(NAME_KEY.get(c, ""), c) for c in t.crop])
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("MAPE по субъектам, % (скользящая проверка 2012–2025)")
    ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.13))
    return _save(fig, out)


def _end_best(r, key="ck"):
    q = r[(r.date == "end") & r.ck.isin(CROP_ORDER)]
    return q


def trend_target(out: Path) -> bool:
    r = S.sweep("v1")
    if r is None:
        return False
    q = _end_best(r)
    q = q[(q.stage == "coarse") & (q.model == "ridge") & (q.crop != "pooled")]
    g = q.groupby(["ck", "trend", "target"]).gain_pct.max().groupby(["trend", "target"]).mean().unstack()
    order = ["mean5", "lin15", "lin_all", "lin10", "ts15", "ts10"]
    g = g.reindex([o for o in order if o in g.index])[["diff", "ratio", "log"]]
    lab = {"mean5": "среднее 5 лет", "lin15": "лин. 15 лет", "lin_all": "лин. все годы", "lin10": "лин. 10 лет",
           "ts15": "Тейл–Сен 15", "ts10": "Тейл–Сен 10"}
    fig, ax = plt.subplots(figsize=(W * 0.6, 2.6))
    im = ax.imshow(g.values, cmap=CMAP_DIV, vmin=-22, vmax=22, aspect="auto")
    ax.set_yticks(range(len(g)), [lab[i] for i in g.index])
    ax.set_xticks(range(3), ["разность\ny − тренд", "отношение\ny / тренд − 1", "логарифм\nln(y / тренд)"])
    ax.grid(False)
    annotate_heat(ax, g.values, fmt="{:+.1f}", thresh=22, fontsize=7.5)
    ax.set_title("Ridge: тренд × цель, выигрыш к бейзлайну, %")
    return _save(fig, out)


def feature_blocks(out: Path) -> bool:
    r = S.sweeps()
    if r is None:
        return False
    q = _end_best(r)
    q = q[q.stage.isin(["coarse", "models", "models_default"]) & (q.model != "trend")]
    g = q.groupby(["ck", "feats"]).gain_pct.max().unstack()
    cols = [c for c in ["F1", "F2", "F2r", "F3", "F4", "F5", "F6", "F7", "F8"] if c in g.columns]
    g = g.reindex(index=CROP_ORDER, columns=cols)
    fig, ax = plt.subplots(figsize=(W, 2.8))
    im = ax.imshow(g.values, cmap=CMAP_SEQ, vmin=-5, vmax=32, aspect="auto")
    ax.set_yticks(range(len(g)), _crop_axis(g.index))
    names = {"F1": "F1\nмесяцы", "F2": "F2\n+окно", "F2r": "F2r\n+регион", "F3": "F3\n+почвы", "F4": "F4\n+NDVI",
             "F5": "F5\n+регион", "F6": "F6\n+спутник", "F7": "F7\nтолько\nспутник", "F8": "F8\nпогода+\nспутник"}
    ax.set_xticks(range(len(cols)), [names[c] for c in cols], fontsize=7)
    ax.grid(False)
    annotate_heat(ax, g.values, fmt="{:.1f}", thresh=32, fontsize=7)
    ax.set_title("Лучший выигрыш к бейзлайну по набору признаков, % (конец сезона)")
    return _save(fig, out)


def model_families(out: Path) -> bool:
    r = S.sweeps()
    if r is None:
        return False
    q = _end_best(r)
    g = q.groupby(["ck", "model"]).gain_pct.max().unstack()
    order = ["trend", "ridge", "enet", "rf", "et", "hgb", "lgbm", "xgb", "cat", "ens_mean2", "ens_mean3",
             "ens_mean5", "ens_stack"]
    g = g.reindex(index=CROP_ORDER, columns=[o for o in order if o in g.columns])
    lab = {"trend": "только\nтренд", "ridge": "Ridge", "enet": "Elastic\nNet", "rf": "Random\nForest",
           "et": "Extra\nTrees", "hgb": "HistGB", "lgbm": "Light\nGBM", "xgb": "XGBoost", "cat": "Cat\nBoost",
           "ens_mean2": "среднее\nтоп-2", "ens_mean3": "среднее\nтоп-3", "ens_mean5": "среднее\nтоп-5",
           "ens_stack": "стекинг"}
    fig, ax = plt.subplots(figsize=(W, 2.9))
    im = ax.imshow(g.values, cmap=CMAP_SEQ, vmin=-5, vmax=32, aspect="auto")
    ax.set_yticks(range(len(g)), _crop_axis(g.index))
    ax.set_xticks(range(g.shape[1]), [lab[c] for c in g.columns], fontsize=6.6)
    ax.grid(False)
    annotate_heat(ax, g.values, fmt="{:.0f}", thresh=32, fontsize=7)
    ax.axvline(0.5, color="white", lw=2)
    if "ens_mean2" in g.columns:
        ax.axvline(list(g.columns).index("ens_mean2") - 0.5, color="white", lw=2)
    ax.set_title("Лучший выигрыш семейства моделей к бейзлайну, % (конец сезона, v1 + v2)")
    return _save(fig, out)


def leadtime(out: Path) -> bool:
    r = S.sweeps()
    if r is None:
        return False
    q = r[r.ck.isin(CROP_ORDER) & (r.model != "trend")]
    g = q.groupby(["ck", "date"]).gain_pct.max().unstack().reindex(index=CROP_ORDER, columns=DATE_ORDER)
    fig, ax = plt.subplots(figsize=(W, 2.7))
    x = np.arange(len(DATE_ORDER))
    for k in CROP_ORDER:
        ax.plot(x, g.loc[k], marker="o", color=CROP_COLOR[k], label=CROP_SHORT[k])
    # подписи справа, раздвинутые, чтобы не налезали
    ends = sorted(((g.loc[k].iloc[-1], k) for k in CROP_ORDER), reverse=True)
    pos, gap = [], (g.max().max() - min(0, g.min().min())) * 0.06
    for v, k in ends:
        pos.append(min(v, pos[-1] - gap) if pos else v)
        ax.text(x[-1] + 0.1, pos[-1], CROP_SHORT[k], va="center", fontsize=7, color=INK2)
    ax.set_xticks(x, [DATE_LABEL[d] for d in DATE_ORDER])
    ax.set_xlim(-0.2, len(x) - 0.2)
    ax.set_ylabel("выигрыш к бейзлайну, %")
    ax.axhline(0, color=NEUTRAL, lw=0.8)
    ax.legend(ncol=7, loc="upper center", bbox_to_anchor=(0.45, 1.16), fontsize=7, handlelength=1.2)
    return _save(fig, out)


def v1_v2(out: Path) -> bool:
    a, b = S.sweep("v1"), S.sweep("v2")
    if a is None or b is None:
        return False
    ba = _end_best(a).groupby("ck").gain_pct.max().reindex(CROP_ORDER)
    bb = _end_best(b).groupby("ck").gain_pct.max().reindex(CROP_ORDER)
    sat = b[(b.date == "end") & b.ck.isin(CROP_ORDER) & b.feats.isin(["F6", "F7", "F8"])]
    nos = b[(b.date == "end") & b.ck.isin(CROP_ORDER) & ~b.feats.isin(["F6", "F7", "F8"]) & (b.model != "trend")]
    bs = sat.groupby("ck").gain_pct.max().reindex(CROP_ORDER)
    bn = nos.groupby("ck").gain_pct.max().reindex(CROP_ORDER)
    fig, ax = plt.subplots(figsize=(W, 2.8))
    y = np.arange(len(CROP_ORDER))
    h = 0.26
    ax.barh(y - h, ba, h * 0.9, color=ORD5[2], label="v1: погода, почвы, NDVI (с ансамблями)")
    ax.barh(y, bn, h * 0.9, color=NEUTRAL, label="v2 без спутника")
    ax.barh(y + h, bs, h * 0.9, color=VIOLET, label="v2 со спутником MODIS")
    ax.set_yticks(y, _crop_axis(CROP_ORDER))
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("лучший выигрыш к бейзлайну, % (конец сезона)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.17), ncol=3, fontsize=7)
    return _save(fig, out)


def ladder_end(out: Path) -> bool:
    lad = S.ladder()
    if lad is None:
        return False
    q = lad[(lad.date == "end") & (lad.period == "all")]
    g = q.pivot(index="crop", columns="step", values="mape").reindex(CROP_ORDER)
    names = q.drop_duplicates("step").set_index("step").step_name.sort_index()
    fig, ax = plt.subplots(figsize=(W, 3.2))
    y = np.arange(len(g))
    n = g.shape[1]
    h = 0.8 / n
    for i, s in enumerate(g.columns):
        ax.barh(y + (i - (n - 1) / 2) * h, g[s], h * 0.9, color=ORD5[i % 5], label=f"{s}. {names[s]}")
    ax.set_yticks(y, _crop_axis(g.index))
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("MAPE по субъектам, % (скользящая проверка 2012–2025, конец сезона)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.2), ncol=3, fontsize=7)
    return _save(fig, out)


def ladder_dates(out: Path) -> bool:
    m = S.ladder_macro()
    if m is None:
        return False
    m = m[m.period == "all"]
    fig, ax = plt.subplots(figsize=(W, 2.6))
    x = np.arange(len(DATE_ORDER))
    for i, (s, g) in enumerate(m.groupby("step")):
        g = g.set_index("date").reindex(DATE_ORDER)
        ax.plot(x, g.gain, marker="o", color=ORD5[i % 5], label=f"{s}. {g.step_name.dropna().iloc[0]}")
    ax.set_xticks(x, [DATE_LABEL[d] for d in DATE_ORDER])
    ax.set_ylabel("снижение MAE к «прошлому году», %")
    ax.legend(fontsize=7, ncol=2, loc="lower right")
    return _save(fig, out)


def years(out: Path) -> bool:
    r = S.sweeps()
    if r is None:
        return False
    b = S.best(r[r.ck.isin(CROP_ORDER)])
    rows = {}
    for k in CROP_ORDER:
        if k in b.index:
            d = S.mae_by_year(b.loc[k])
            mean = np.mean(list(d.values()))
            rows[CROP_SHORT[k]] = {y: v / mean for y, v in d.items()}
    t = pd.DataFrame(rows).T.sort_index(axis=1)
    fig, ax = plt.subplots(figsize=(W, 2.5))
    im = ax.imshow(t.values, cmap=CMAP_SEQ, vmin=0.3, vmax=2.0, aspect="auto")
    ax.set_yticks(range(len(t)), t.index)
    ax.set_xticks(range(t.shape[1]), t.columns, rotation=0, fontsize=7)
    ax.grid(False)
    annotate_heat(ax, t.values, fmt="{:.1f}", thresh=2.0, fontsize=6.5)
    ax.set_title("Ошибка лучшей модели по годам: MAE года / средняя MAE культуры")
    return _save(fig, out)


def pred_actual(out: Path) -> bool:
    r = S.sweeps()
    if r is None:
        return False
    b = S.best(r[r.ck.isin(CROP_ORDER)])
    fig, axes = plt.subplots(2, 4, figsize=(W, 3.5))
    for ax, k in zip(axes.flat, CROP_ORDER):
        row = b.loc[k]
        p = S.preds(row.ver, row.cfg_id)
        if p is None:
            ax.axis("off")
            continue
        p = p[(p.crop == k) & p.year.between(2012, 2025)] if "crop" in p else p[p.year.between(2012, 2025)]
        lim = np.nanpercentile(np.r_[p.y, p.yhat], 99.5) * 1.05
        ax.plot([0, lim], [0, lim], color=NEUTRAL, lw=0.8)
        ax.scatter(p.yhat, p.y, s=4, color=CROP_COLOR[k], alpha=0.45, lw=0)
        ax.set_xlim(0, lim)
        ax.set_ylim(0, lim)
        ax.set_title(CROP_SHORT[k], fontsize=8)
        ax.tick_params(labelsize=6)
    axes.flat[-1].axis("off")
    axes.flat[-1].text(0.05, 0.55, "по горизонтали — прогноз,\nпо вертикали — факт, т/га;\n"
                       "точка — субъект × год\n(2012–2025)", fontsize=7, color=INK2, transform=axes.flat[-1].transAxes)
    fig.tight_layout(pad=0.4)
    return _save(fig, out)


def intervals(out: Path) -> bool:
    r = S.sweeps()
    if r is None:
        return False
    b = S.best(r[r.ck.isin(CROP_ORDER)]).reindex(CROP_ORDER)
    fig, axes = plt.subplots(1, 2, figsize=(W, 2.4), sharey=True)
    y = np.arange(len(b))
    axes[0].barh(y, b.cov80 * 100, color=BLUE, height=0.6)
    axes[0].axvline(80, color=RED, lw=1.2, ls="--")
    axes[0].text(80.5, -0.75, "цель 80 %", color=RED, fontsize=7)
    axes[0].set_xlim(60, 100)
    axes[0].set_xlabel("доля фактов внутри интервала, %")
    axes[1].barh(y, b.width80_pct, color=ORANGE, height=0.6)
    axes[1].set_xlabel("ширина P90 − P10, % от прогноза")
    for ax in axes:
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(y, _crop_axis(b.index))
    axes[0].invert_yaxis()
    for yi, v in enumerate(b.width80_pct):
        axes[1].text(v + 1, yi, f"±{v / 2:.0f} %", va="center", fontsize=7, color=INK2)
    axes[1].set_xlim(0, b.width80_pct.max() * 1.25)
    return _save(fig, out)


# ---------------------------------------------------------------- интерпретация

def shap_blocks(out: Path) -> bool:
    s = S.shap()
    if s is None:
        return False
    g = s.groupby(["crop", "block"]).mean_abs_shap.sum().unstack().reindex(CROP_ORDER)
    g = g.div(g.sum(axis=1), axis=0) * 100
    order = ["погода по месяцам", "окно культуры и зима", "спутник MODIS", "NDVI", "регион и прошлые отклонения",
             "почвы", "климат региона", "рельеф и тип почвы"]
    g = g[[o for o in order if o in g.columns]]
    fig, ax = plt.subplots(figsize=(W, 2.9))
    y = np.arange(len(g))
    left = np.zeros(len(g))
    for c, col in zip(g.columns, CAT):
        ax.barh(y, g[c], left=left, color=col, height=0.66, label=c, edgecolor="white", linewidth=1)
        for yi, (l, v) in enumerate(zip(left, g[c])):
            if v >= 7:
                ax.text(l + v / 2, yi, f"{v:.0f}", ha="center", va="center", fontsize=6.8, color="white")
        left += g[c].to_numpy()
    ax.set_yticks(y, _crop_axis(g.index))
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.grid(False)
    ax.set_xlabel("доля суммарного |SHAP|, %")
    ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.22), fontsize=6.8)
    return _save(fig, out)


def shap_top(out: Path) -> bool:
    s = S.shap()
    if s is None:
        return False
    crops = ["winter_wheat", "barley", "maize", "sugar_beet"]
    fig, axes = plt.subplots(2, 2, figsize=(W, 4.4))
    for ax, k in zip(axes.flat, crops):
        q = s[s.crop == k].nlargest(8, "mean_abs_shap").iloc[::-1]
        rel = q.mean_abs_shap / q.y_mean * 100
        col = [BLUE if v >= 0 else RED for v in q.sign_corr.fillna(0)]
        ax.barh(range(len(q)), rel, color=col, height=0.62)
        ax.set_yticks(range(len(q)), [feature_label(f) for f in q.feature], fontsize=6.6)
        ax.grid(axis="y", visible=False)
        ax.set_title(CROP_NAME[k], fontsize=8.5)
        ax.tick_params(axis="x", labelsize=6.5)
    for ax in axes[1]:
        ax.set_xlabel("средний |SHAP|, % от урожайности", fontsize=7)
    fig.text(0.0, -0.02, "Синий — чем больше значение признака, тем выше урожайность; красный — наоборот. "
             "¹ — месяц предыдущего года.", fontsize=7, color=INK2)
    fig.tight_layout(pad=0.5)
    return _save(fig, out)


def forecast_2026(out: Path) -> bool:
    t = S._read_csv(S.TABLES / "forecast_2026_rf.csv")
    if t is None:
        return False
    t = t[t.crop.isin(CROP_NAME.values())].copy()
    t["k"] = t.crop.map(NAME_KEY)
    t = t.set_index("k").reindex(CROP_ORDER).dropna(subset=["vs_trend_pct"])
    fig, ax = plt.subplots(figsize=(W, 2.4))
    y = np.arange(len(t))
    col = [BLUE if v >= 0 else RED for v in t.vs_trend_pct]
    ax.barh(y, t.vs_trend_pct, color=col, height=0.6)
    for yi, (v, f, tr) in enumerate(zip(t.vs_trend_pct, t.forecast_2026, t.trend_2026)):
        ax.text(v + (0.4 if v >= 0 else -0.4), yi, f"{f:.2f} т/га (тренд {tr:.2f})".replace(".", ","),
                va="center", ha="left" if v >= 0 else "right", fontsize=7, color=INK2)
    ax.axvline(0, color=NEUTRAL, lw=0.8)
    ax.set_yticks(y, _crop_axis(t.index))
    ax.invert_yaxis()
    ax.set_xlim(-25, 30)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("прогноз 2026 к тренду, % (средневзвешенно по модельным регионам)")
    return _save(fig, out)


# ---------------------------------------------------------------- оптимизация

def _opt(name):
    return S._read_csv(S.TABLES / f"optimization_{name}.csv")


def opt_delta(out: Path) -> bool:
    d = _opt("delta_curve")
    if d is None:
        return False
    fig, axes = plt.subplots(1, 2, figsize=(W, 2.6))
    x = d.delta * 100
    ax = axes[0]
    ax.plot(x, d.gain_mln / 1e3, color=BLUE, label="ожидаемая прибыль")
    ax.plot(x, d.cvar_gain_mln / 1e3, color=ORANGE, label="прибыль в худших 20 % лет (CVaR)")
    ax.set_xlabel("допустимое изменение доли культуры δ, п. п.")
    ax.set_ylabel("прирост, млрд руб./год")
    ax.legend(loc="upper left", fontsize=7)
    for dv in (5, 10, 20):
        r = d.loc[(d.delta * 100 - dv).abs().idxmin()]
        ax.plot([dv], [r.gain_mln / 1e3], "o", color=BLUE, ms=5, mec="white", mew=1.2)
        ax.annotate(f"{r.gain_mln / 1e3:.0f}", (dv, r.gain_mln / 1e3), xytext=(4, -10),
                    textcoords="offset points", fontsize=7, color=INK2)
    ax = axes[1]
    ax.plot(x, d.gain_share_of_d30_pct, color=BLUE)
    ax.plot(x, x / x.max() * 100, color=NEUTRAL, ls="--", lw=1)
    ax.text(16, 40, "линейный рост", color=MUTED, fontsize=7, rotation=33)
    ax.set_xlabel("δ, п. п.")
    ax.set_ylabel("доля эффекта от δ = 30 п. п., %")
    for dv in (5, 10):
        r = d.loc[(d.delta * 100 - dv).abs().idxmin()]
        ax.plot([dv], [r.gain_share_of_d30_pct], "o", color=BLUE, ms=5, mec="white", mew=1.2)
        ax.annotate(f"{r.gain_share_of_d30_pct:.0f} %", (dv, r.gain_share_of_d30_pct), xytext=(-6, 8),
                    textcoords="offset points", fontsize=7, color=INK2)
    fig.tight_layout(pad=0.5)
    return _save(fig, out)


def opt_backtest(out: Path) -> bool:
    b = _opt("backtest_summary")
    if b is None:
        return False
    lab = {"d5": "δ = 5 п. п.", "d10": "δ = 10 п. п.", "d20": "δ = 20 п. п.", "dall": "без ограничения δ",
           "d10_mean_only": "δ = 10, без учёта риска", "d10_cvar_only": "δ = 10, только риск",
           "d10_last_year": "δ = 10, «как в прошлом году»"}
    b = b[b.plan.isin(lab)].set_index("plan").reindex([k for k in lab if k in set(b.plan)])
    fig, ax = plt.subplots(figsize=(W, 2.7))
    y = np.arange(len(b))
    h = 0.27
    ax.barh(y - h, b.exp_gain_rub_ha, h * 0.9, color=NEUTRAL, label="обещано моделью (ожидание)")
    ax.barh(y, b.real_gain_rub_ha, h * 0.9, color=BLUE, label="получено по факту года")
    ax.barh(y + h, b.bad_years_gain_rub_ha, h * 0.9, color=ORANGE, label="по факту в худшие 20 % лет")
    right = b[["exp_gain_rub_ha", "real_gain_rub_ha", "bad_years_gain_rub_ha"]].max(axis=1)
    for yi, (v, w, xr) in enumerate(zip(b.real_gain_rub_ha, b.win_share_pct, right)):
        ax.text(xr + 80, yi,f"{v:,.0f} ₽/га · выигрыш в {w:.0f} % случаев".replace(",", " "),
                va="center", fontsize=6.6, color=INK2)
    ax.set_yticks(y, [lab[k] for k in b.index])
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, b.exp_gain_rub_ha.max() * 1.45)
    ax.set_xlabel("прирост прибыли к текущему плану, руб./га (2012–2025, субъекты)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.17), ncol=3, fontsize=7)
    return _save(fig, out)


def opt_sensitivity(out: Path) -> bool:
    d = _opt("sensitivity")
    c = _opt("costs")
    if d is None or c is None:
        return False
    base = float(d.loc[d.factor == "база", "gain_mln"].iloc[0])
    names = dict(zip(c.crop_code.astype(str), c.crop))
    rows = []
    for (f, cc), g in d[d.factor.isin(["price", "cost"])].groupby(["factor", "crop_code"]):
        lo = float(g.loc[g.shock < 0, "gain_mln"].iloc[0]) - base
        hi = float(g.loc[g.shock > 0, "gain_mln"].iloc[0]) - base
        rows.append({"lab": f"{'цена' if f == 'price' else 'затраты'}: {names.get(str(int(cc)), cc).lower()}",
                     "lo": lo / 1e3, "hi": hi / 1e3, "span": abs(hi - lo)})
    t = pd.DataFrame(rows).sort_values("span").tail(10)
    fig, ax = plt.subplots(figsize=(W, 2.9))
    y = np.arange(len(t))
    ax.barh(y, t.lo, color=RED, height=0.6, label="−20 %")
    ax.barh(y, t.hi, color=BLUE, height=0.6, label="+20 %")
    ax.axvline(0, color=INK2, lw=0.8)
    ax.set_yticks(y, t.lab)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel(f"изменение эффекта плана, млрд руб./год (база {base / 1e3:.0f} млрд при δ = 10 п. п.)")
    ax.legend(loc="lower right", fontsize=7)
    return _save(fig, out)


def _stats():
    p = S.BUILD / "data_stats.json"
    import json
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


FIGS = {
    "pipeline": pipeline, "data_volume": data_volume, "coverage": coverage, "weather_corr": weather_corr,
    "first_model": first_model, "trend_target": trend_target, "feature_blocks": feature_blocks,
    "model_families": model_families, "leadtime": leadtime, "v1_v2": v1_v2, "ladder_end": ladder_end,
    "ladder_dates": ladder_dates, "years": years, "pred_actual": pred_actual, "intervals": intervals,
    "shap_blocks": shap_blocks, "shap_top": shap_top, "forecast_2026": forecast_2026,
    "opt_delta": opt_delta, "opt_backtest": opt_backtest, "opt_sensitivity": opt_sensitivity,
}
