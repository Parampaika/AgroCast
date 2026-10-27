"""Расчёты для отчёта: рекомендации по субъектам, эффективная граница, кривая «δ → эффект»,
чувствительность к ценам и затратам, проверка на отложенных годах (backtest)."""
from __future__ import annotations

import numpy as np
import pandas as pd

import inputs as I
import problems as P
from lp import Problem, evaluate, solve


def regions_for(scen: pd.DataFrame, year: int, price_year: int, cost_year: int | None = None) -> dict[str, P.Region]:
    out = {}
    for ok in sorted(scen.okato.unique()):
        r = P.build(ok, year, scen, price_year, cost_year)
        if r is not None:
            out[ok] = r
    return out


def _row(r: P.Region, d, lam, alpha, s0, s1) -> dict:
    ch = s1.x - r.x0
    return {"okato": r.okato, "delta": np.nan if d is None else d, "lambda": lam, "alpha": alpha,
            "pool_kha": r.pool_kha, "sown_kha": r.sown_kha, "n_crops": len(r.crops), "n_scen": len(r.scen_years),
            "mean0": s0.mean, "mean1": s1.mean, "cvar0": s0.cvar, "cvar1": s1.cvar,
            "worst0": s0.profits.min(), "worst1": s1.profits.min(),
            "gain_rub_ha": s1.mean - s0.mean, "cvar_gain_rub_ha": s1.cvar - s0.cvar,
            "gain_mln": (s1.mean - s0.mean) * r.pool_kha * 1e3 / 1e6,
            "cvar_gain_mln": (s1.cvar - s0.cvar) * r.pool_kha * 1e3 / 1e6,
            "turnover": np.abs(ch).sum() / 2, "x0": r.x0.round(4).tolist(), "x": s1.x.round(4).tolist(),
            "crops": r.crops}


def recommendations(regs: dict[str, P.Region], deltas, lam: float, alpha: float) -> pd.DataFrame:
    rows = []
    for r in regs.values():
        pr = r.problem()
        s0 = evaluate(pr, r.x0, alpha, lam)
        for d in list(deltas) + [None]:
            rows.append(_row(r, d, lam, alpha, s0, solve(pr, lam, alpha, d)))
    return pd.DataFrame(rows)


def frontier(r: P.Region, lambdas, alpha: float, delta) -> list[dict]:
    """Эффективная граница «ожидаемая прибыль — CVaR» при заданном δ (перебор веса риска λ)."""
    pr = r.problem()
    out = []
    for lam in lambdas:
        s = solve(pr, lam, alpha, delta)
        out.append({"lambda": lam, "mean": s.mean, "cvar": s.cvar, "x": s.x.round(4).tolist()})
    return out


def delta_curve(regs: dict[str, P.Region], lam: float, alpha: float, grid=None) -> pd.DataFrame:
    """Сумма эффекта по субъектам (млн руб./год) при δ от 0 до 30 п.п."""
    grid = np.round(np.arange(0, 0.301, 0.01), 2) if grid is None else grid
    rows = []
    for r in regs.values():
        pr = r.problem()
        s0 = evaluate(pr, r.x0, alpha, lam)
        k = r.pool_kha * 1e3 / 1e6
        for d in grid:
            s = solve(pr, lam, alpha, float(d))
            rows.append({"okato": r.okato, "delta": d, "gain_mln": (s.mean - s0.mean) * k,
                         "cvar_gain_mln": (s.cvar - s0.cvar) * k, "pool_kha": r.pool_kha,
                         "turnover": np.abs(s.x - r.x0).sum() / 2})
    return pd.DataFrame(rows)


def sensitivity(regs: dict[str, P.Region], delta: float, lam: float, alpha: float, shock: float = 0.2) -> pd.DataFrame:
    """Чувствительность суммарного эффекта и рекомендованной структуры к цене и затратам каждой культуры ±shock."""
    base = _aggregate(regs, delta, lam, alpha)
    rows = [{"factor": "база", "crop_code": "", "shock": 0.0, **base}]
    for cc in I.CROPS:
        for kind in ("price", "cost"):
            for sgn in (-1, 1):
                agg = _aggregate(regs, delta, lam, alpha, cc, kind, 1 + sgn * shock)
                rows.append({"factor": kind, "crop_code": cc, "shock": sgn * shock, **agg})
    for a in (0.1, 0.3):
        rows.append({"factor": "alpha", "crop_code": "", "shock": a, **_aggregate(regs, delta, lam, a)})
    for l in (0.0, 1.0):
        rows.append({"factor": "lambda", "crop_code": "", "shock": l, **_aggregate(regs, delta, l, alpha)})
    return pd.DataFrame(rows)


def _aggregate(regs, delta, lam, alpha, cc=None, kind=None, mult=1.0) -> dict:
    gain = cgain = 0.0
    shift = {c: 0.0 for c in I.CROPS}
    for r in regs.values():
        pm = np.ones(len(r.crops))
        cm = np.ones(len(r.crops))
        if cc in r.crops:
            (pm if kind == "price" else cm)[r.crops.index(cc)] = mult
        pr = r.problem(pm, cm)
        s0 = evaluate(pr, r.x0, alpha, lam)
        s1 = solve(pr, lam, alpha, delta)
        k = r.pool_kha * 1e3 / 1e6
        gain += (s1.mean - s0.mean) * k
        cgain += (s1.cvar - s0.cvar) * k
        for c, d in zip(r.crops, s1.x - r.x0):
            shift[c] += d * r.pool_kha
    return {"gain_mln": gain, "cvar_gain_mln": cgain, **{f"shift_kha_{c}": v for c, v in shift.items()}}


# ---------------------------------------------------------------- проверка на отложенных годах
def backtest(years, deltas, lam: float, alpha: float, window: int = 20, control: float = 0.1) -> pd.DataFrame:
    """План на год t выбирается только по данным до t: сценарии — отклонения от тренда за годы < t,
    тренд — по годам < t, цены — года t−1, текущий план — структура площадей t−1. Результат считается
    по фактической урожайности и ценам года t. Сравнение: оптимальный план против текущего."""
    rows = []
    Y = I.yields_wide()
    for t in years:
        yrs = [s for s in range(t - window, t) if s >= 2006]
        scen = I.hist_scenarios(t, yrs)
        regs = regions_for(scen, t, price_year=t - 1, cost_year=t - 1)
        for ok, r in regs.items():
            y_real = np.array([Y.loc[(ok, cc)].get(t, np.nan) if (ok, cc) in Y.index else np.nan for cc in r.crops])
            p_real = np.array([I.price(ok, cc, t) for cc in r.crops])
            lvl = I.rf_trend_level()
            ratio = r.yields.mean(1) / lvl.reindex(r.crops).to_numpy()
            c_real = np.array([I.cost(cc, q, t) for cc, q in zip(r.crops, ratio)])
            pr = r.problem()
            s0 = evaluate(pr, r.x0, alpha, lam)
            plans = {"current": (r.x0, s0)}
            for d in deltas:
                s = solve(pr, lam, alpha, d)
                plans[f"d{'all' if d is None else int(round(d * 100))}"] = (s.x, s)
            # контрольные планы при δ = control: без учёта риска (λ = 0) и по точечному прогнозу (один сценарий — среднее)
            s = solve(pr, 0.0, alpha, control)
            plans[f"d{int(round(control * 100))}_mean_only"] = (s.x, evaluate(pr, s.x, alpha, lam))
            pt = Problem(r.crops, pr.R.mean(1, keepdims=True), r.x0, hi=pr.hi, groups=pr.groups)
            s = solve(pt, 0.0, alpha, control)
            plans[f"d{int(round(control * 100))}_point"] = (s.x, evaluate(pr, s.x, alpha, lam))
            used = np.zeros(len(r.crops), bool)
            for x, _ in plans.values():
                used |= x > 0.005
            if not np.all(np.isfinite(y_real[used])) or not np.all(np.isfinite(p_real[used])):
                continue
            real = np.where(np.isfinite(y_real), y_real, 0) * p_real - c_real
            base_real = float(r.x0 @ real)
            for name, (x, s) in plans.items():
                rows.append({"year": t, "okato": ok, "plan": name, "pool_kha": r.pool_kha, "n_scen": len(r.scen_years),
                             "exp_rub_ha": s.mean, "exp_cvar_rub_ha": s.cvar, "exp_gain_rub_ha": s.mean - s0.mean,
                             "real_rub_ha": float(x @ real), "real_gain_rub_ha": float(x @ real) - base_real,
                             "turnover": float(np.abs(x - r.x0).sum() / 2)})
    return pd.DataFrame(rows)


def backtest_summary(bt: pd.DataFrame, alpha: float) -> pd.DataFrame:
    """Сводка по планам: средний фактический выигрыш (взвешенный по площади), доля случаев с выигрышем,
    обещанный выигрыш, «плохие годы» — худшие α региональных лет по прибыли текущего плана."""
    base = bt[bt.plan == "current"].set_index(["year", "okato"]).real_rub_ha
    out = []
    for name, g in bt.groupby("plan", sort=False):
        g = g.set_index(["year", "okato"])
        w = g.pool_kha
        gain = g.real_gain_rub_ha
        # плохие годы: в каждом субъекте худшие α его лет по факту текущего плана
        bad = []
        for ok, gg in base.groupby(level="okato"):
            k = max(1, int(round(alpha * len(gg))))
            bad += list(gg.nsmallest(k).index)
        gb = g.loc[g.index.isin(bad)]
        out.append({"plan": name, "n": len(g), "turnover_pct": 100 * np.average(g.turnover, weights=w),
                    "exp_gain_rub_ha": np.average(g.exp_gain_rub_ha, weights=w),
                    "real_gain_rub_ha": np.average(gain, weights=w),
                    "real_gain_bln_year": (gain * w).groupby(level="year").sum().mean() * 1e3 / 1e9,
                    "win_share_pct": 100 * float((gain > 1e-6).sum() / max(1, (gain.abs() > 1e-6).sum())),
                    "bad_years_gain_rub_ha": np.average(gb.real_gain_rub_ha, weights=gb.pool_kha) if len(gb) else np.nan,
                    "bad_years_profit_rub_ha": np.average(gb.real_rub_ha, weights=gb.pool_kha) if len(gb) else np.nan})
    return pd.DataFrame(out)
