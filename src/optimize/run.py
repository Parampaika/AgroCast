"""CLI модуля оптимизации структуры посевов.

    uv run python -I -X utf8 src/optimize/run.py all                 # всё: расчёты, таблицы, графики, web/data
    uv run python -I -X utf8 src/optimize/run.py all --scenarios hist   # источник сценариев: auto|final|web|hist
    uv run python -I -X utf8 src/optimize/run.py solve backtest       # отдельные шаги: scenarios solve backtest figures web

Промежуточные результаты — data/optimize/ (в git не идут), таблицы — reports/tables/optimization_*.csv,
графики — reports/figures/optimization_*.png, сайт — web/data/optimization.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(v, "1")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import analysis as A  # noqa: E402
import inputs as I  # noqa: E402

TABLES = I.ROOT / "reports" / "tables"
STEPS = ["scenarios", "solve", "backtest", "figures", "web"]
SHOWCASE = ["03000000000", "07000000000", "60000000000", "63000000000", "38000000000", "01000000000"]


def below_normal() -> None:
    """Понизить приоритет процесса (Windows), чтобы расчёт не мешал остальной работе."""
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)


def region_names() -> dict[str, str]:
    gj = json.loads((I.ROOT / "web" / "data" / "regions.geojson").read_text(encoding="utf-8"))
    return {f["properties"]["okato"]: f["properties"]["name"] for f in gj["features"]}


def step_scenarios(src: str) -> pd.DataFrame:
    sc = I.load_scenarios(src)
    I.OUT.mkdir(parents=True, exist_ok=True)
    sc.to_parquet(I.OUT / "scenarios.parquet", index=False)
    print(f"сценарии: {sc.source.iloc[0]}, {sc.okato.nunique()} субъектов, {sc.scenario_year.nunique()} лет", flush=True)
    return sc


def step_solve(sc: pd.DataFrame) -> None:
    cfg = I.config()
    T, lam, alpha = cfg["season"], cfg["lambda_default"], cfg["alpha"]
    regs = A.regions_for(sc, T, price_year=T)
    names = region_names()
    print(f"субъектов в оптимизации: {len(regs)}", flush=True)
    rec = A.recommendations(regs, cfg["deltas"], lam, alpha)
    rec["name"] = rec.okato.map(names)
    rec.to_pickle(I.OUT / "recommendations.pkl")
    # задачи по субъектам — для выгрузки на сайт
    pd.to_pickle(regs, I.OUT / "regions.pkl")
    fr = []
    for ok, r in regs.items():
        for d in (0.1, None):
            for p in A.frontier(r, cfg["lambdas"], alpha, d):
                fr.append({"okato": ok, "delta": np.nan if d is None else d, **p})
    pd.DataFrame(fr).to_pickle(I.OUT / "frontier.pkl")
    dc = A.delta_curve(regs, lam, alpha)
    dc.to_parquet(I.OUT / "delta_curve.parquet", index=False)
    sens = A.sensitivity(regs, 0.1, lam, alpha)
    sens.to_csv(TABLES / "optimization_sensitivity.csv", index=False, float_format="%.2f")
    write_tables(rec, dc, regs)
    print("solve: готово", flush=True)


def plan_text(crops, x0, x, thr=0.005) -> str:
    d = np.asarray(x) - np.asarray(x0)
    up = [f"{I.CROP_SHORT[c].lower()} +{v * 100:.0f}" for c, v in zip(crops, d) if v > thr]
    dn = [f"{I.CROP_SHORT[c].lower()} −{-v * 100:.0f}" for c, v in zip(crops, d) if v < -thr]
    return "; ".join(dn + up) + (" п.п." if up or dn else "без изменений")


def write_tables(rec: pd.DataFrame, dc: pd.DataFrame, regs) -> None:
    r = rec.copy()
    r["change"] = [plan_text(c, a, b) for c, a, b in zip(r.crops, r.x0, r.x)]
    r["delta_pp"] = (r.delta * 100).round(0)
    cols = ["okato", "name", "delta_pp", "pool_kha", "n_crops", "n_scen", "mean0", "mean1", "gain_rub_ha", "cvar0", "cvar1",
            "cvar_gain_rub_ha", "worst0", "worst1", "gain_mln", "cvar_gain_mln", "turnover", "change"]
    r[cols].to_csv(TABLES / "optimization_recommendations.csv", index=False, float_format="%.1f")
    agg = dc.groupby("delta")[["gain_mln", "cvar_gain_mln"]].sum().reset_index()
    agg["turnover_pct"] = dc.groupby("delta").apply(lambda g: 100 * np.average(g.turnover, weights=g.pool_kha)).to_numpy()
    agg["gain_share_of_d30_pct"] = 100 * agg.gain_mln / agg.gain_mln.iloc[-1]
    agg.to_csv(TABLES / "optimization_delta_curve.csv", index=False, float_format="%.2f")
    # допущения по затратам и калибровка по Росстату
    cfg = I.config()
    ci = I.cost_index()
    rows = [{"crop_code": c, "crop": I.CROP_SHORT[c], "cost_rub_ha_2026": v, "max_share_sown": cfg["rotation"]["max_share"][c],
             "price_product": cfg["prices"]["product"][c]} for c, v in cfg["costs"]["base_rub_ha"].items()]
    pd.DataFrame(rows).to_csv(TABLES / "optimization_costs.csv", index=False)
    e = pd.read_parquet(I.CLEAN / "economics_aux.parquet", columns=["indicator_id", "okato", "year", "value"])
    c = e[(e.indicator_id.astype(str) == "42381") & (e.okato == "643")].groupby("year").value.first()
    a = I.sown_rf_sxo()
    cal = pd.DataFrame({"cost_bln": c / 1e6, "sown_sxo_kha": a.reindex(c.index)})
    cal["rub_ha"] = cal.cost_bln * 1e9 / (cal.sown_sxo_kha * 1e3)
    cal["index_to_2026"] = ci.reindex(cal.index)
    # средневзвешенные допущения по площадям пула 2025 г.
    w = {cc: 0.0 for cc in I.CROPS}
    for rg in regs.values():
        for cc, x in zip(rg.crops, rg.x0):
            w[cc] += x * rg.pool_kha
    avg = sum(cfg["costs"]["base_rub_ha"][cc] * v for cc, v in w.items()) / sum(w.values())
    cal.attrs["weighted_assumption_2026"] = avg
    cal.reset_index().to_csv(TABLES / "optimization_cost_calibration.csv", index=False, float_format="%.1f")
    (I.OUT / "cost_weighted_avg.txt").write_text(f"{avg:.0f}", encoding="utf-8")


def step_backtest() -> None:
    cfg = I.config()
    lam, alpha = cfg["lambda_default"], cfg["alpha"]
    years = list(range(2012, 2026))
    bt = A.backtest(years, list(cfg["deltas"]) + [None], lam, alpha)
    bt.to_parquet(I.OUT / "backtest.parquet", index=False)
    sm = A.backtest_summary(bt, alpha)
    sm.to_csv(TABLES / "optimization_backtest_summary.csv", index=False, float_format="%.1f")
    by = bt.assign(gw=bt.real_gain_rub_ha * bt.pool_kha * 1e3 / 1e9, ew=bt.exp_gain_rub_ha * bt.pool_kha * 1e3 / 1e9) \
        .groupby(["year", "plan"])[["gw", "ew"]].sum().reset_index() \
        .rename(columns={"gw": "real_gain_bln", "ew": "exp_gain_bln"})
    by.to_csv(TABLES / "optimization_backtest_by_year.csv", index=False, float_format="%.2f")
    print(sm.round(1).to_string(), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("steps", nargs="*", default=["all"])
    ap.add_argument("--scenarios", default="auto", help="auto | final | web | hist")
    a = ap.parse_args()
    below_normal()
    steps = STEPS if "all" in a.steps else a.steps
    t0 = time.time()
    TABLES.mkdir(parents=True, exist_ok=True)
    I.OUT.mkdir(parents=True, exist_ok=True)
    sc = None
    if "scenarios" in steps or "solve" in steps:
        sc = step_scenarios(a.scenarios)
    if "solve" in steps:
        step_solve(sc)
    if "backtest" in steps:
        step_backtest()
    if "figures" in steps:
        import figures
        figures.main(SHOWCASE)
    if "web" in steps:
        import export_web
        export_web.main()
    print(f"готово за {time.time() - t0:.0f} с")


if __name__ == "__main__":
    main()
