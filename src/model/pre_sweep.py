"""Шаг перед перебором: взгляд на данные и быстрые эксперименты, которые сужают сетку.

    uv run python -I -X utf8 src/model/pre_sweep.py eda      # графики → reports/figures/pre_sweep/
    uv run python -I -X utf8 src/model/pre_sweep.py exp      # эксперименты → data/model/pre_sweep_results.csv
    uv run python -I -X utf8 src/model/pre_sweep.py summary  # сводные таблицы → data/model/pre_sweep_summary.md
"""
from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from model import cv  # noqa: E402
from model import data as D  # noqa: E402
from model.runner import MODEL_DIR, Runner, setup_log  # noqa: E402

FIG = D.ROOT / "reports" / "figures" / "pre_sweep"
CROPS = list(D.CROP_NAME)
KEY_FEAT = {"winter_wheat": "m:tmean_05", "spring_wheat": "m:tmean_06", "barley": "m:hot30_06",
            "sunflower": "m:cwb_07", "maize": "m:hot30_07", "soy": "m:cwb_07",
            "sugar_beet": "m:hot30_07"}


def frame_all() -> pd.DataFrame:
    f = pd.concat([D.crop_frame(c) for c in CROPS], ignore_index=True)
    f["r"] = f.y / f.tr_lin_all - 1
    return f


def eda():
    FIG.mkdir(parents=True, exist_ok=True)
    f = frame_all()
    ev = f[f.year.between(2005, 2025) & f.r.notna()]
    stats = []
    # 1. распределение отклонения от тренда
    fig, axs = plt.subplots(2, 4, figsize=(15, 6.5))
    for ax, c in zip(axs.flat, CROPS):
        r = ev[ev.crop == c].r.clip(-1, 1)
        ax.hist(r, bins=50, color="#3a6ea5")
        ax.axvline(0, color="k", lw=0.8)
        sk = float(r.skew())
        ax.set_title(f"{D.CROP_NAME[c]}\nsd={r.std():.2f}, skew={sk:.2f}", fontsize=9)
        stats.append({"crop": c, "n": len(r), "sd_r": r.std(), "skew_r": sk,
                      "q05": r.quantile(.05), "q95": r.quantile(.95),
                      "share_lt_-30%": (r < -0.3).mean()})
    axs.flat[-1].axis("off")
    fig.suptitle("y / линейный тренд(годы < t) − 1, субъекты выборки, 2005–2025")
    fig.tight_layout()
    fig.savefig(FIG / "01_target_dist.png", dpi=110)
    plt.close(fig)
    pd.DataFrame(stats).round(3).to_csv(MODEL_DIR / "pre_eda_target.csv", index=False)

    # 2. ряды типичных регионов (крупнейший по площади)
    fig, axs = plt.subplots(2, 4, figsize=(16, 7))
    reg = pd.read_parquet(D.CLEAN / "regions.parquet").set_index("okato").name_emiss
    for ax, c in zip(axs.flat, CROPS):
        g = f[f.crop == c]
        ok = g.groupby("okato").area_kha.mean().idxmax()
        s = g[g.okato == ok]
        ax.plot(s.year, s.y, "ko-", ms=3, label="факт")
        for k, st in (("lin_all", "-"), ("lin10", "--"), ("ts10", ":"), ("mean5", "-.")):
            ax.plot(s.year, s[f"tr_{k}"], st, label=k)
        ax.set_title(f"{D.CROP_NAME[c]}: {reg.get(ok, ok)}", fontsize=9)
    axs.flat[0].legend(fontsize=7)
    axs.flat[-1].axis("off")
    fig.tight_layout()
    fig.savefig(FIG / "02_series_examples.png", dpi=110)
    plt.close(fig)

    # 3. отклонение от тренда против ключевого погодного признака (аномалия к норме < t)
    fig, axs = plt.subplots(2, 4, figsize=(16, 7))
    for ax, c in zip(axs.flat, CROPS):
        fg = D.feature_grid(c, "end")
        X = D.fold_features(fg, 2026, [KEY_FEAT[c]])
        g = f[(f.crop == c) & f.year.between(2005, 2025)].set_index(["okato", "year"])
        x = X[KEY_FEAT[c]].reindex(g.index)
        ok = x.notna() & g.r.notna()
        ax.scatter(x[ok], g.r[ok].clip(-1, 1), s=5, alpha=0.4)
        rr = np.corrcoef(x[ok], g.r[ok])[0, 1]
        ax.set_title(f"{D.CROP_NAME[c]}: {KEY_FEAT[c][2:]}, r={rr:.2f}", fontsize=9)
        ax.axhline(0, color="k", lw=0.5)
    axs.flat[-1].axis("off")
    fig.tight_layout()
    fig.savefig(FIG / "03_dev_vs_key_weather.png", dpi=110)
    plt.close(fig)

    # 4. корреляции признаков (кукуруза, конец сезона): сколько независимой информации
    fg = D.feature_grid("maize", "end")
    cols = [c for c in fg.blocks["m"] if c.endswith(("_06", "_07", "_08"))] + fg.blocks["w"]
    C = D.fold_features(fg, 2026, cols).corr()
    fig, ax = plt.subplots(figsize=(13, 11))
    im = ax.imshow(C, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(cols)), [c[2:] for c in cols], rotation=90, fontsize=6)
    ax.set_yticks(range(len(cols)), [c[2:] for c in cols], fontsize=6)
    fig.colorbar(im, shrink=0.6)
    ax.set_title("Корреляции аномалий июня–августа и окна культуры (кукуруза)")
    fig.tight_layout()
    fig.savefig(FIG / "04_feature_corr_maize.png", dpi=110)
    plt.close(fig)
    ev_ = np.linalg.eigvalsh(C.fillna(0).to_numpy())[::-1]
    n90 = int(np.searchsorted(np.cumsum(ev_) / ev_.sum(), 0.9) + 1)

    # 5. пропуски цели по годам и культурам (выбранные регионы)
    miss = f[f.year <= 2025].groupby(["crop", "year"]).y.apply(lambda s: s.isna().mean()).unstack()
    fig, ax = plt.subplots(figsize=(13, 3.5))
    im = ax.imshow(miss, aspect="auto", cmap="Reds", vmin=0, vmax=0.5)
    ax.set_yticks(range(len(miss)), [D.CROP_NAME[c] for c in miss.index], fontsize=8)
    ax.set_xticks(range(len(miss.columns)), miss.columns, rotation=90, fontsize=7)
    fig.colorbar(im)
    ax.set_title("Доля пропусков урожайности в выбранных регионах")
    fig.tight_layout()
    fig.savefig(FIG / "05_missing_target.png", dpi=110)
    plt.close(fig)
    nd = D.load_ndvi()
    nd_miss = nd[[f"ndvi_{m}" for m in D.NDVI_MONTHS]].isna().groupby(level=1).mean()

    # 6. годы-аномалии: медианное отклонение от тренда по годам
    yr = ev.groupby(["crop", "year"]).r.median().unstack()
    fig, ax = plt.subplots(figsize=(13, 3.5))
    im = ax.imshow(yr, aspect="auto", cmap="RdBu", vmin=-0.3, vmax=0.3)
    ax.set_yticks(range(len(yr)), [D.CROP_NAME[c] for c in yr.index], fontsize=8)
    ax.set_xticks(range(len(yr.columns)), yr.columns, rotation=90, fontsize=7)
    fig.colorbar(im)
    ax.set_title("Медиана y/тренд − 1 по годам (2010, 2012 — засуха; 2022 — рекорд; 2024 — заморозки и засуха)")
    fig.tight_layout()
    fig.savefig(FIG / "06_year_anomalies.png", dpi=110)
    plt.close(fig)

    # 7. флаги качества: насколько строки с флагами выбиваются
    fl = []
    for c in CROPS:
        g = ev[ev.crop == c]
        for flag in ("flag_mismatch", "flag_lo", "is_proxy"):
            fl.append({"crop": c, "flag": flag, "n_flag": int(g[flag].sum()),
                       "share": g[flag].mean(), "mean_abs_r_flag": g[g[flag]].r.abs().mean(),
                       "mean_abs_r_rest": g[~g[flag]].r.abs().mean()})
    fl = pd.DataFrame(fl)

    # 8. трендовые ошибки: смещение по годам (недооценка роста)
    bias = []
    for k in D.TREND_TYPES:
        e = (ev[f"tr_{k}"] - ev.y) / ev.y
        bias.append({"trend": k, **{str(y): 100 * e[ev.year == y].median()
                                    for y in range(2012, 2026)}, "median": 100 * e.median()})
    bias = pd.DataFrame(bias).set_index("trend")

    with open(MODEL_DIR / "pre_eda.md", "w", encoding="utf-8") as fh:
        fh.write("## target\n" + pd.DataFrame(stats).round(3).to_markdown(index=False))
        fh.write(f"\n\n## maize corr: {len(cols)} features, 90% variance in {n90} components\n")
        fh.write("\n## NDVI missing share by year\n" + nd_miss.round(2).to_markdown())
        fh.write("\n\n## flags\n" + fl.round(3).to_markdown(index=False))
        fh.write("\n\n## trend bias % by year (median (tr-y)/y)\n" + bias.round(1).to_markdown())
        fh.write("\n\n## median r by year\n" + (100 * yr).round(0).to_markdown())
        fh.write("\n\n## regions per crop\n" + f.groupby("crop").okato.nunique().to_markdown())
    print(open(MODEL_DIR / "pre_eda.md", encoding="utf-8").read())


def experiments() -> list[cv.Config]:
    C = cv.Config
    cfgs = []
    for c in CROPS:
        for tr in D.TREND_TYPES:                                   # A: тренд × цель
            cfgs.append(C(c, trend=tr, model="trend"))
            for tg in D.TARGETS:
                cfgs.append(C(c, trend=tr, target=tg, feats="F2", model="ridge"))
                cfgs.append(C(c, trend=tr, target=tg, feats="F5", model="ridge"))
        for fs in cv.FEATSETS:                                     # B: блоки признаков
            for m in ("ridge", "lgbm"):
                cfgs.append(C(c, feats=fs, model=m))
        for fs in ("F2", "F5"):                                    # C: нормы, D: выборка
            for m in ("ridge", "lgbm"):
                cfgs.append(C(c, feats=fs, model=m, norm="fixed2021"))
                for s in ("no_mismatch", "no_lo"):
                    cfgs.append(C(c, feats=fs, model=m, sample=s))
        for d in D.DATES:                                          # F: дата прогноза
            for m in ("ridge", "lgbm"):
                for fs in ("F2", "F5"):
                    cfgs.append(C(c, date=d, feats=fs, model=m))
    for fs in ("F2", "F5"):                                        # E: общая модель
        for m in ("ridge", "lgbm"):
            cfgs.append(C("pooled", feats=fs, model=m))
    return cfgs


def summary():
    r = pd.read_csv(MODEL_DIR / "pre_sweep_results.csv", dtype={"cfg_id": str})
    r = r[r.status == "ok"]
    r["scheme"] = np.where(r.crop == "pooled", "pooled", "per_crop")
    out = []

    def pv(q, idx, name):
        t = q.pivot_table(index=idx, columns="eval_crop", values="gain_pct", aggfunc="mean")
        t["mean"] = t.mean(axis=1)
        out.append(f"### {name} (выигрыш MAE к лучшему бейзлайну, %)\n" + t.round(1).to_markdown())

    base = (r.date == "end") & (r["sample"] == "all") & (r.norm == "fold") & (r.scheme == "per_crop")
    q = r[base & r.model.isin(["trend", "ridge"])]
    pv(q[q.model == "trend"], ["trend"], "A0. Только тренд")
    pv(q[(q.model == "ridge") & (q.feats == "F2")], ["trend", "target"], "A1. Ridge F2: тренд × цель")
    pv(q[(q.model == "ridge") & (q.feats == "F5")], ["trend", "target"], "A2. Ridge F5: тренд × цель")
    q = r[base & (r.trend == "lin_all") & (r.target == "ratio") & r.model.isin(["ridge", "lgbm"])]
    pv(q, ["model", "feats"], "B. Блоки признаков (lin_all, ratio)")
    q = r[(r.date == "end") & (r.trend == "lin_all") & (r.target == "ratio") & r.feats.isin(["F2", "F5"])
          & r.model.isin(["ridge", "lgbm"])]
    pv(q[(q["sample"] == "all") & (q.scheme == "per_crop")], ["model", "feats", "norm"], "C. Нормы")
    pv(q[(q.norm == "fold") & (q.scheme == "per_crop")], ["model", "feats", "sample"], "D. Выборка")
    pv(q[(q.norm == "fold") & (q["sample"] == "all")], ["model", "feats", "scheme"], "E. Общая модель")
    q = r[(r["sample"] == "all") & (r.norm == "fold") & (r.scheme == "per_crop") & (r.trend == "lin_all")
          & (r.target == "ratio") & r.feats.isin(["F2", "F5"]) & r.model.isin(["ridge", "lgbm"])]
    pv(q, ["model", "feats", "date"], "F. Дата прогноза")
    t = r[base].groupby("model").seconds.median()
    out.append("### Время одной конфигурации (медиана, с)\n" + t.round(1).to_markdown())
    late = r[base & (r.trend == "lin_all") & (r.target == "ratio") & r.model.isin(["ridge", "lgbm"])]
    t = late.pivot_table(index=["model", "feats"], columns="eval_crop", values="late_gain_pct")
    out.append("### B на 2019–2025\n" + t.round(1).to_markdown())
    t = late.pivot_table(index=["model", "feats"], columns="eval_crop", values="cov80")
    out.append("### Покрытие 80 % интервала\n" + t.round(2).to_markdown())
    txt = "\n\n".join(out)
    (MODEL_DIR / "pre_sweep_summary.md").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("eda", "all"):
        eda()
    if what in ("exp", "all"):
        log = setup_log(MODEL_DIR / "pre_sweep.log")
        Runner(MODEL_DIR / "pre_sweep_results.csv", 12, log).run(experiments(), "pre")
    if what in ("summary", "all", "exp"):
        summary()
