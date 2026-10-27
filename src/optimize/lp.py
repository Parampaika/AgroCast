"""Сценарная оптимизация структуры посевов с риск-мерой CVaR (линейное программирование).

Решение — доли площади культур x_c (Σx = 1). Прибыль на 1 га в сценарии s: π_s(x) = Σ_c x_c·R_cs,
где R_cs = y_cs·p_c − cost_c (руб./га). Цель:

    max (1 − λ)·E_p[π(x)] + λ·CVaR_α(π(x)),

CVaR_α(π) — средняя прибыль в худших α долях сценариев (с весами p_s). По Рокафеллару–Урясеву
CVaR_α(π) = −min_η { η + (1/α)·Σ_s p_s·max(0, −π_s − η) }, поэтому задача линейна:

    min −(1 − λ)·Σ_s p_s π_s + λ·(η + (1/α)·Σ_s p_s u_s)
    u_s ≥ −π_s − η,  u_s ≥ 0,  Σ_c x_c = 1,
    max(lo_c, x0_c − δ) ≤ x_c ≤ min(hi_c, x0_c + δ),   Σ_{c∈G} x_c ≤ g_G,
    [по желанию] ½·Σ_c |x_c − x0_c| ≤ τ (общий перенос площади).

Решатель — HiGHS через scipy.optimize.linprog (точный симплекс, без лишних зависимостей).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linprog


def cvar_lower(values, p=None, alpha: float = 0.2) -> float:
    """Средняя прибыль в худших α долях сценариев с весами p (дробный «атом» на границе учитывается)."""
    v = np.asarray(values, float)
    p = np.full(len(v), 1 / len(v)) if p is None else np.asarray(p, float) / np.sum(p)
    o = np.argsort(v, kind="stable")
    v, p = v[o], p[o]
    take = np.minimum(p, np.maximum(0.0, alpha - (np.cumsum(p) - p)))
    return float(np.dot(take, v) / alpha)


@dataclass
class Problem:
    """Одна задача: субъект (или хозяйство) с пулом культур и матрицей прибыли R (культура × сценарий)."""
    crops: list[str]
    R: np.ndarray                    # руб./га, shape (n_crops, n_scen)
    x0: np.ndarray                   # текущий план, доли
    lo: np.ndarray | None = None     # нижние границы долей (по умолчанию 0)
    hi: np.ndarray | None = None     # верхние границы (севооборот), по умолчанию 1
    p: np.ndarray | None = None      # веса сценариев
    groups: list[tuple[np.ndarray, float]] = field(default_factory=list)  # (маска культур, max суммы долей)

    def __post_init__(self):
        n, s = self.R.shape
        self.lo = np.zeros(n) if self.lo is None else np.asarray(self.lo, float)
        self.hi = np.ones(n) if self.hi is None else np.asarray(self.hi, float)
        self.p = np.full(s, 1 / s) if self.p is None else np.asarray(self.p, float) / np.sum(self.p)
        self.x0 = np.asarray(self.x0, float)


@dataclass
class Solution:
    x: np.ndarray
    status: str
    mean: float        # E[π], руб./га
    cvar: float        # CVaR_α(π), руб./га
    objective: float
    profits: np.ndarray


def evaluate(pr: Problem, x, alpha: float, lam: float) -> Solution:
    prof = np.asarray(x) @ pr.R
    m, c = float(prof @ pr.p), cvar_lower(prof, pr.p, alpha)
    return Solution(np.asarray(x, float), "eval", m, c, (1 - lam) * m + lam * c, prof)


def solve(pr: Problem, lam: float = 0.5, alpha: float = 0.2, delta: float | None = None,
          turnover: float | None = None) -> Solution:
    """Оптимальный план. delta — макс. изменение доли каждой культуры; turnover — макс. общий перенос."""
    n, S = pr.R.shape
    lo, hi = pr.lo.copy(), pr.hi.copy()
    if delta is not None:
        lo = np.maximum(lo, pr.x0 - delta)
        hi = np.minimum(hi, pr.x0 + delta)
    # текущий план всегда допустим: границы не уже текущих долей
    lo = np.minimum(lo, pr.x0)
    hi = np.maximum(hi, pr.x0)
    use_t = turnover is not None
    nt = n if use_t else 0
    # переменные: x (n), η (1), u (S), t (nt)
    nv = n + 1 + S + nt
    c = np.zeros(nv)
    c[:n] = -(1 - lam) * (pr.R @ pr.p)
    c[n] = lam
    c[n + 1:n + 1 + S] = lam * pr.p / alpha
    A_ub, b_ub = [], []
    # −π_s − η − u_s ≤ 0
    blk = np.zeros((S, nv))
    blk[:, :n] = -pr.R.T
    blk[:, n] = -1
    blk[np.arange(S), n + 1 + np.arange(S)] = -1
    A_ub.append(blk)
    b_ub.append(np.zeros(S))
    for mask, g in pr.groups:
        row = np.zeros((1, nv))
        row[0, :n] = mask
        A_ub.append(row)
        b_ub.append([max(g, float(mask @ pr.x0))])
    if use_t:
        k = n + 1 + S
        blk = np.zeros((2 * n, nv))
        blk[:n, :n] = np.eye(n)
        blk[:n, k:k + n] = -np.eye(n)
        blk[n:, :n] = -np.eye(n)
        blk[n:, k:k + n] = -np.eye(n)
        A_ub.append(blk)
        b_ub.append(np.r_[pr.x0, -pr.x0])
        row = np.zeros((1, nv))
        row[0, k:k + n] = 0.5
        A_ub.append(row)
        b_ub.append([turnover])
    A_eq = np.zeros((1, nv))
    A_eq[0, :n] = 1
    bounds = [(lo[i], hi[i]) for i in range(n)] + [(None, None)] + [(0, None)] * S + [(0, None)] * nt
    # масштаб: рубли → тыс. руб., чтобы симплекс не страдал от больших коэффициентов
    scale = max(1.0, float(np.abs(pr.R).max()) / 1e3)
    res = linprog(c / scale, A_ub=np.vstack(A_ub), b_ub=np.concatenate(b_ub), A_eq=A_eq, b_eq=[1.0],
                  bounds=bounds, method="highs")
    if res.status != 0:
        sol = evaluate(pr, pr.x0, alpha, lam)
        sol.status = "fail: " + res.message
        return sol
    x = np.clip(res.x[:n], 0, 1)
    x = x / x.sum()
    sol = evaluate(pr, x, alpha, lam)
    sol.status = "ok"
    return sol
