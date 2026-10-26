"""Модели перебора с общим интерфейсом fit(X, y) / predict(X).

X — DataFrame; категориальные колонки (регион, ФО, культура) приходят целыми кодами,
пропуски — NaN. Линейным моделям и лесам пропуски заполняются медианой фолда,
линейным категории разворачиваются в one-hot.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

MODELS = ["ridge", "enet", "rf", "et", "hgb", "lgbm", "cat", "xgb"]

DEFAULTS = {
    "ridge": {"alpha": 300.0},
    "enet": {"alpha": 0.01, "l1_ratio": 0.5},
    "rf": {"n_estimators": 300, "min_samples_leaf": 10, "max_features": 0.33},
    "et": {"n_estimators": 300, "min_samples_leaf": 10, "max_features": 0.5},
    "hgb": {"max_depth": 3, "max_iter": 300, "learning_rate": 0.04, "min_samples_leaf": 25,
            "l2_regularization": 0.0, "loss": "squared_error"},
    "lgbm": {"n_estimators": 400, "learning_rate": 0.03, "num_leaves": 8, "min_child_samples": 25,
             "subsample": 0.8, "colsample_bytree": 0.5, "reg_lambda": 1.0, "objective": "regression"},
    "cat": {"iterations": 600, "depth": 4, "learning_rate": 0.04, "l2_leaf_reg": 5.0,
            "loss_function": "RMSE"},
    "xgb": {"n_estimators": 400, "max_depth": 3, "learning_rate": 0.04, "subsample": 0.8,
            "colsample_bytree": 0.5, "min_child_weight": 10.0, "reg_lambda": 1.0,
            "objective": "reg:squarederror"},
}


def suggest(trial, name: str) -> dict:
    """Пространство гиперпараметров Optuna."""
    f, i, c = trial.suggest_float, trial.suggest_int, trial.suggest_categorical
    if name == "ridge":
        return {"alpha": f("alpha", 1.0, 1e4, log=True)}
    if name == "enet":
        return {"alpha": f("alpha", 1e-4, 0.3, log=True), "l1_ratio": f("l1_ratio", 0.05, 1.0)}
    if name in ("rf", "et"):
        return {"n_estimators": i("n_estimators", 150, 600, step=50),
                "min_samples_leaf": i("min_samples_leaf", 2, 40, log=True),
                "max_features": f("max_features", 0.1, 0.8)}
    if name == "hgb":
        return {"max_depth": i("max_depth", 2, 6), "max_iter": i("max_iter", 100, 800, step=50),
                "learning_rate": f("learning_rate", 0.01, 0.15, log=True),
                "min_samples_leaf": i("min_samples_leaf", 10, 80, log=True),
                "l2_regularization": f("l2_regularization", 1e-3, 10, log=True),
                "loss": c("loss", ["squared_error", "absolute_error"])}
    if name == "lgbm":
        return {"n_estimators": i("n_estimators", 100, 1000, step=50),
                "learning_rate": f("learning_rate", 0.01, 0.15, log=True),
                "num_leaves": i("num_leaves", 4, 31, log=True),
                "min_child_samples": i("min_child_samples", 10, 80, log=True),
                "subsample": f("subsample", 0.5, 1.0), "colsample_bytree": f("colsample_bytree", 0.2, 1.0),
                "reg_lambda": f("reg_lambda", 1e-3, 30, log=True),
                "objective": c("objective", ["regression", "huber", "regression_l1"])}
    if name == "cat":
        return {"iterations": i("iterations", 200, 800, step=100), "depth": i("depth", 3, 6),
                "learning_rate": f("learning_rate", 0.01, 0.15, log=True),
                "l2_leaf_reg": f("l2_leaf_reg", 0.5, 30, log=True),
                "loss_function": c("loss_function", ["RMSE", "MAE", "Huber:delta=0.15"])}
    if name == "xgb":
        return {"n_estimators": i("n_estimators", 100, 1000, step=50), "max_depth": i("max_depth", 2, 6),
                "learning_rate": f("learning_rate", 0.01, 0.15, log=True),
                "subsample": f("subsample", 0.5, 1.0), "colsample_bytree": f("colsample_bytree", 0.2, 1.0),
                "min_child_weight": f("min_child_weight", 1, 50, log=True),
                "reg_lambda": f("reg_lambda", 1e-3, 30, log=True),
                "objective": c("objective", ["reg:squarederror", "reg:pseudohubererror", "reg:absoluteerror"])}
    raise ValueError(name)


def _safe(c: str) -> str:
    """LightGBM и XGBoost не принимают «:» в именах признаков."""
    return c.replace(":", "__")


class Model:
    def __init__(self, name: str, params: dict | None = None, cat_cols: list[str] | None = None,
                 seed: int = 0):
        self.name = name
        self.params = {**DEFAULTS[name], **(params or {})}
        self.cat_cols = [_safe(c) for c in (cat_cols or [])]
        self.seed = seed

    # подготовка матрицы
    def _prep(self, X: pd.DataFrame, fit: bool) -> np.ndarray | pd.DataFrame:
        cats = [c for c in self.cat_cols if c in X]
        num = [c for c in X.columns if c not in cats]
        if self.name in ("ridge", "enet", "rf", "et"):
            xn = X[num].to_numpy(np.float64)
            if fit:
                med = np.nanmedian(xn, axis=0) if len(xn) else np.zeros(xn.shape[1])
                self._med = np.where(np.isnan(med), 0.0, med)
            xn = np.where(np.isnan(xn), self._med, xn)
            if self.name in ("ridge", "enet"):
                if fit:
                    self._mu, sd = xn.mean(0), xn.std(0)
                    self._sd = np.where(sd > 1e-9, sd, 1.0)
                xn = (xn - self._mu) / self._sd
                if cats:
                    if fit:
                        self._levels = {c: np.unique(X[c].dropna().astype(int)) for c in cats}
                    oh = [(X[c].to_numpy()[:, None] == self._levels[c][None, :]).astype(float)
                          for c in cats]
                    xn = np.hstack([xn] + oh)
                return xn
            return np.hstack([xn, X[cats].fillna(-1).to_numpy(float)]) if cats else xn
        if self.name == "lgbm":
            Z = X.copy()
            for c in cats:
                Z[c] = pd.Categorical(Z[c].fillna(-1).astype(int), categories=self._levels_of(X, c, fit))
            return Z
        if self.name == "cat":
            Z = X.copy()
            for c in cats:
                Z[c] = Z[c].fillna(-1).astype(int)
            return Z
        if self.name == "hgb":
            Z = X.copy()
            for c in cats:
                Z[c] = Z[c].fillna(-1).astype(int).clip(lower=-1)
            return Z
        return X.to_numpy(np.float64)

    def _levels_of(self, X, c, fit):
        if fit:
            self._lv = getattr(self, "_lv", {})
            self._lv[c] = sorted(set(X[c].fillna(-1).astype(int)))
        return self._lv[c]

    def fit(self, X: pd.DataFrame, y: np.ndarray):
        X = X.rename(columns=_safe)
        p = dict(self.params)
        Z = self._prep(X, fit=True)
        cats = [c for c in self.cat_cols if c in X]
        n = self.name
        if n == "ridge":
            from sklearn.linear_model import Ridge
            self.m = Ridge(alpha=p["alpha"])
        elif n == "enet":
            from sklearn.linear_model import ElasticNet
            self.m = ElasticNet(alpha=p["alpha"], l1_ratio=p["l1_ratio"], max_iter=5000)
        elif n == "rf":
            from sklearn.ensemble import RandomForestRegressor
            self.m = RandomForestRegressor(n_jobs=1, random_state=self.seed, **p)
        elif n == "et":
            from sklearn.ensemble import ExtraTreesRegressor
            self.m = ExtraTreesRegressor(n_jobs=1, random_state=self.seed, **p)
        elif n == "hgb":
            from sklearn.ensemble import HistGradientBoostingRegressor
            mask = [c in cats for c in Z.columns]
            self.m = HistGradientBoostingRegressor(random_state=self.seed, early_stopping=False,
                                                   categorical_features=mask if any(mask) else None, **p)
        elif n == "lgbm":
            from lightgbm import LGBMRegressor
            self.m = LGBMRegressor(random_state=self.seed, n_jobs=1, verbose=-1, subsample_freq=1,
                                   min_child_weight=1e-3, **p)
        elif n == "cat":
            from catboost import CatBoostRegressor
            self.m = CatBoostRegressor(random_seed=self.seed, thread_count=1, verbose=0,
                                       allow_writing_files=False, one_hot_max_size=255, border_count=64, boosting_type="Plain",
                                       cat_features=[Z.columns.get_loc(c) for c in cats] or None, **p)
        elif n == "xgb":
            from xgboost import XGBRegressor
            self.m = XGBRegressor(random_state=self.seed, n_jobs=1, tree_method="hist",
                                  huber_slope=0.15, **p)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.m.fit(Z, y)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return np.asarray(self.m.predict(self._prep(X.rename(columns=_safe), fit=False)), float)
