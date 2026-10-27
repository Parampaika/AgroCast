"""Сборка задачи оптимизации для субъекта: пул культур, текущий план, матрица прибыли, нормы севооборота."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import inputs as I
from lp import Problem


@dataclass
class Region:
    okato: str
    year: int                    # сезон, для которого ищем план
    crops: list[str]
    x0: np.ndarray               # текущий план — структура площадей пула в году year−1
    pool_kha: float              # площадь пула (сумма культур) в году year−1
    sown_kha: float              # вся посевная площадь субъекта
    yields: np.ndarray           # т/га, культура × сценарий
    prices: np.ndarray           # руб./т
    costs: np.ndarray            # руб./га
    scen_years: list[int]
    weights: np.ndarray
    hi: np.ndarray               # верхние границы долей пула (севооборот)
    groups: list[tuple[np.ndarray, float]] = field(default_factory=list)
    group_names: list[str] = field(default_factory=list)

    def problem(self, price_mult=None, cost_mult=None) -> Problem:
        pm = np.ones(len(self.crops)) if price_mult is None else np.asarray(price_mult)
        cm = np.ones(len(self.crops)) if cost_mult is None else np.asarray(cost_mult)
        R = self.yields * (self.prices * pm)[:, None] - (self.costs * cm)[:, None]
        return Problem(self.crops, R, self.x0, hi=self.hi, p=self.weights, groups=self.groups)


def pool_crops(ok: str, year: int, scen: pd.DataFrame) -> list[str]:
    """Культуры субъекта, которые можно перераспределять: есть сценарии, площадь и ряд наблюдений."""
    cfg = I.config()["pool"]
    A, Y = I.area_wide(), I.yields_wide()
    y0, y1 = I.config()["scenarios"]["years"]
    out = []
    for cc in I.CROPS:
        if (ok, cc) not in A.index or (ok, cc) not in Y.index:
            continue
        a = A.loc[(ok, cc), [c for c in A.columns if year - 5 <= c < year]].mean()
        n = Y.loc[(ok, cc), [c for c in Y.columns if c < year]].notna().sum()
        if a >= cfg["min_area_kha"] and n >= cfg["min_years"] and cc in scen:
            out.append(cc)
    return out


def build(ok: str, year: int, scen_long: pd.DataFrame, price_year: int, cost_year: int | None = None) -> Region | None:
    """Задача для субъекта ok на сезон year по таблице сценариев (okato, crop_code, scenario_year, yield_t_ha)."""
    cfg = I.config()
    sc = scen_long[scen_long.okato == ok]
    if sc.empty:
        return None
    W = sc.pivot_table(index="crop_code", columns="scenario_year", values="yield_t_ha", aggfunc="first")
    crops = pool_crops(ok, year, set(W.index))
    if len(crops) < cfg["pool"]["min_crops"]:
        return None
    W = W.loc[crops].dropna(axis=1, how="any")
    if W.shape[1] < 5:
        return None
    A = I.area_wide()
    # площадь года year−1; пропуск (например, подсолнечник 2025 г. в 31328) — последнее значение за 3 года
    area = np.array([A.loc[(ok, cc), [c for c in A.columns if year - 3 <= c < year]].ffill().iloc[-1]
                     if (ok, cc) in A.index else np.nan for cc in crops], float)
    area = np.nan_to_num(area)
    if area.sum() <= 0:
        return None
    x0 = area / area.sum()
    pool = float(area.sum())
    sown = I.last_value(I.total_area("6"), ok, year - 1)
    if not np.isfinite(sown) or sown < pool:
        sown = pool
    yrs = list(W.columns)
    Ymat = W.loc[crops, yrs].to_numpy(float)
    wts = sc.groupby("scenario_year").weight.mean().reindex(yrs).fillna(1.0).to_numpy()
    prices = np.array([I.price(ok, cc, price_year) for cc in crops])
    if not np.all(np.isfinite(prices)):
        return None
    lvl = I.rf_trend_level()
    ratio = Ymat.mean(1) / lvl.reindex(crops).to_numpy()
    costs = np.array([I.cost(cc, r, cost_year or year) for cc, r in zip(crops, ratio)])
    # севооборот: доля во всей посевной → доля пула; не ниже текущей
    ms = cfg["rotation"]["max_share"]
    hi = np.array([ms.get(cc, 1.0) * sown / pool for cc in crops])
    for cc in cfg["rotation"].get("no_expand", []):
        if cc in crops:
            hi[crops.index(cc)] = x0[crops.index(cc)]
    hi = np.minimum(1.0, np.maximum(hi, x0))
    groups, names = [], []
    for g in cfg["rotation"]["groups"]:
        mask = np.array([cc in g["crops"] for cc in crops], float)
        if mask.sum() < 1:
            continue
        outside = 0.0
        if g.get("include_outside"):
            tot = I.last_value(I.total_area(g["include_outside"]), ok, year - 1)
            if np.isfinite(tot):
                outside = max(0.0, tot - float(mask @ area))
        cap = (g["max_share"] * sown - outside) / pool
        groups.append((mask, max(cap, float(mask @ x0))))
        names.append(g["name"])
    return Region(ok, year, crops, x0, pool, sown, Ymat, prices, costs, yrs, wts, hi, groups, names)
