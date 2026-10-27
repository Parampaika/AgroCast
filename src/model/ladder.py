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


if __name__ == "__main__":
    main()
