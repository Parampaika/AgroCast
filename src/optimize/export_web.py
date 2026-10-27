"""Выгрузка результатов оптимизации на сайт: web/data/optimization.json (формат — docs/06_ui_data_contract.md)."""
from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd

import inputs as I

WEB = I.ROOT / "web" / "data"
TAB = I.ROOT / "reports" / "tables"


def r(x, n=0):
    if x is None or not np.isfinite(x):
        return None
    v = round(float(x), n)
    return int(v) if n == 0 else v


def key(d) -> str:
    return "all" if d is None or (isinstance(d, float) and np.isnan(d)) else str(int(round(d * 100)))


def main() -> None:
    cfg = I.config()
    regs = pd.read_pickle(I.OUT / "regions.pkl")
    rec = pd.read_pickle(I.OUT / "recommendations.pkl")
    fr = pd.read_pickle(I.OUT / "frontier.pkl")
    sc = pd.read_parquet(I.OUT / "scenarios.parquet", columns=["source"])
    src = str(sc.source.iloc[0])
    bt = pd.read_parquet(I.OUT / "backtest.parquet") if (I.OUT / "backtest.parquet").exists() else None
    out_regions = {}
    for ok, rg in regs.items():
        plans = {}
        for _, row in rec[rec.okato == ok].iterrows():
            plans[key(row.delta)] = {"x": [round(v, 4) for v in row.x], "mean": r(row.mean1), "cvar": r(row.cvar1),
                                     "worst": r(row.worst1), "gain_mln": r(row.gain_mln, 1),
                                     "cvar_gain_mln": r(row.cvar_gain_mln, 1), "turnover_pct": r(row.turnover * 100, 1)}
        row0 = rec[rec.okato == ok].iloc[0]
        front = {}
        for d, g in fr[fr.okato == ok].groupby(fr.delta.fillna(-1)):
            g = g.sort_values("lambda")
            front[key(None if d < 0 else d)] = [[r(c), r(m), round(l, 2)] for c, m, l in zip(g.cvar, g["mean"], g["lambda"])]
        item = {"pool_kha": r(rg.pool_kha, 1), "sown_kha": r(rg.sown_kha, 1), "crops": rg.crops,
                "x0": [round(v, 4) for v in rg.x0], "max_share": [round(min(1.0, v), 4) for v in rg.hi],
                "price_rub_t": [r(v) for v in rg.prices], "cost_rub_ha": [r(v) for v in rg.costs],
                "scenario_years": [int(y) for y in rg.scen_years],
                "yields": [[r(v, 3) for v in row] for row in rg.yields],
                "current": {"mean": r(row0.mean0), "cvar": r(row0.cvar0), "worst": r(row0.worst0)},
                "plans": plans, "frontier": front}
        if bt is not None:
            g = bt[(bt.okato == ok) & (bt.plan == "d10")]
            if len(g):
                item["backtest"] = {"years": [int(g.year.min()), int(g.year.max())], "n": int(len(g)),
                                    "real_gain_rub_ha": r(g.real_gain_rub_ha.mean()),
                                    "win_share_pct": r(100 * (g.real_gain_rub_ha > 1).sum() / max(1, (g.real_gain_rub_ha.abs() > 1).sum()))}
        out_regions[ok] = item
    dc = pd.read_csv(TAB / "optimization_delta_curve.csv")
    summary = {"delta_curve": [[r(d * 100), r(g / 1e3, 2), r(c / 1e3, 2), r(t, 1)]
                               for d, g, c, t in zip(dc.delta, dc.gain_mln, dc.cvar_gain_mln, dc.turnover_pct)]}
    if (TAB / "optimization_backtest_summary.csv").exists():
        sm = pd.read_csv(TAB / "optimization_backtest_summary.csv")
        summary["backtest"] = [{"plan": p, "real_gain_rub_ha": r(a), "exp_gain_rub_ha": r(e), "bad_years_gain_rub_ha": r(b),
                                "win_share_pct": r(w, 1), "real_gain_bln_year": r(gb, 1), "turnover_pct": r(t, 1)}
                               for p, a, e, b, w, gb, t in zip(sm.plan, sm.real_gain_rub_ha, sm.exp_gain_rub_ha,
                                                                sm.bad_years_gain_rub_ha, sm.win_share_pct,
                                                                sm.real_gain_bln_year, sm.turnover_pct)]
    rot = cfg["rotation"]
    crops = {cc: {"cost_rub_ha": cfg["costs"]["base_rub_ha"][cc], "max_share": rot["max_share"][cc],
                  "no_expand": cc in rot.get("no_expand", [])} for cc in I.CROPS}
    src_txt = {"hist": "история: тренд сезона × (1 + отклонение от тренда в году-аналоге), ЕМИСС 31533"}.get(
        src, "итоговая модель «тренд × погода» на погоде годов-аналогов" if src.startswith(("final", "web")) else src)
    js = {"meta": {"mock": False, "season": cfg["season"],
                   "source": f"src/optimize (CVaR-LP, HiGHS); сценарии — {src_txt}; цены — ЕМИСС 57693; затраты — допущения (src/optimize/config.toml)",
                   "note": ("Доли — от площади пула культур субъекта (7 культур прототипа) в 2025 г. Прибыль — руб./га пула. "
                            "Затраты на 1 га — допущения с региональной поправкой на уровень урожайности. "
                            "plans.<δ> — оптимум при |x − x0| ≤ δ п.п. по каждой культуре; 'all' — только севооборот."),
                   "generated": datetime.now().strftime("%Y-%m-%d %H:%M")},
          "settings": {"alpha": cfg["alpha"], "lambda": cfg["lambda_default"], "deltas": [int(d * 100) for d in cfg["deltas"]],
                       "scenario_source": src},
          "crops": crops, "summary": summary, "regions": out_regions}
    txt = json.dumps(js, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    (WEB / "optimization.json").write_text(txt, encoding="utf-8")
    print(f"web/data/optimization.json: {len(out_regions)} субъектов, {len(txt) / 1024:.0f} КБ", flush=True)
