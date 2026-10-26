"""Скользящая проверка по времени и метрики.

Конфигурация = культура (или pooled) × дата × тренд × цель × набор признаков × модель
× гиперпараметры × правило выборки. Для каждого тестового года T модель обучается
на сезонах < T, нормы погоды — тоже по сезонам < T. Годы 2009–2011 — разогрев для
конформного интервала: их прогнозы в метрики точности не входят.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from model import data as D
from model.models import Model

EVAL_YEARS = list(range(2012, 2026))
WARMUP_YEARS = [2009, 2010, 2011]
DEV_YEARS = list(range(2012, 2019))     # на них подбираются гиперпараметры (Optuna)
LATE_YEARS = list(range(2019, 2026))    # в подборе гиперпараметров не участвуют
TRAIN_FROM = 2003

FEATSETS = {
    "F0": [],                               # только тренд + свободный член модели
    "F1": ["m"],                            # месячные аномалии
    "F2": ["m", "w"],                       # + окно культуры, зима, запас влаги
    "F3": ["m", "w", "c", "s"],             # + климат региона и почвы
    "F4": ["m", "w", "c", "s", "n"],        # + NDVI
    "F5": ["m", "w", "c", "s", "n", "r"],   # + регион, ФО, прошлые отклонения
    "F2r": ["m", "w", "r"],                 # F2 + регион и прошлые отклонения, без почв и NDVI
}
CAT_COLS = ["cat:okato", "cat:fo", "cat:crop"]


@dataclass(frozen=True)
class Config:
    crop: str            # ключ культуры или "pooled"
    date: str = "end"
    trend: str = "lin_all"
    target: str = "ratio"
    feats: str = "F2"
    model: str = "ridge"
    params: str = "{}"   # json
    sample: str = "all"  # all | no_mismatch | no_lo
    norm: str = "fold"   # fold | fixed2021

    @property
    def id(self) -> str:
        return hashlib.md5(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:12]

    def as_dict(self) -> dict:
        return {**asdict(self), "cfg_id": self.id}


_CODES: dict[str, dict] = {}


def _code(kind: str, values: pd.Series) -> np.ndarray:
    if kind not in _CODES:
        if kind == "okato":
            lv = sorted(D.load_soil().index)
        elif kind == "fo":
            lv = sorted(set(D.load_panel().fo.dropna()))
        else:
            lv = sorted(D.CROP_NAME)
        _CODES[kind] = {v: i for i, v in enumerate(lv)}
    return values.map(_CODES[kind]).fillna(-1).to_numpy(float)


def _crop_matrix(crop: str, cfg: Config, T: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(строки культуры с годами ≤ T, признаки этих строк) для фолда T."""
    f = D.crop_frame(crop)
    f = f[(f.year <= T) & (f.year >= TRAIN_FROM)]
    blocks = FEATSETS[cfg.feats]
    fg = D.feature_grid(crop, cfg.date)
    cols = [c for b in blocks if b in fg.blocks for c in fg.blocks[b]]
    if cols:
        X = D.fold_features(fg, T, cols, cfg.norm)
        X = X.reindex(pd.MultiIndex.from_arrays([f.okato, f.year])).reset_index(drop=True)
    else:
        X = pd.DataFrame(index=range(len(f)))
    f = f.reset_index(drop=True)
    if "r" in blocks:
        X["cat:okato"] = _code("okato", f.okato)
        X["cat:fo"] = _code("fo", f.fo)
        X["r1"] = f[f"r1_{cfg.trend}"].to_numpy()
        X["r2"] = f[f"r2_{cfg.trend}"].to_numpy()
    return f, X


def eval_mask(f: pd.DataFrame) -> np.ndarray:
    """Общие строки оценки: есть цель, все тренды и все бейзлайны."""
    ok = f.y.notna()
    for k in D.TREND_TYPES:
        ok &= f[f"tr_{k}"].notna()
    for b in D.BASELINES:
        ok &= f[f"bl_{b}"].notna()
    return ok.to_numpy()


def run_config(cfg: Config, years: list[int] | None = None) -> pd.DataFrame:
    """Прогнозы конфигурации на годы years (по умолчанию разогрев + 2012–2025)."""
    years = years or (WARMUP_YEARS + EVAL_YEARS)
    crops = sorted(D.CROP_NAME) if cfg.crop == "pooled" else [cfg.crop]
    params = json.loads(cfg.params)
    out = []
    for T in years:
        parts = []
        for crop in crops:
            f, X = _crop_matrix(crop, cfg, T)
            if cfg.crop == "pooled":
                X["cat:crop"] = _code("crop", f.crop)
            parts.append((f, X))
        f = pd.concat([p[0] for p in parts], ignore_index=True)
        X = pd.concat([p[1] for p in parts], ignore_index=True)
        tr = f[f"tr_{cfg.trend}"].to_numpy()
        y = f.y.to_numpy()
        z = D.make_target(y, tr, cfg.target)
        train = (f.year < T).to_numpy() & np.isfinite(z)
        if cfg.sample == "no_mismatch":
            train &= ~f.flag_mismatch.to_numpy()
        elif cfg.sample == "no_lo":
            train &= ~f.flag_lo.to_numpy()
        test = (f.year == T).to_numpy() & eval_mask(f)
        if not test.any():
            continue
        if cfg.model == "trend":
            zhat = np.zeros(test.sum())
        elif X.shape[1] == 0:
            zhat = np.full(test.sum(), np.mean(z[train]))  # только свободный член
        else:
            cats = [c for c in CAT_COLS if c in X]
            m = Model(cfg.model, params, cats).fit(X[train], z[train])
            zhat = m.predict(X[test])
        yhat = D.invert_target(zhat, tr[test], cfg.target)
        yhat = np.where(np.isfinite(yhat) & (yhat > 0), yhat, tr[test])
        g = f.loc[test, ["crop", "okato", "year", "y", "area_kha", "is_proxy",
                         "bl_lin10", "bl_mean5", "bl_lag1"]].copy()
        g["trend"] = tr[test]
        g["yhat"] = yhat
        out.append(g)
    return pd.concat(out, ignore_index=True)


# ---------------------------------------------------------------- метрики
def conformal(p: pd.DataFrame, alpha: float = 0.2, window: int | None = None,
              kind: str = "rel") -> pd.DataFrame:
    """Интервал года T по ошибкам прогнозов прошлых лет (< T) той же культуры."""
    p = p.copy()
    p["lo"] = np.nan
    p["hi"] = np.nan
    e = p.y / p.yhat - 1 if kind == "rel" else p.y - p.yhat
    for (crop, T), idx in p.groupby(["crop", "year"]).groups.items():
        past = (p.crop == crop) & (p.year < T)
        if window:
            past &= p.year >= T - window
        ep = e[past].dropna()
        if len(ep) < 30:
            continue
        ql, qh = np.quantile(ep, [alpha / 2, 1 - alpha / 2])
        yh = p.loc[idx, "yhat"]
        p.loc[idx, "lo"] = yh * (1 + ql) if kind == "rel" else yh + ql
        p.loc[idx, "hi"] = yh * (1 + qh) if kind == "rel" else yh + qh
    return p


def metrics(p: pd.DataFrame, years: list[int] | None = None, pred: str = "yhat") -> dict:
    years = years or EVAL_YEARS
    q = p[p.year.isin(years)]
    if q.empty:
        return {}
    err = (q[pred] - q.y).abs()
    ape = err / q.y
    w = q.area_kha.fillna(q.area_kha.median())
    out = {"n": int(len(q)), "mae": float(err.mean()), "mape": float(100 * ape.mean()),
           "wmape": float(100 * (ape * w).sum() / w.sum()),
           "bias_pct": float(100 * ((q[pred] - q.y) / q.y).median())}
    for b in D.BASELINES:
        out[f"mae_bl_{b}"] = float((q[f"bl_{b}"] - q.y).abs().mean())
    best = min(out[f"mae_bl_{b}"] for b in D.BASELINES)
    out["mae_best_bl"] = best
    out["gain_pct"] = float(100 * (1 - out["mae"] / best))
    if "lo" in q and q.lo.notna().any():
        c = q[q.lo.notna()]
        out["cov80"] = float(((c.y >= c.lo) & (c.y <= c.hi)).mean())
        out["width80_pct"] = float(100 * ((c.hi - c.lo) / c[pred]).mean())
    return out


def summarize(cfg: Config, p: pd.DataFrame) -> list[dict]:
    """Строки результатов: по каждой культуре конфигурации (у pooled — по всем)."""
    p = conformal(p)
    rows = []
    for crop, q in p.groupby("crop"):
        r = {**cfg.as_dict(), "eval_crop": crop}
        r.update(metrics(q))
        r.update({f"dev_{k}": v for k, v in metrics(q, DEV_YEARS).items() if k in ("mae", "gain_pct")})
        r.update({f"late_{k}": v for k, v in metrics(q, LATE_YEARS).items() if k in ("mae", "gain_pct")})
        r["mae_by_year"] = json.dumps({int(y): round(float((g.yhat - g.y).abs().mean()), 4)
                                       for y, g in q[q.year.isin(EVAL_YEARS)].groupby("year")})
        rows.append(r)
    return rows
