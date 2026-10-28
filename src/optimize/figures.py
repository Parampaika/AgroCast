"""Графики отчёта reports/optimization.md (reports/figures/optimization_*.png)."""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import inputs as I  # noqa: E402

FIG = I.ROOT / "reports" / "figures"
TAB = I.ROOT / "reports" / "tables"
INK, INK2, GRID, GRAY = "#1f1f1e", "#5f5e58", "#e4e2dc", "#a9a79f"
BLUE = {"d5": "#86b6ef", "d10": "#3987e5", "d20": "#1c5cab", "dall": "#0d366b"}
ORANGE = "#eb6834"
DLABEL = {"d5": "δ = 5 п.п.", "d10": "δ = 10 п.п.", "d20": "δ = 20 п.п.", "dall": "только севооборот"}


def style():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5, "axes.edgecolor": GRAY, "axes.labelcolor": INK2,
                         "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID,
                         "grid.linewidth": 0.7, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titleweight": "bold", "axes.titlesize": 10.5, "axes.titlecolor": INK,
                         "legend.frameon": False, "figure.dpi": 150, "savefig.bbox": "tight"})


def crop_colors() -> dict[str, str]:
    js = json.loads((I.ROOT / "web" / "data" / "crops.json").read_text(encoding="utf-8"))
    return {c["crop_code"]: c["color"] for c in js["crops"]}


def names() -> dict[str, str]:
    gj = json.loads((I.ROOT / "web" / "data" / "regions.geojson").read_text(encoding="utf-8"))
    return {f["properties"]["okato"]: f["properties"]["name"] for f in gj["features"]}


def fig_frontier(showcase):
    fr = pd.read_pickle(I.OUT / "frontier.pkl")
    rec = pd.read_pickle(I.OUT / "recommendations.pkl")
    nm = names()
    show = [o for o in showcase if o in set(fr.okato)][:6]
    fig, axs = plt.subplots(2, 3, figsize=(11, 6.4))
    for ax, ok in zip(axs.flat, show):
        for d, col, lab in ((np.nan, BLUE["dall"], "только севооборот"), (0.1, BLUE["d10"], "δ = 10 п.п.")):
            g = fr[(fr.okato == ok) & (fr.delta.isna() if np.isnan(d) else fr.delta == d)].sort_values("lambda")
            ax.plot(g.cvar / 1e3, g["mean"] / 1e3, "-", color=col, lw=2, label=lab, zorder=2)
            ax.scatter(g.cvar / 1e3, g["mean"] / 1e3, s=16, color=col, zorder=3, edgecolor="white", linewidth=0.8)
        r0 = rec[(rec.okato == ok)].iloc[0]
        ax.scatter([r0.cvar0 / 1e3], [r0.mean0 / 1e3], s=60, color=ORANGE, zorder=4, edgecolor="white", linewidth=1.5,
                   label="текущий план")
        ax.set_title(nm.get(ok, ok))
        ax.set_xlabel("CVaR₂₀: прибыль в худших 20 % сезонов, тыс. ₽/га")
        ax.set_ylabel("Ожидаемая прибыль, тыс. ₽/га")
    axs.flat[0].legend(loc="lower right", fontsize=8.5)
    for ax in list(axs.flat)[len(show):]:
        ax.axis("off")
    fig.suptitle("Эффективная граница «доход — риск» (λ от 0 до 1, α = 0,2)", fontweight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(FIG / "optimization_frontier.png")
    plt.close(fig)


def fig_delta_curve():
    d = pd.read_csv(TAB / "optimization_delta_curve.csv")
    fig, ax = plt.subplots(figsize=(7.2, 4))
    ax.plot(d.delta * 100, d.gain_mln / 1e3, color=BLUE["d10"], lw=2, label="Ожидаемая прибыль")
    ax.plot(d.delta * 100, d.cvar_gain_mln / 1e3, color=ORANGE, lw=2, ls=(0, (5, 3)), label="Прибыль в худших 20 % сезонов")
    for x in (5, 10, 20):
        r = d[np.isclose(d.delta * 100, x)].iloc[0]
        ax.scatter([x], [r.gain_mln / 1e3], s=36, color=BLUE["d10"], zorder=3, edgecolor="white", linewidth=1.2)
        ax.annotate(f"{r.gain_mln / 1e3:.0f} млрд ₽\n({r.gain_share_of_d30_pct:.0f} % от δ=30)", (x, r.gain_mln / 1e3),
                    textcoords="offset points", xytext=(4, -26), fontsize=8.5, color=INK2)
    ax.set_xlabel("δ — допустимое изменение доли каждой культуры, п.п.")
    ax.set_ylabel("Прирост к текущему плану, млрд ₽ в год")
    ax.set_title("Сколько меняем → сколько выигрываем (сумма по субъектам, λ = 0,5)")
    ax.legend(loc="upper left")
    ax.set_ylim(bottom=0)
    fig.savefig(FIG / "optimization_delta_curve.png")
    plt.close(fig)


def fig_backtest():
    by = pd.read_csv(TAB / "optimization_backtest_by_year.csv")
    plans = ["d5", "d10", "d20"]
    yrs = sorted(by.year.unique())
    fig, axs = plt.subplots(1, 2, figsize=(11, 4), gridspec_kw={"width_ratios": [2.2, 1]})
    ax = axs[0]
    w = 0.26
    for i, p in enumerate(plans):
        g = by[by.plan == p].set_index("year").reindex(yrs)
        ax.bar(np.arange(len(yrs)) + (i - 1) * w, g.real_gain_bln, w * 0.92, color=BLUE[p], label=DLABEL[p])
    ax.axhline(0, color=GRAY, lw=1)
    ax.set_xticks(np.arange(len(yrs)), [str(y) for y in yrs], fontsize=8.5)
    ax.set_ylabel("Фактический выигрыш к текущему плану, млрд ₽")
    ax.set_title("Проверка на отложенных годах: план по данным до t, результат года t")
    ax.legend(loc="upper left", ncols=3)
    sm = pd.read_csv(TAB / "optimization_backtest_summary.csv").set_index("plan")
    ax = axs[1]
    keys = [k for k in ["d10_last_year", "d10_mean_only", "d10", "d10_cvar_only"] if k in sm.index]
    lab = {"d10_last_year": "по прошлому году", "d10_mean_only": "только среднее (λ=0)", "d10": "λ = 0,5",
           "d10_cvar_only": "только CVaR (λ=1)"}
    y = np.arange(len(keys))
    ax.barh(y + 0.2, sm.loc[keys, "real_gain_rub_ha"], 0.38, color=BLUE["d10"], label="все годы")
    ax.barh(y - 0.2, sm.loc[keys, "bad_years_gain_rub_ha"], 0.38, color=ORANGE, label="плохие годы (худшие 20 %)")
    ax.set_yticks(y, [lab[k] for k in keys])
    ax.set_xlabel("Фактический выигрыш, ₽/га")
    ax.set_title("δ = 10 п.п.: что даёт учёт риска")
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "optimization_backtest.png")
    plt.close(fig)


def fig_shift():
    rec = pd.read_pickle(I.OUT / "recommendations.pkl")
    cc = crop_colors()
    fig, ax = plt.subplots(figsize=(7.6, 4))
    ds = [0.05, 0.1, 0.2]
    w = 0.26
    for i, d in enumerate(ds):
        g = rec[np.isclose(rec.delta, d)]
        sh = {c: 0.0 for c in I.CROPS}
        for _, r in g.iterrows():
            for c, a, b in zip(r.crops, r.x0, r.x):
                sh[c] += (b - a) * r.pool_kha
        vals = [sh[c] for c in I.CROPS]
        ax.bar(np.arange(len(I.CROPS)) + (i - 1) * w, vals, w * 0.92, color=[cc[c] for c in I.CROPS],
               alpha=[0.45, 0.7, 1.0][i], edgecolor="white", linewidth=0.6)
    ax.axhline(0, color=GRAY, lw=1)
    ax.set_xticks(np.arange(len(I.CROPS)), [I.CROP_SHORT[c] for c in I.CROPS], rotation=20, ha="right")
    ax.set_ylabel("Изменение площади, тыс. га")
    ax.set_title("Куда переносится площадь (сумма по субъектам; столбцы: δ = 5 / 10 / 20 п.п.)")
    fig.savefig(FIG / "optimization_shift.png")
    plt.close(fig)


def fig_sensitivity():
    s = pd.read_csv(TAB / "optimization_sensitivity.csv", dtype={"crop_code": str})
    base = s[s.factor == "база"].gain_mln.iloc[0]
    rows = []
    for (f, c), g in s[s.factor.isin(["price", "cost"])].groupby(["factor", "crop_code"]):
        lo = g[g.shock < 0].gain_mln.iloc[0]
        hi = g[g.shock > 0].gain_mln.iloc[0]
        rows.append((f"{'Цена' if f == 'price' else 'Затраты'}: {I.CROP_SHORT[str(c)].lower()}", lo, hi))
    rows.sort(key=lambda r: max(abs(r[1] - base), abs(r[2] - base)))
    rows = rows[-10:]
    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    for i, (lab, lo, hi) in enumerate(rows):
        ax.barh(i, (lo - base) / 1e3, left=base / 1e3, color=GRAY, height=0.6)
        ax.barh(i, (hi - base) / 1e3, left=base / 1e3, color=BLUE["d10"], height=0.6)
    ax.axvline(base / 1e3, color=INK, lw=1)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.set_xlabel("Ожидаемый прирост прибыли при δ = 10 п.п., млрд ₽ в год")
    ax.set_title("Чувствительность: −20 % (серый) и +20 % (синий)")
    fig.savefig(FIG / "optimization_sensitivity.png")
    plt.close(fig)


def fig_regions():
    rec = pd.read_pickle(I.OUT / "recommendations.pkl")
    g = rec[np.isclose(rec.delta, 0.1)].sort_values("gain_mln", ascending=False).head(15)[::-1]
    fig, ax = plt.subplots(figsize=(7.6, 5))
    ax.barh(np.arange(len(g)) + 0.2, g.gain_mln, 0.38, color=BLUE["d10"], label="ожидаемая прибыль")
    ax.barh(np.arange(len(g)) - 0.2, g.cvar_gain_mln, 0.38, color=ORANGE, label="прибыль в худших 20 % сезонов")
    ax.set_yticks(np.arange(len(g)), g.name)
    ax.set_xlabel("Прирост к текущему плану, млн ₽ в год")
    ax.set_title("15 субъектов с наибольшим эффектом (δ = 10 п.п., λ = 0,5)")
    ax.legend(loc="lower right")
    fig.savefig(FIG / "optimization_regions.png")
    plt.close(fig)


def fig_distribution():
    """Эффект по субъектам: каждая точка — субъект; черта — медиана, рамка — межквартильный размах."""
    rec = pd.read_pickle(I.OUT / "recommendations.pkl")
    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    rng = np.random.default_rng(0)
    for ax, col, title, color in ((axs[0], "gain_rub_ha", "Ожидаемая прибыль", BLUE["d10"]),
                                  (axs[1], "cvar_gain_rub_ha", "Прибыль в худших 20 % сезонов", ORANGE)):
        labels = []
        for i, d in enumerate((0.05, 0.1, 0.2)):
            v = rec[np.isclose(rec.delta, d)][col].to_numpy()
            ax.scatter(i + rng.uniform(-0.18, 0.18, len(v)), v, s=14, color=color, alpha=0.55, edgecolor="none")
            q1, q2, q3 = np.quantile(v, [0.25, 0.5, 0.75])
            ax.add_patch(plt.Rectangle((i - 0.28, q1), 0.56, q3 - q1, fill=False, edgecolor=INK2, lw=1))
            ax.plot([i - 0.28, i + 0.28], [q2, q2], color=INK, lw=2)
            labels.append(f"δ = {d * 100:.0f} п.п.\nмедиана {q2:,.0f} · Q3 {q3:,.0f}".replace(",", " "))
        ax.axhline(0, color=GRAY, lw=1)
        ax.set_xticks(range(3), labels, fontsize=8.5)
        ax.set_xlim(-0.5, 2.5)
        ax.set_ylabel("Прирост к текущему плану, ₽/га")
        ax.set_title(title)
    fig.suptitle(f"Эффект по {rec.okato.nunique()} субъектам (каждая точка — субъект)", fontweight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(FIG / "optimization_distribution.png")
    plt.close(fig)


def main(showcase):
    style()
    fig_distribution()
    FIG.mkdir(parents=True, exist_ok=True)
    fig_frontier(showcase)
    fig_delta_curve()
    fig_shift()
    fig_sensitivity()
    fig_regions()
    if (TAB / "optimization_backtest_by_year.csv").exists():
        fig_backtest()
    print("графики: готово", flush=True)
