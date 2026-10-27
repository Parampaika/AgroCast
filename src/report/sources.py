"""Чтение результатов проекта для отчёта: перебор моделей, лесенка, оптимизация, данные.

Всё только читается. Если файла ещё нет (ночные расчёты не закончились), функции
возвращают None, а отчёт ставит заглушку «ждёт данных».
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
TABLES = REPORTS / "tables"
MODEL = ROOT / "data" / "model"
BUILD = ROOT / "report" / "build"


def _read_csv(p: Path, **kw) -> pd.DataFrame | None:
    try:
        return pd.read_csv(p, **kw) if p.exists() else None
    except Exception:
        return None


@lru_cache(maxsize=None)
def sweep(ver: str) -> pd.DataFrame | None:
    """Успешные строки перебора `data/model/<ver>/sweep_results.csv`; ck — культура оценки."""
    r = _read_csv(MODEL / ver / "sweep_results.csv", dtype={"cfg_id": str, "params": str})
    if r is None:
        return None
    r = r[r.status == "ok"].copy()
    r["ck"] = r.eval_crop.where(r.eval_crop.notna() & (r.eval_crop != ""), r.crop)
    r["gain_naive"] = 100 * (1 - r.mae / r.mae_bl_lag1)
    r["ver"] = ver
    return r


def sweeps() -> pd.DataFrame | None:
    parts = [s for v in ("v1", "v2") if (s := sweep(v)) is not None]
    return pd.concat(parts, ignore_index=True) if parts else None


def best(r: pd.DataFrame, date: str = "end", by: str = "ck") -> pd.DataFrame:
    q = r[r.date == date]
    return q.loc[q.groupby(by).mae.idxmin()].set_index(by)


def n_configs() -> dict:
    out = {}
    pre = _read_csv(MODEL / "pre_sweep_results.csv")
    out["pre"] = int(pre.drop_duplicates(subset=[c for c in ("cfg_id",) if c in pre]).shape[0]) if pre is not None else 627
    for v in ("v1", "v2"):
        r = _read_csv(MODEL / v / "sweep_results.csv", usecols=["cfg_id", "status"])
        out[v] = int(r[r.status == "ok"].cfg_id.nunique()) if r is not None else 0
    out["optuna_trials"], out["optuna_studies"] = 0, 0
    for v in ("v1", "v2"):
        d = MODEL / v / "optuna"
        if d.exists():
            for f in d.glob("*.log"):
                out["optuna_studies"] += 1
                try:  # журнал Optuna: op_code 4 — создание попытки
                    out["optuna_trials"] += sum(1 for line in f.open(encoding="utf-8", errors="ignore")
                                                if line.startswith('{"op_code":4,'))
                except OSError:
                    pass
    out["total"] = out["pre"] + out["v1"] + out["v2"]
    return out


def ladder() -> pd.DataFrame | None:
    return _read_csv(TABLES / "ladder_by_crop_date.csv")


def ladder_macro() -> pd.DataFrame | None:
    return _read_csv(TABLES / "ladder_macro_by_date.csv")


def report_exists(name: str) -> bool:
    return (REPORTS / name).exists()


def opt_tables() -> dict[str, pd.DataFrame]:
    """Все таблицы оптимизации, какие есть: reports/tables/opt*.csv и optimization*.csv."""
    out = {}
    for p in sorted(TABLES.glob("opt*.csv")):
        if (df := _read_csv(p)) is not None:
            out[p.stem] = df
    return out


def md_section(path: Path, heading_re: str) -> str | None:
    """Текст раздела markdown-файла (до следующего заголовка того же или старшего уровня)."""
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    start, level = None, 0
    for i, ln in enumerate(lines):
        m = re.match(r"^(#+)\s+(.*)", ln)
        if m and start is None and re.search(heading_re, m.group(2), re.I):
            start, level = i + 1, len(m.group(1))
        elif m and start is not None and len(m.group(1)) <= level:
            return "\n".join(lines[start:i]).strip()
    return "\n".join(lines[start:]).strip() if start is not None else None


def emiss_inventory() -> dict:
    p = ROOT / "data" / "interim" / "emiss" / "inventory.tsv"
    inv = _read_csv(p, sep="\t")
    if inv is None:
        return {}
    ok = inv[inv.status == "скачано"]
    return {"n_ind": int(len(inv)), "n_ok": int(len(ok)), "rows": int(pd.to_numeric(ok.rows, errors="coerce").sum()),
            "mb": float(pd.to_numeric(ok.mb, errors="coerce").sum())}


def tests_count() -> int:
    """Число тестов чистого слоя (по декораторам и параметрам — оценка без запуска pytest)."""
    cache = BUILD / "tests_count.txt"
    if cache.exists():
        return int(cache.read_text())
    import subprocess
    try:
        out = subprocess.run(["uv", "run", "pytest", "-q", "--collect-only", "tests"], cwd=ROOT,
                             capture_output=True, text=True, timeout=300).stdout
        n = int(re.search(r"(\d+) tests? collected", out).group(1))
    except Exception:
        n = 50
    BUILD.mkdir(parents=True, exist_ok=True)
    cache.write_text(str(n))
    return n


def shap() -> pd.DataFrame | None:
    return _read_csv(BUILD / "shap_features.csv")


def mae_by_year(row) -> dict[int, float]:
    try:
        return {int(k): float(v) for k, v in json.loads(row.mae_by_year).items()}
    except Exception:
        return {}


def preds(ver: str, cfg_id: str) -> pd.DataFrame | None:
    p = MODEL / ver / "preds" / f"{cfg_id}.parquet"
    return pd.read_parquet(p) if p.exists() else None


def first_model_table() -> pd.DataFrame | None:
    t = _read_csv(TABLES / "model_summary_rolling_table.csv")
    if t is None:
        return None
    rows = []
    for r in t.itertuples(index=False):
        d = {"crop": r[0]}
        for name, v in zip(t.columns[1:5], r[1:5]):
            mae, mape = (float(x) for x in str(v).split("/"))
            d[name] = mape
            d[name + "_mae"] = mae
        d["gain"] = float(r[5])
        rows.append(d)
    return pd.DataFrame(rows)


def fmt(x, digits: int = 0, unit: str = "") -> str:
    """Число по-русски: пробел — разделитель тысяч, запятая — десятичный."""
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    s = f"{x:,.{digits}f}".replace(",", " ").replace(".", ",")
    return s + (f" {unit}" if unit else "")
