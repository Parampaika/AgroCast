"""Проверки модуля оптимизации структуры посевов (uv run pytest -q tests/test_optimize.py).

Игрушечные задачи — без данных; последняя проверка собирает задачу по data/clean и пропускается, если слоя нет.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "optimize"
sys.path.insert(0, str(SRC))
from lp import Problem, cvar_lower, evaluate, solve  # noqa: E402


def test_cvar_toy():
    # 10 равновероятных сценариев, α = 0,2 → среднее двух худших
    v = np.array([5, -3, 7, 1, 0, 10, -8, 4, 2, 6], float)
    assert cvar_lower(v, alpha=0.2) == pytest.approx((-8 - 3) / 2)
    # дробная граница: α = 0,25 → (−8 − 3 + 0,5·0) / 2,5
    assert cvar_lower(v, alpha=0.25) == pytest.approx((-8 - 3 + 0.5 * 0) / 2.5)
    # веса: худший сценарий с весом 0,3 при α = 0,2 целиком определяет CVaR
    p = np.array([0.3] + [0.7 / 9] * 9)
    assert cvar_lower(v[[6, 0, 1, 2, 3, 4, 5, 7, 8, 9]], p, alpha=0.2) == pytest.approx(-8)
    # α = 1 → среднее
    assert cvar_lower(v, alpha=1.0) == pytest.approx(v.mean())


def test_lp_cvar_matches_bruteforce():
    """λ = 1: LP максимизирует CVaR; сверяем с перебором по сетке на симплексе из трёх культур."""
    rng = np.random.default_rng(0)
    R = rng.normal([[10], [8], [6]], [[12], [6], [2]], size=(3, 20))
    R[0] += 0.5 * R[1]   # совместность
    pr = Problem(["a", "b", "c"], R, np.array([1 / 3, 1 / 3, 1 / 3]))
    for lam in (0.0, 0.5, 1.0):
        s = solve(pr, lam=lam, alpha=0.2)
        assert s.status == "ok"
        assert s.objective == pytest.approx((1 - lam) * s.mean + lam * s.cvar)
        best = -np.inf
        g = np.linspace(0, 1, 101)
        for a in g:
            for b in g[g <= 1 - a + 1e-12]:
                best = max(best, evaluate(pr, [a, b, 1 - a - b], 0.2, lam).objective)
        assert s.objective >= best - 1e-6
        assert s.objective <= best + 0.05 * abs(best) + 1e-6   # сетка шагом 1 % почти точна


def test_constraints_hold():
    rng = np.random.default_rng(1)
    n = 5
    R = rng.normal(5, 4, size=(n, 25)) + np.arange(n)[:, None] * 3
    x0 = np.array([0.4, 0.3, 0.1, 0.1, 0.1])
    hi = np.array([1, 1, 1, 0.25, 0.15])
    grp = [(np.array([1, 1, 0, 0, 0], float), 0.75), (np.array([0, 0, 0, 1, 1], float), 0.3)]
    pr = Problem(list("abcde"), R, x0, hi=hi, groups=grp)
    for d in (0.05, 0.1, 0.2, None):
        for lam in (0, 0.5, 1):
            s = solve(pr, lam=lam, alpha=0.2, delta=d)
            x = s.x
            assert s.status == "ok"
            assert x.sum() == pytest.approx(1)
            assert (x >= -1e-9).all()
            assert (x <= np.maximum(hi, x0) + 1e-7).all()
            if d is not None:
                assert np.abs(x - x0).max() <= d + 1e-7
            for m, g in grp:
                assert m @ x <= max(g, m @ x0) + 1e-7
            # оптимум не хуже текущего плана
            assert s.objective >= evaluate(pr, x0, 0.2, lam).objective - 1e-6
    s = solve(pr, lam=0.5, alpha=0.2, turnover=0.1)
    assert np.abs(s.x - x0).sum() / 2 <= 0.1 + 1e-7


def test_delta_zero_returns_current_plan():
    rng = np.random.default_rng(2)
    R = rng.normal(0, 10, size=(4, 15))
    x0 = np.array([0.5, 0.2, 0.2, 0.1])
    pr = Problem(list("abcd"), R, x0, hi=np.array([0.3, 1, 1, 1]))   # x0 выше нормы — тоже допустим
    s = solve(pr, lam=0.5, alpha=0.2, delta=0.0)
    assert s.status == "ok"
    np.testing.assert_allclose(s.x, x0, atol=1e-9)


def test_more_freedom_never_worse():
    rng = np.random.default_rng(3)
    R = rng.normal(5, 6, size=(4, 20))
    pr = Problem(list("abcd"), R, np.full(4, 0.25))
    vals = [solve(pr, 0.5, 0.2, d).objective for d in (0, 0.05, 0.1, 0.2, None)]
    assert all(b >= a - 1e-9 for a, b in zip(vals, vals[1:]))


def test_real_region_problem():
    clean = Path(__file__).resolve().parents[1] / "data" / "clean" / "yield_panel.parquet"
    if not clean.exists():
        pytest.skip("нет data/clean")
    import inputs as I
    import problems as P
    sc = I.hist_scenarios(2026, list(range(2005, 2025)))
    r = P.build("03000000000", 2026, sc, 2026)   # Краснодарский край
    assert r is not None and len(r.crops) >= 4
    assert r.x0.sum() == pytest.approx(1)
    assert np.isfinite(r.yields).all() and (r.yields > 0).all()
    s = solve(r.problem(), 0.5, 0.2, 0.05)
    assert s.status == "ok" and np.abs(s.x - r.x0).max() <= 0.05 + 1e-7


def test_model_scenarios_schema():
    """Таблица сценариев модели приводится к схеме оптимизатора; для плана берётся дата до сезона."""
    import pandas as pd
    import inputs as I
    df = pd.DataFrame({"okato": ["1", "1", "1", "1"], "crop_code": ["1010400"] * 4,
                       "forecast_date": ["pre_season", "pre_season", "final", "final"],
                       "scenario_year": [2005, 2006, 2005, 2006], "yield_t_ha": [3.0, 2.0, 9.0, 9.0]})
    out = I._normalize(df, "test")
    assert set(out.scenario_year) == {2005, 2006}
    assert out.yield_t_ha.tolist() == [3.0, 2.0]
    assert "pre_season" in out.source.iloc[0]
    assert {"okato", "crop_code", "scenario_year", "yield_t_ha", "weight"} <= set(out.columns)
