"""Пути, параметры сборки, кэш промежуточных файлов и общие справочные функции."""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"
CACHE = CLEAN / "_cache"
SRC_DATA = ROOT / "src" / "data"  # исследовательские скрипты другой сессии: только импорт, не правим

CAT_ALL, CAT_SHO, CAT_KFH, CAT_HH = "1", "2", "8", "17"
RF = "643"


@dataclass
class Config:
    train_end_year: int = 2021      # нормы климата и все «обучающие» статистики — только по годам ≤ этого
    clim_start_year: int = 2001     # первый полный сезон погоды (сентябрь 2000 — октябрь 2001)
    category: str = CAT_ALL         # категория хозяйств для model_table
    price_base_year: int = 2021     # базовый год реальных цен
    force: bool = False             # пересобирать кэш
    crops: list[str] | None = None  # фильтр культур для model_table (None — все)
    stats: dict = field(default_factory=dict)


def ensure_dirs() -> None:
    CLEAN.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)


def log(*a) -> None:
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def save(df: pd.DataFrame, name: str, cfg: Config | None = None) -> Path:
    """Пишет data/clean/<name>.parquet и запоминает размер для сводки."""
    ensure_dirs()
    p = CLEAN / f"{name}.parquet"
    df.to_parquet(p, index=False)
    log(f"{name}: {len(df):,} строк × {df.shape[1]} колонок → {p.relative_to(ROOT)}")
    if cfg is not None:
        cfg.stats[name] = {"rows": int(len(df)), "cols": int(df.shape[1])}
    return p


def load(name: str) -> pd.DataFrame:
    return pd.read_parquet(CLEAN / f"{name}.parquet")


def write_stats(name: str, stats: dict) -> None:
    """Сводка шага для отчёта: data/clean/_stats/<name>.json."""
    d = CLEAN / "_stats"
    d.mkdir(parents=True, exist_ok=True)

    def keys(o):
        if isinstance(o, dict):
            return {(k if isinstance(k, str) else str(_json_default(k)) if not isinstance(k, tuple)
                     else " ".join(map(str, k))): keys(v) for k, v in o.items()}
        if isinstance(o, list):
            return [keys(v) for v in o]
        return o

    (d / f"{name}.json").write_text(json.dumps(keys(stats), ensure_ascii=False, indent=1, default=_json_default),
                                    encoding="utf-8")


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (pd.Timestamp,)):
        return str(o.date())
    return str(o)


# ---------- ЕМИСС ----------

def _parse_emiss():
    """Парсер SDMX из src/data/parse_emiss.py (та же логика: 999999999 → NaN + флаг, коды w2:, region_level)."""
    if str(SRC_DATA) not in sys.path:
        sys.path.insert(0, str(SRC_DATA))
    from parse_emiss import parse_indicator  # noqa: PLC0415
    return parse_indicator


def emiss(ind: str, force: bool = False) -> pd.DataFrame:
    """Длинная таблица показателя ЕМИСС, разобранная из data/raw/emiss/<id>/ (кэш в data/clean/_cache/emiss)."""
    out = CACHE / "emiss" / f"{ind}.parquet"
    raw_dir = RAW / "emiss" / ind
    raw_files = list(raw_dir.glob("data*.xml"))
    if out.exists() and not force and raw_files and out.stat().st_mtime > max(f.stat().st_mtime for f in raw_files):
        return pd.read_parquet(out)
    df = _parse_emiss()(ind)
    if df is None:
        raise FileNotFoundError(f"ЕМИСС {ind}: нет разобранных данных в {raw_dir}")
    # измерение территории у части показателей называется mОКАТО
    if "okato" not in df.columns:
        for c in list(df.columns):
            if c.endswith("ОКАТО_code"):
                df = df.rename(columns={c: "okato", c[:-5]: "region"})
        if "okato" in df.columns:
            from parse_emiss import region_level  # noqa: PLC0415
            df["region_level"] = [region_level(c, n) for c, n in zip(df["okato"], df["region"])]
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return df


# ---------- регионы ----------

def regions_raw() -> pd.DataFrame:
    return pd.read_csv(RAW / "geo" / "regions.csv", dtype={"okato": str})


def points() -> pd.DataFrame:
    """Точки пашни; вес точки в среднем по региону — доля пашни вокруг неё (не меньше 0.05), как в src/data."""
    p = pd.read_csv(RAW / "geo" / "points.csv", dtype={"okato": str})
    p["w"] = p.crop_frac_3km.clip(lower=0.05)
    return p


def fo_map() -> dict[str, str]:
    """ОКАТО (включая коды «с АО» и «без АО») → ФО."""
    reg = regions_raw()
    m = dict(zip(reg.okato, reg.fo))
    for c, f in list(m.items()):
        m.setdefault(c[:2] + "000000000", f)
        m.setdefault(c[:2] + "001000000", f)
    return m


def weighted_mean(df: pd.DataFrame, by: list[str], cols: list[str], w: str = "w") -> pd.DataFrame:
    """Взвешенное среднее по группам с учётом пропусков (вес пропущенного значения не учитывается)."""
    num = df[cols].mul(df[w], axis=0)
    den = df[cols].notna().mul(df[w], axis=0)
    num[by] = df[by]
    den[by] = df[by]
    res = num.groupby(by).sum(min_count=1) / den.groupby(by).sum().replace(0, np.nan)
    return res.reset_index()
