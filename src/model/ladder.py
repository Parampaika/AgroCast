"""Лесенка моделей на одной скользящей проверке 2012–2025.

0 — наивная: урожайность прошлого года;
1 — тренд без погоды (лучший из «среднее 5 лет» и линейный тренд 10 лет, выбор по годам 2012–2018);
2 — простая: тренд + погода, Ridge (признаки F2: месячные аномалии и окно культуры);
3 — наша модель до тюнинга: LightGBM с параметрами по умолчанию, со спутником и рельефом (F6);
4 — Optuna-тюнинг + ансамбль: лучшая конфигурация перебора на дату (отбор по годам 2012–2018).

    uv run python -I -X utf8 src/model/ladder.py [--results data/model/v2] [--out reports]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model import cv  # noqa: E402
from model import data as D  # noqa: E402
from model.final import pick  # noqa: E402

DATES = ["05-01", "06-01", "07-01", "08-01", "end"]
DATE_LABEL = {"05-01": "1 мая", "06-01": "1 июня", "07-01": "1 июля", "08-01": "1 авг", "end": "конец сезона"}
STEPS = {0: "Прошлый год", 1: "Тренд без погоды", 2: "Тренд + погода (Ridge)",
         3: "Бустинг по умолчанию + спутник", 4: "Optuna + ансамбль"}
KEYS = ["okato", "year"]


def metrics(p: pd.DataFrame, yhat: str, years: list[int]) -> dict:
    q = p[p.year.isin(years)]
    e = q[yhat] - q.y
    return {"n": len(q), "mae": float(e.abs().mean()), "rmse": float(np.sqrt((e ** 2).mean())),
            "mape": float(100 * (e.abs() / q.y).mean())}


def fixed_run(crop: str, date: str, name: str, cache: Path) -> pd.DataFrame:
    f = cache / f"{crop}_{date}_{name}.parquet"
    if f.exists():
        return pd.read_parquet(f)
    if name == "ridge":
        c = cv.Config(crop, date=date, trend="mean5", target="diff", feats="F2", model="ridge", sample="no_mismatch")
    else:
        c = cv.Config(crop, date=date, trend="mean5", target="diff", feats="F6", model="lgbm", sample="no_mismatch")
    p = cv.run_config(c)
    p.to_parquet(f, index=False)
    return p


COL = {0: "#9aa0a6", 1: "#6c8ebf", 2: "#d6a23a", 3: "#4f9d69", 4: "#b8392f"}


def build_report(df: pd.DataFrame, macro: pd.DataFrame, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fdir = out / "figures" / "ladder"
    fdir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.grid": True, "grid.alpha": .25, "axes.axisbelow": True})
    end = df[(df.date == "end") & (df.period == "all")]
    crops = list(end[end.step == 0].sort_values("crop_name").crop_name)
    # 1. лесенка по ступеням, конец сезона: MAPE по культурам и в среднем
    fig, ax = plt.subplots(figsize=(11, 4.8))
    w = 0.16
    xs = np.arange(len(crops) + 1)
    for s in STEPS:
        v = [end[(end.step == s) & (end.crop_name == c)].mape.iloc[0] for c in crops]
        v.append(float(np.mean(v)))
        ax.bar(xs + (s - 2) * w, v, w, color=COL[s], label=f"{s}. {STEPS[s]}")
    ax.set_xticks(xs, crops + ["Среднее"], rotation=15)
    ax.set_ylabel("MAPE, %  (меньше — лучше)")
    ax.set_title("Лесенка моделей: ошибка на конец сезона, скользящая проверка 2012–2025")
    ax.legend(ncol=2, frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(fdir / "ladder_steps.png", dpi=150)
    plt.close(fig)
    # 2. качество по датам прогноза: выигрыш к ступени 0, среднее по культурам
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True)
    for ax, per, ttl in zip(axs, ("all", "late"), ("все годы 2012–2025", "отложенные годы 2019–2025")):
        for s in (1, 2, 3, 4):
            m = macro[(macro.period == per) & (macro.step == s)].set_index("date").reindex(DATES)
            ax.plot([DATE_LABEL[d] for d in DATES], m.gain, "o-", color=COL[s], label=f"{s}. {STEPS[s]}", lw=2)
        ax.set_title(ttl)
        ax.set_xlabel("Дата прогноза")
    axs[0].set_ylabel("Снижение MAE к «прошлому году», % (среднее по культурам)")
    axs[1].legend(frameon=False, fontsize=9, loc="lower right")
    fig.tight_layout()
    fig.savefig(fdir / "ladder_by_date.png", dpi=150)
    plt.close(fig)
    # 3. тепловая карта культура × ступень (конец сезона), выигрыш к ступени 0
    piv = end.pivot(index="crop_name", columns="step", values="gain_vs_step0_pct").loc[crops, [1, 2, 3, 4]]
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    im = ax.imshow(piv.to_numpy(), cmap="YlGn", vmin=0, aspect="auto")
    ax.set_xticks(range(4), [f"{s}. {STEPS[s]}" for s in (1, 2, 3, 4)], rotation=15, ha="right")
    ax.set_yticks(range(len(crops)), crops)
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            ax.text(j, i, f"{piv.iloc[i, j]:.0f}", ha="center", va="center", fontsize=10)
    ax.set_title("Снижение MAE к «прошлому году», %, конец сезона")
    ax.grid(False)
    fig.colorbar(im, ax=ax, shrink=.8)
    fig.tight_layout()
    fig.savefig(fdir / "ladder_crops_heatmap.png", dpi=150)
    plt.close(fig)
    # отчёт
    def tab(frame):
        return frame.to_markdown(floatfmt=".2f")
    t_end = end.pivot(index="crop_name", columns="step", values="mae")
    t_end.columns = [f"{s}. {STEPS[s]}" for s in t_end.columns]
    g_end = end.pivot(index="crop_name", columns="step", values="gain_vs_step0_pct")[[1, 2, 3, 4]]
    g_end.columns = [f"{s}. {STEPS[s]}" for s in g_end.columns]
    mc = end.groupby("step").agg(mae=("mae", "mean"), rmse=("rmse", "mean"), mape=("mape", "mean"),
                                 gain=("gain_vs_step0_pct", "mean")).rename(index=STEPS)
    mc.columns = ["MAE, т/га (среднее по культурам)", "RMSE, т/га", "MAPE, %", "снижение MAE к ступени 0, %"]
    dm = macro[macro.period == "all"].pivot(index="step_name", columns="date", values="gain").reindex(
        list(STEPS.values()))[DATES]
    dm.columns = [DATE_LABEL[d] for d in dm.columns]
    dl = macro[macro.period == "late"].pivot(index="step_name", columns="date", values="gain").reindex(
        list(STEPS.values()))[DATES]
    dl.columns = [DATE_LABEL[d] for d in dl.columns]
    NL = "\n"
    L = ["# Лесенка моделей" + NL,
         "Пять ступеней оцениваются на **одной и той же** скользящей проверке: для каждого года T от 2012 до 2025 модель "
         "обучается только на сезонах до T, прогноз сравнивается с фактом на одних и тех же парах «субъект × год». "
         "Выборка: субъекты с посевом ≥ 5 тыс. га и рядом ≥ 15 лет. 2025 год — урожайность восстановлена как сбор / посевная "
         "(итогов Росстата нет), поэтому все ступени ошибаются относительно одной и той же «правды».",
         "",
         "| ступень | что это |", "|---|---|",
         "| 0. Прошлый год | урожайность прошлого сезона без каких-либо поправок |",
         "| 1. Тренд без погоды | лучший из «среднее 5 лет» и линейного тренда 10 лет (выбор по годам 2012–2018) |",
         "| 2. Тренд + погода (Ridge) | линейная модель на аномалиях погоды и окне культуры, цель «отклонение от среднего 5 лет» |",
         "| 3. Бустинг по умолчанию + спутник | LightGBM с параметрами по умолчанию на погоде, почвах, NDVI, спутнике MODIS (LAI, FPAR, LST), рельефе и прошлых отклонениях |",
         "| 4. Optuna + ансамбль | лучшая конфигурация перебора на каждую культуру и дату (подбор гиперпараметров и признаков, среднее лучших моделей); выбор по годам 2012–2018 |",
         "",
         "## Итог на конец сезона", "", tab(mc), "",
         "![лесенка](figures/ladder/ladder_steps.png)", "",
         "### MAE по культурам, т/га", "", tab(t_end), "",
         "### Снижение MAE к ступени 0, %", "", tab(g_end), "",
         "![культуры × ступени](figures/ladder/ladder_crops_heatmap.png)", "",
         "## Качество по датам прогноза", "",
         "Среднее по семи культурам снижение MAE к «прошлому году», %. Все годы 2012–2025:", "", tab(dm), "",
         "Отложенные годы 2019–2025 (в подборе гиперпараметров не участвовали):", "", tab(dl), "",
         "![по датам](figures/ladder/ladder_by_date.png)", "",
         "Полные таблицы с RMSE и MAPE по культурам и датам — `reports/tables/ladder_by_crop_date.csv`.", "",
         "## Примечания", "",
         "- Ступени 0–1 не зависят от даты: к любой дате они известны одинаково.",
         "- Ступень 4 выбирается по DEV-годам 2012–2018, поэтому отложенные годы дают честную оценку.",
         "- Честно о монотонности: лесенка растёт не на каждом шаге. Бустинг по умолчанию со спутником в среднем не лучше Ridge с погодой (разница в пределах шума), выигрыш даёт именно подбор гиперпараметров, набора признаков и ансамбль. На отложенных годах 2019–2025 ступень 4 лучше ступени 2 заметно только к концу сезона; ранние даты (1 мая) почти не отличаются.",
         "- Ступени 2–3 зафиксированы заранее (конфигурация не подбиралась под результат), чтобы показать вклад каждого шага."]
    (out / "ladder.md").write_text(NL.join(L) + NL, encoding="utf-8")
    print("отчёт записан:", out / "ladder.md")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="data/model/v2")
    ap.add_argument("--out", default="reports")
    a = ap.parse_args()
    rdir = D.ROOT / a.results
    cache = D.ROOT / "data" / "model" / "ladder"
    cache.mkdir(parents=True, exist_ok=True)
    res = pd.read_csv(rdir / "sweep_results.csv", dtype={"cfg_id": str, "params": str, "sample": str, "norm": str})
    res = res[res.status == "ok"]
    rows = []
    for crop in sorted(D.CROP_NAME):
        for date in DATES:
            r2 = fixed_run(crop, date, "ridge", cache)
            r3 = fixed_run(crop, date, "lgbm", cache)
            ch = pick(res, crop, date)
            r4 = pd.read_parquet(rdir / "preds" / f"{ch['cfg_id']}.parquet").query("crop == @crop")
            base = r3.merge(r2[KEYS + ["yhat"]].rename(columns={"yhat": "s2"}), on=KEYS) \
                     .merge(r4[KEYS + ["yhat"]].rename(columns={"yhat": "s4"}), on=KEYS)
            base = base.rename(columns={"yhat": "s3"})
            yrs = base.year.isin(cv.EVAL_YEARS)
            # ступень 1: лучший из двух трендовых бейзлайнов по DEV-годам
            dev = base[base.year.isin(cv.DEV_YEARS)]
            b1 = min(["bl_mean5", "bl_lin10"], key=lambda c: (dev[c] - dev.y).abs().mean())
            base["s0"], base["s1"] = base.bl_lag1, base[b1]
            for s in STEPS:
                for per, years in (("all", cv.EVAL_YEARS), ("late", cv.LATE_YEARS)):
                    m = metrics(base, f"s{s}", years)
                    rows.append({"crop": crop, "crop_name": D.CROP_NAME[crop], "date": date, "step": s,
                                 "step_name": STEPS[s], "period": per, **m,
                                 "detail": b1 if s == 1 else (f"{ch['kind']}: " + "; ".join(
                                     f"{x['model']}/{x['feats']}" for x in ch["members"]) if s == 4 else "")})
            print(crop, date, "ok", flush=True)
    df = pd.DataFrame(rows)
    ref = df[df.step == 0].set_index(["crop", "date", "period"]).mae
    df["gain_vs_step0_pct"] = [100 * (1 - r.mae / ref[(r.crop, r.date, r.period)]) for r in df.itertuples()]
    tdir = D.ROOT / a.out / "tables"
    tdir.mkdir(parents=True, exist_ok=True)
    df.to_csv(tdir / "ladder_by_crop_date.csv", index=False, encoding="utf-8")
    end = df[(df.date == "end") & (df.period == "all")]
    summ = end.pivot_table(index="crop_name", columns="step", values=["mae", "rmse", "mape", "gain_vs_step0_pct"])
    summ.to_csv(tdir / "ladder_summary_end.csv", encoding="utf-8")
    macro = df.groupby(["date", "period", "step", "step_name"]).agg(
        gain=("gain_vs_step0_pct", "mean"), mape=("mape", "mean")).reset_index()
    macro.to_csv(tdir / "ladder_macro_by_date.csv", index=False, encoding="utf-8")
    print("таблицы записаны в", tdir)
    build_report(df, macro, D.ROOT / a.out)


if __name__ == "__main__":
    main()
