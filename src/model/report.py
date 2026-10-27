"""Отчёт перебора: reports/sweep.md и графики reports/figures/sweep/."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from model import cv  # noqa: E402
from model import data as D  # noqa: E402

DATE_LABEL = {"05-01": "1 мая", "06-01": "1 июня", "07-01": "1 июля", "08-01": "1 авг", "end": "конец"}
DATE_ORDER = ["05-01", "06-01", "07-01", "08-01", "end"]
# выигрыш первой модели «тренд × погода» (reports/model_weather.md), %: для сравнения
PREV_GAIN = {"winter_wheat": 11, "spring_wheat": 8, "barley": 7, "sunflower": 0, "maize": 7,
             "soy": 4, "sugar_beet": 26}
# от простого к сложному: при равной точности рекомендуем более простую модель
SIMPLE = ["ridge", "enet", "hgb", "lgbm", "xgb", "et", "rf", "cat", "ens_mean2", "ens_mean3",
          "ens_mean5", "ens_stack"]


def _md(df: pd.DataFrame, digits: int = 1) -> str:
    return df.round(digits).to_markdown(index=False)


def _desc(r) -> str:
    if str(r.model).startswith("ens_"):
        return f"{r.model}"
    sch = "общая" if r.crop == "pooled" else ""
    return f"{r.model} · {r.trend} · {r.target} · {r.feats}" + (f" · {sch}" if sch else "")


def recommend(q: pd.DataFrame, tol: float = 0.01) -> pd.Series:
    """Самая простая конфигурация в пределах tol от лучшей MAE."""
    best = q.mae.min()
    c = q[q.mae <= best * (1 + tol)].copy()
    c["rank"] = c.model.map({m: i for i, m in enumerate(SIMPLE)}).fillna(99)
    return c.sort_values(["rank", "mae"]).iloc[0]


def build_report(out: Path, G: dict, smoke: bool = False, name: str = "sweep", compare: Path | None = None,
                 title: str = "Перебор моделей прогноза урожайности"):
    res = pd.read_csv(out / "sweep_results.csv", dtype={"cfg_id": str, "params": str})
    ok = res[res.status == "ok"].copy()
    n_err = int((res.status == "error").sum())
    name = "sweep_smoke" if smoke else name
    fig_dir = D.ROOT / "reports" / "figures" / name
    fig_dir.mkdir(parents=True, exist_ok=True)
    md_path = D.ROOT / "reports" / f"{name}.md"
    ok["desc"] = [_desc(r) for r in ok.itertuples()]
    crops = [c for c in G["crops"] if c in set(ok.eval_crop)]
    L = []
    L.append(f"# {title}\n")
    L.append(f"*Сгенерировано `src/model/sweep.py` {pd.Timestamp.now():%d.%m.%Y %H:%M}. "
             f"Результаты — `{out.resolve().relative_to(D.ROOT).as_posix()}/sweep_results.csv` "
             f"({len(res)} строк, конфигураций {ok.cfg_id.nunique()}, ошибок {n_err}), "
             "лог — `sweep.log`. Анализ перед перебором — [pre_sweep_analysis.md](pre_sweep_analysis.md).*\n")
    L.append("**Проверка:** скользящий прогноз 2012–2025 (обучение, тренд и нормы погоды — только по годам < t), "
             "2025 — урожайность, восстановленная по сбору. Выигрыш — снижение MAE против лучшего из бейзлайнов "
             "lin10 / mean5 / lag1 на тех же строках. Гиперпараметры Optuna подбирались только по 2012–2018, "
             "поэтому колонка «2019–25» — честная отложенная проверка для подбора гиперпараметров "
             "(выбор признаков и тренда видел все годы). Интервал — конформный 80 % по относительным "
             "ошибкам прошлых лет (с разогревом 2009–2011).\n")
    stage_n = ok.groupby("stage").cfg_id.nunique()
    L.append("Конфигураций по этапам: " + ", ".join(f"{k} — {v}" for k, v in stage_n.items()) + ".\n")

    # ---------- 1. итог по культурам
    end = ok[ok.date == "end"]
    summ, recs = [], {}
    for c in crops:
        q = end[end.eval_crop == c]
        qm = q[q.model != "trend"]
        if qm.empty:
            continue
        b = qm.sort_values("mae").iloc[0]
        r = recommend(qm)
        recs[c] = r
        bl = {k: q[f"mae_bl_{k}"].iloc[0] for k in D.BASELINES}
        blk = min(bl, key=bl.get)
        summ.append({"культура": D.CROP_NAME[c], "регионов": D.crop_frame(c).okato.nunique(),
                     "строк": int(b.n), "лучший бейзлайн": f"{blk} {bl[blk]:.3f}",
                     "лучшая модель": b.desc, "MAE": b.mae, "MAPE": b.mape, "wMAPE": b.wmape,
                     "выигрыш, %": b.gain_pct, "2019–25, %": b.late_gain_pct,
                     "покрытие 80": b.cov80, "ширина, %": b.width80_pct,
                     "было (model_weather), %": PREV_GAIN.get(c)})
    L.append("## 1. Итог: конец сезона\n")
    L.append(_md(pd.DataFrame(summ), 3) + "\n")

    # ---------- 2. рекомендация
    L.append("## 2. Что брать в прототип\n")
    L.append("Правило: из конфигураций в пределах 1 % от лучшей MAE берётся самая простая "
             "(ridge < enet < бустинги < леса < ансамбли).\n")
    rr = []
    for c in crops:
        for d in DATE_ORDER:
            q = ok[(ok.eval_crop == c) & (ok.date == d) & (ok.model != "trend")]
            if q.empty:
                continue
            r = recommend(q)
            rr.append({"культура": D.CROP_NAME[c], "дата": DATE_LABEL[d], "конфигурация": r.desc,
                       "MAE": r.mae, "выигрыш, %": r.gain_pct, "2019–25, %": r.late_gain_pct,
                       "покрытие 80": r.cov80, "ширина, %": r.width80_pct, "cfg_id": r.cfg_id})
    rec_df = pd.DataFrame(rr)
    L.append(_md(rec_df, 3) + "\n")
    rec_df.to_csv(out / "sweep_recommendation.csv", index=False)

    # ---------- 3. лидерборд
    L.append("## 3. Лидерборд по культурам (конец сезона, топ-10)\n")
    for c in crops:
        q = end[(end.eval_crop == c)].sort_values("mae").head(10)
        t = q[["desc", "stage", "mae", "mape", "wmape", "gain_pct", "dev_gain_pct", "late_gain_pct",
               "cov80", "width80_pct"]].rename(columns={"desc": "конфигурация", "gain_pct": "выигрыш",
                                                        "dev_gain_pct": "2012–18", "late_gain_pct": "2019–25"})
        L.append(f"### {D.CROP_NAME[c]}\n\n" + _md(t, 3) + "\n")

    # ---------- 4. модели
    mm = end[end.crop == end.eval_crop].groupby(["eval_crop", "model"]).gain_pct.max().unstack(0)
    mm = mm.reindex(columns=crops)
    mm.columns = [D.CROP_NAME[c] for c in mm.columns]
    L.append("## 4. Лучший выигрыш каждой модели, % (конец сезона)\n")
    L.append(mm.round(1).reset_index().to_markdown(index=False) + "\n")
    if not mm.empty:
        fig, ax = plt.subplots(figsize=(10, 0.45 * len(mm) + 1.5))
        im = ax.imshow(mm.to_numpy(float), cmap="RdYlGn", vmin=-5, vmax=max(25, np.nanmax(mm.to_numpy(float))))
        ax.set_xticks(range(mm.shape[1]), mm.columns, rotation=30, ha="right", fontsize=8)
        ax.set_yticks(range(mm.shape[0]), mm.index, fontsize=8)
        for i in range(mm.shape[0]):
            for j in range(mm.shape[1]):
                v = mm.iat[i, j]
                if np.isfinite(v):
                    ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7)
        fig.colorbar(im, label="выигрыш MAE к лучшему бейзлайну, %")
        fig.tight_layout()
        fig.savefig(fig_dir / "models_gain.png", dpi=110)
        plt.close(fig)
        L.append("![models](figures/{}/models_gain.png)\n".format(fig_dir.name))

    # ---------- 5. оси этапа 1
    co = ok[(ok.stage == "coarse") & (ok.model != "trend") & (ok.date == "end")]
    if not co.empty:
        L.append("## 5. Оси грубого отбора (лучший выигрыш по оси, %)\n")
        for ax_ in ("trend", "target", "feats", "model"):
            t = co[co.crop == co.eval_crop].groupby([ax_, "eval_crop"]).gain_pct.max().unstack()
            t = t.reindex(columns=crops)
            t.columns = [D.CROP_NAME[c] for c in t.columns]
            L.append(f"**{ax_}**\n\n" + t.round(1).reset_index().to_markdown(index=False) + "\n")
        pl = co[co.crop == "pooled"].groupby("eval_crop").gain_pct.max()
        pc = co[co.crop != "pooled"].groupby("eval_crop").gain_pct.max()
        if len(pl):
            t = pd.DataFrame({"по культуре": pc, "общая": pl}).reindex(crops)
            t.index = [D.CROP_NAME[c] for c in t.index]
            L.append("**Схема**\n\n" + t.round(1).reset_index().to_markdown(index=False) + "\n")
        tr = ok[(ok.model == "trend") & (ok.date == "end")].pivot_table(
            index="trend", columns="eval_crop", values="gain_pct").reindex(columns=crops)
        tr.columns = [D.CROP_NAME[c] for c in tr.columns]
        L.append("**Только тренд (без погоды)**\n\n" + tr.round(1).reset_index().to_markdown(index=False) + "\n")

    # ---------- 6. дата прогноза
    dd = ok[ok.model != "trend"].groupby(["eval_crop", "date"]).agg(mae=("mae", "min"),
                                                                    gain=("gain_pct", "max")).reset_index()
    if dd.date.nunique() > 1:
        g = dd.pivot(index="eval_crop", columns="date", values="gain").reindex(columns=DATE_ORDER)
        g = g.reindex([c for c in crops if c in g.index])
        g.index = [D.CROP_NAME[c] for c in g.index]
        g.columns = [DATE_LABEL[c] for c in g.columns]
        g.index.name = "культура"
        L.append("## 6. Дата прогноза → выигрыш к лучшему бейзлайну, % (лучшая конфигурация на дату)\n")
        L.append(g.round(1).reset_index().to_markdown(index=False) + "\n")
        fig, axs = plt.subplots(1, 2, figsize=(13, 4.5))
        for c in crops:
            q = dd[dd.eval_crop == c].set_index("date").reindex(DATE_ORDER)
            axs[0].plot(range(5), q.gain, "o-", label=D.CROP_NAME[c])
            axs[1].plot(range(5), q.mae / q.mae.iloc[-1], "o-", label=D.CROP_NAME[c])
        for ax in axs:
            ax.set_xticks(range(5), [DATE_LABEL[d] for d in DATE_ORDER])
            ax.grid(alpha=0.3)
        axs[0].axhline(0, color="k", lw=0.7)
        axs[0].set_ylabel("выигрыш MAE к лучшему бейзлайну, %")
        axs[1].set_ylabel("MAE / MAE в конце сезона")
        axs[0].legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(fig_dir / "leadtime.png", dpi=110)
        plt.close(fig)
        L.append("![lead](figures/{}/leadtime.png)\n".format(fig_dir.name))

    # ---------- 7. интервалы
    cal_p = out / "sweep_calibration.csv"
    if cal_p.exists():
        cal = pd.read_csv(cal_p)
        if not cal.empty:
            cal["win"] = cal.window.map(lambda w: "все годы" if w == 0 else f"{w} лет")
            t = cal[cal.years == "late"].pivot_table(index=["kind", "win"], columns="crop",
                                                     values=["cov80", "width80_pct"], aggfunc="mean")
            L.append("## 7. Калибровка 80 % интервала (2019–2025, среднее по датам)\n")
            L.append("Варианты: относительная (rel) или абсолютная (abs) ошибка, окно прошлых лет. "
                     "Цель — покрытие около 0,80 при наименьшей ширине.\n")
            L.append(t.round(2).reset_index().to_markdown(index=False) + "\n")
            a = cal[cal.years == "all"].copy()
            a["score"] = (a.cov80 - 0.8).abs() * 100 + 0.02 * a.width80_pct
            best = a.groupby(["kind", "win"]).score.mean().idxmin()
            L.append(f"Лучший по сумме (|покрытие − 0,8| и ширина): **{best[0]}, {best[1]}**.\n")

    # ---------- 8. графики победителей
    fig, axs = plt.subplots(2, 4, figsize=(16, 7.5))
    for ax, c in zip(axs.flat, crops):
        r = recs.get(c)
        if r is None:
            continue
        p = pd.read_parquet(out / "preds" / f"{r.cfg_id}.parquet")
        p = p[(p.year >= 2012) & (p.crop == c)]
        yr = p.groupby("year").apply(lambda g: pd.Series({
            "модель": (g.yhat - g.y).abs().mean(),
            **{b: (g[f"bl_{b}"] - g.y).abs().mean() for b in D.BASELINES}}), include_groups=False)
        for col, st in (("модель", "o-"), ("lin10", "--"), ("mean5", ":"), ("lag1", "-.")):
            ax.plot(yr.index, yr[col], st, label=col, ms=3)
        ax.set_title(f"{D.CROP_NAME[c]}: MAE по годам\n{r.desc}", fontsize=8)
        ax.grid(alpha=0.3)
    axs.flat[0].legend(fontsize=7)
    for ax in list(axs.flat)[len(crops):]:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(fig_dir / "mae_by_year.png", dpi=110)
    plt.close(fig)
    L.append("## 8. Рекомендованные модели по годам\n")
    L.append("![years](figures/{}/mae_by_year.png)\n".format(fig_dir.name))

    fig, axs = plt.subplots(2, 4, figsize=(16, 7.5))
    for ax, c in zip(axs.flat, crops):
        r = recs.get(c)
        if r is None:
            continue
        p = pd.read_parquet(out / "preds" / f"{r.cfg_id}.parquet")
        p = cv.conformal(p)
        p = p[(p.year >= 2012) & (p.crop == c)]
        ax.errorbar(p.y, p.yhat, yerr=[p.yhat - p.lo, p.hi - p.yhat], fmt="o", ms=2, alpha=0.3, lw=0.5)
        lim = [0, max(p.y.max(), p.yhat.max()) * 1.05]
        ax.plot(lim, lim, "k-", lw=0.7)
        ax.set_title(f"{D.CROP_NAME[c]}: прогноз и 80 % интервал против факта", fontsize=8)
        ax.set_xlabel("факт, т/га", fontsize=8)
    for ax in list(axs.flat)[len(crops):]:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(fig_dir / "pred_vs_actual.png", dpi=110)
    plt.close(fig)
    L.append("![scatter](figures/{}/pred_vs_actual.png)\n".format(fig_dir.name))

    if compare is not None:
        L.extend(compare_section(ok, compare, crops))
    errs = res[res.status == "error"]
    if len(errs):
        L.append("## Ошибки\n")
        e = errs.groupby(["stage", "model"]).size().reset_index(name="n")
        L.append(e.to_markdown(index=False) + "\n\nПервые сообщения:\n")
        for m in errs.error.dropna().head(5):
            L.append(f"- `{str(m)[:200]}`")
    md_path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return md_path


def best_by(df: pd.DataFrame) -> pd.DataFrame:
    """Лучшая MAE и выигрыш по (культура, дата) среди всех одиночных моделей и ансамблей."""
    q = df[df.model != "trend"]
    i = q.groupby(["eval_crop", "date"]).mae.idxmin()
    return q.loc[i].set_index(["eval_crop", "date"])


def _cmp_table(a: pd.DataFrame, b: pd.DataFrame, col: str, crops: list[str]) -> str:
    rows = []
    for c in crops:
        r = {"культура": D.CROP_NAME[c]}
        for d in DATE_ORDER:
            if (c, d) in a.index and (c, d) in b.index:
                x, y = a.loc[(c, d), col], b.loc[(c, d), col]
                r[DATE_LABEL[d]] = f"{x:.1f} → {y:.1f} ({y - x:+.1f})"
        rows.append(r)
    return pd.DataFrame(rows).to_markdown(index=False)


def compare_section(ok: pd.DataFrame, v1_dir: Path, crops: list[str]) -> list[str]:
    old = pd.read_csv(v1_dir / "sweep_results.csv", dtype={"cfg_id": str, "params": str})
    old = old[old.status == "ok"]
    a, b = best_by(old), best_by(ok)
    L = ["## 9. Сравнение с первой версией (v1, без спутника и рельефа)\n",
         "Выигрыш к лучшему бейзлайну, %: v1 → новая версия (разница в п. п.). "
         "Бейзлайны те же, поэтому разница честная.\n",
         _cmp_table(a, b, "gain_pct", crops) + "\n",
         "На отложенных годах 2019–2025:\n\n" + _cmp_table(a, b, "late_gain_pct", crops) + "\n"]
    # что дал спутник: лучшая одиночная конфигурация с блоками F6/F7 против лучшей без них
    sat = ok[ok.feats.isin(["F6", "F7"]) & (ok.model != "trend")]
    nos = ok[~ok.feats.isin(["F6", "F7"]) & (ok.model != "trend") & ~ok.model.str.startswith("ens_")]
    sat, nos = sat[~sat.model.str.startswith("ens_")], nos
    ga = sat.groupby(["eval_crop", "date"])[["gain_pct"]].max()
    gb = nos.groupby(["eval_crop", "date"])[["gain_pct"]].max()
    L.append("Лучшая одиночная конфигурация без спутника → со спутником (F6/F7), та же версия:\n\n"
             + _cmp_table(gb, ga, "gain_pct", crops) + "\n")
    return L


if __name__ == "__main__":
    import sys
    from model.runner import MODEL_DIR
    from model.sweep import FULL
    out_ = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else MODEL_DIR
    nm = sys.argv[2] if len(sys.argv) > 2 else "sweep"
    cmp_ = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 and sys.argv[3] else None
    ttl = sys.argv[4] if len(sys.argv) > 4 else "Перебор моделей прогноза урожайности"
    build_report(out_, FULL, name=nm, compare=cmp_, title=ttl)
    print(json.dumps({"ok": True}))
