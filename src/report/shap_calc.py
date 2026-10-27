"""SHAP-разложение для отчёта: LightGBM на полном наборе признаков F6, конец сезона.

Одна модель на культуру, обучение на сезонах ≤ 2024 (цель — разность y − mean5, как у
лучших конфигураций перебора), TreeSHAP встроенный в LightGBM (`pred_contrib=True`),
без отдельного пакета shap. Модуль только читает `src/model` и `data/clean`.
Результат — `report/build/shap_features.csv` (культура × признак: mean|SHAP|, знак связи).

    uv run python -I -X utf8 src/report/shap_calc.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "report" / "build" / "shap_features.csv"

BLOCK = {"m": "погода по месяцам", "w": "окно культуры и зима", "c": "климат региона",
         "s": "почвы", "n": "NDVI", "g": "спутник MODIS", "e": "рельеф и тип почвы",
         "r": "регион и прошлые отклонения"}


def block_of(col: str) -> str:
    if col.startswith("cat:") or col in ("r1", "r2"):
        return BLOCK["r"]
    return BLOCK.get(col.split(":", 1)[0], "прочее")


def run(crop: str, T: int = 2025) -> pd.DataFrame:
    import lightgbm as lgb
    from model import cv
    from model import data as D

    cfg = cv.Config(crop, date="end", trend="mean5", target="diff", feats="F6", model="lgbm")
    f, X = cv._crop_matrix(crop, cfg, T)
    z = D.make_target(f.y.to_numpy(), f["tr_mean5"].to_numpy(), "diff")
    tr = (f.year < T).to_numpy() & np.isfinite(z) & ~f.flag_mismatch.to_numpy()
    Xn = X.astype(float)
    Xn.columns = [f"f{i}" for i in range(X.shape[1])]  # LightGBM не принимает «:» в именах
    m = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.03, num_leaves=15, min_child_samples=20,
                          subsample=0.8, subsample_freq=1, colsample_bytree=0.5, reg_lambda=1.0,
                          verbose=-1, random_state=0)
    m.fit(Xn[tr], z[tr])
    sv = m.predict(Xn[tr], pred_contrib=True)[:, :-1]
    xs = Xn[tr].to_numpy()
    rows = []
    for j, col in enumerate(X.columns):
        s, x = sv[:, j], xs[:, j]
        ok = np.isfinite(x) & (np.nanstd(x) > 0)
        sign = float(np.corrcoef(x[ok], s[ok])[0, 1]) if ok.sum() > 10 and np.std(s[ok]) > 0 else np.nan
        rows.append({"crop": crop, "crop_name": D.CROP_NAME[crop], "feature": col, "block": block_of(col),
                     "mean_abs_shap": float(np.abs(s).mean()), "sign_corr": sign,
                     "y_mean": float(np.nanmean(f.y[tr]))})
    print(crop, "строк", int(tr.sum()), "признаков", X.shape[1], flush=True)
    return pd.DataFrame(rows)


def main() -> None:
    from model import data as D
    out = pd.concat([run(c) for c in D.CROP_NAME], ignore_index=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False, encoding="utf-8")
    print("записано", OUT)


if __name__ == "__main__":
    main()
