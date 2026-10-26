"""Эксперименты, часть 2: форма тренда (линейный / лог-линейный) и лаги отклонений как признаки.

Запуск:
    uv run python -I -X utf8 src/data/model_experiments2.py

Модель — ансамбль Ridge + бустинг (Ensemble из model_weather.py); схема — скользящая, t = 2012…2025.
Лог-линейный тренд: log y = a + b·год, цель — log(y / тренд). Лаги: отклонение прошлого года и среднее за 3 года
(технологический сдвиг, который тренд ещё не «увидел»).
Выход: reports/tables/model_experiments2.csv, data/processed/model/experiments2_predictions.parquet.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import MAIN, TAB  # noqa: E402
from model_weather import CROPS, OUT, Ensemble, feature_cols, load_panel  # noqa: E402

warnings.filterwarnings("ignore")
TESTS = list(range(2012, 2026))
LAGS = ["lag_r1", "lag_r3"]


def add_trend2(p: pd.DataFrame, last: int, form: str) -> pd.DataFrame:
    out = []
    for (c, ok), g in p.groupby(["crop_code", "okato"]):
        tr = g[g.year <= last]
        if len(tr) < 6:
            continue
        if form == "log":
            b = np.polyfit(tr.year, np.log(tr.y), 1)
            trend = np.exp(np.polyval(b, g.year))
        else:
            b = np.polyfit(tr.year, tr.y, 1)
            trend = np.polyval(b, g.year)
        out.append(g.assign(trend=trend))
    q = pd.concat(out)
    q = q[q.trend > 0.05 * q.groupby(["crop_code", "okato"]).y.transform("mean")]
    q["r"] = np.log(q.y / q.trend).clip(-1.5, 0.6) if form == "log" else (q.y / q.trend - 1).clip(-0.8, 0.8)
    # лаги отклонения: только по годам ≤ last (для года t это t−1 и раньше)
    q = q.sort_values(["crop_code", "okato", "year"])
    known = q.r.where(q.year <= last)
    keys = [q.crop_code, q.okato]
    prev_year = q.groupby(["crop_code", "okato"]).year.shift(1)
    q["lag_r1"] = known.groupby(keys).shift(1).where(prev_year == q.year - 1)
    q["lag_r3"] = known.groupby(keys).transform(lambda s: s.shift(1).rolling(3, min_periods=2).mean())
    return q


def main():
    p = load_panel()
    recs = []
    for form in ("lin", "log"):
        for t in TESTS:
            q = add_trend2(p, t - 1, form)
            for c in CROPS:
                qc = q[q.crop_code == c]
                tr = qc[(qc.year <= t - 1) & qc.r.notna()]
                te = qc[qc.year == t]
                if te.empty or len(tr) < 100:
                    continue
                inv = (lambda r: np.exp(r)) if form == "log" else (lambda r: 1 + r)
                base = {"okato": te.okato.values, "y": te.y.values, "trend_val": te.trend.values,
                        "area_tha": te.area_tha.values}
                add = lambda name, yhat: recs.append(pd.DataFrame(base | {"variant": name, "yhat": yhat}).assign(  # noqa
                    crop_code=c, year=t, form=form))
                add("trend_only", te.trend.values)
                for lags in (False, True):
                    cols = feature_cols(c) + (LAGS if lags else [])
                    m = Ensemble().fit(tr[cols], tr.r)
                    add("ens" + ("+lags" if lags else ""), te.trend.values * inv(m.predict(te[cols])))
                # только лаги, без погоды
                m = Ensemble().fit(tr[LAGS + ["clim_t", "clim_p"]], tr.r)
                add("lags_only", te.trend.values * inv(m.predict(te[LAGS + ["clim_t", "clim_p"]])))
            print(form, t, flush=True)
    R = pd.concat(recs, ignore_index=True)
    R["crop"] = R.crop_code.map(MAIN)
    R.to_parquet(OUT / "experiments2_predictions.parquet", index=False)
    R["ae"] = (R.yhat - R.y).abs()
    R["ape"] = R.ae / R.y * 100
    R["err"] = (R.yhat / R.y - 1) * 100
    M = R.groupby(["form", "variant", "crop"]).agg(MAE=("ae", "mean"), MAPE=("ape", "mean"),
                                                   bias_med=("err", "median")).reset_index()
    ref = M[(M.form == "lin") & (M.variant == "trend_only")].set_index("crop").MAE
    M["skill_vs_lin_trend"] = 1 - M.MAE / M.crop.map(ref)
    M.to_csv(TAB / "model_experiments2.csv", index=False)
    pd.set_option("display.width", 250)
    t = M.pivot_table(index=["form", "variant"], columns="crop", values="skill_vs_lin_trend")
    t["mean"] = t.mean(axis=1)
    print((t * 100).round(1).to_string())
    print(M.pivot_table(index=["form", "variant"], columns="crop", values="bias_med").round(1).to_string())


if __name__ == "__main__":
    main()
