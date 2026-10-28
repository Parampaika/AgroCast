"""Входные данные оптимизации: сценарии урожайности, цены, затраты, текущие планы, нормы севооборота.

Единый вход для оптимизатора — длинная таблица сценариев (parquet):

    okato | crop_code | scenario_year | yield_t_ha | [weight] | [source]

Сценарий s — урожайность сезона-цели при погоде года s; одинаковый scenario_year у разных культур
субъекта — один и тот же сезон (совместность сохраняется). Источники, по приоритету:
  final — data/model/final/ (итоговые модели, прогон по погоде годов-аналогов);
  web   — web/data/scenarios.json, если он выгружен моделью (meta.mock = false);
  hist  — «тренд сезона × (1 + отклонение от тренда в году s)» по фактической урожайности ЕМИСС.
"""
from __future__ import annotations

import json
import tomllib
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CLEAN = ROOT / "data" / "clean"
OUT = ROOT / "data" / "optimize"
FINAL = ROOT / "data" / "model" / "final"
CROPS = ["1010400", "1010500", "1030100", "1080202", "3080000", "3100000", "3060100"]
CROP_SHORT = {"1010400": "Озимая пшеница", "1010500": "Яровая пшеница", "1030100": "Ячмень", "1080202": "Кукуруза",
              "3080000": "Подсолнечник", "3100000": "Соя", "3060100": "Сахарная свёкла"}


@lru_cache
def config() -> dict:
    return tomllib.loads((Path(__file__).with_name("config.toml")).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- урожайность и площади
@lru_cache
def panel() -> pd.DataFrame:
    """Субъект × культура × год (все категории хозяйств): урожайность, площадь.

    y — урожайность Росстата на убранную площадь; за 2025 г. (итогов ещё нет) — расчётная
    «сбор / посевная», умноженная на медиану отношения y / y_calc этого ряда за 2018–2024.
    """
    yp = pd.read_parquet(CLEAN / "yield_panel.parquet",
                         columns=["okato", "region_level", "fo", "crop_code", "farm_category_code", "year",
                                  "yield_t_ha", "yield_calc_t_ha", "area_kha"])
    yp = yp[(yp.region_level == "subject") & (yp.farm_category_code == "1") & yp.crop_code.isin(CROPS)].copy()
    yp["year"] = yp.year.astype(int)
    r = yp[(yp.year >= 2018) & (yp.year <= 2024)].assign(k=lambda d: d.yield_t_ha / d.yield_calc_t_ha)
    k = r.groupby(["okato", "crop_code"]).k.median().clip(0.8, 1.6).rename("k")
    yp = yp.merge(k, on=["okato", "crop_code"], how="left")
    est = (yp.year == 2025) & yp.yield_t_ha.isna()
    yp["y"] = yp.yield_t_ha
    yp.loc[est, "y"] = yp.loc[est, "yield_calc_t_ha"] * yp.loc[est, "k"].fillna(1.05)
    yp["y_is_est"] = est & yp.y.notna()
    return yp[["okato", "fo", "crop_code", "year", "y", "y_is_est", "area_kha"]]


def _wide(col: str) -> pd.DataFrame:
    p = panel()
    return p.pivot_table(index=["okato", "crop_code"], columns="year", values=col, aggfunc="first")


@lru_cache
def yields_wide() -> pd.DataFrame:
    return _wide("y")


@lru_cache
def area_wide() -> pd.DataFrame:
    return _wide("area_kha")


def linear_trend(Y: pd.DataFrame, T: int, window: int, min_pts: int) -> pd.Series:
    """Линейный тренд по годам T−window…T−1 (только прошлое), прогноз на T; не ниже 30 % среднего окна."""
    yrs = [y for y in range(T - window, T) if y in Y.columns]
    M = Y[yrs].to_numpy(float)
    x = np.array(yrs, float) - T
    ok = np.isfinite(M)
    n = ok.sum(1)
    xm = np.where(ok, x, 0).sum(1) / np.maximum(n, 1)
    ym = np.where(ok, M, 0).sum(1) / np.maximum(n, 1)
    dx = np.where(ok, x - xm[:, None], 0)
    dy = np.where(ok, M - ym[:, None], 0)
    b = (dx * dy).sum(1) / np.maximum((dx * dx).sum(1), 1e-9)
    tr = ym + b * (0 - xm)
    tr = np.where(n >= min_pts, np.maximum(tr, 0.3 * ym), np.nan)
    return pd.Series(tr, index=Y.index)


@lru_cache
def deviations() -> pd.DataFrame:
    """Относительное отклонение урожайности от тренда (по прошлым годам) по годам: y_s / tr_s − 1."""
    cfg = config()["scenarios"]
    Y = yields_wide()
    out = {}
    for s in range(2001, int(Y.columns.max()) + 1):
        if s not in Y.columns:
            continue
        tr = linear_trend(Y, s, cfg["trend_window"], cfg["trend_min_points"])
        out[s] = (Y[s] / tr - 1).clip(*cfg["dev_clip"])
    return pd.DataFrame(out)


def hist_scenarios(T: int, years: list[int]) -> pd.DataFrame:
    """Сценарии «тренд T × (1 + отклонение года s)». Пропуск отклонения → медиана ФО по культуре в году s → 0."""
    cfg = config()["scenarios"]
    Y = yields_wide()
    tr = linear_trend(Y, T, cfg["trend_window"], cfg["trend_min_points"]).dropna()
    dev = deviations().reindex(columns=years)
    fo = panel().drop_duplicates("okato").set_index("okato").fo
    idx = dev.index.to_frame(index=False)
    idx["fo"] = idx.okato.map(fo)
    med = dev.set_axis(pd.MultiIndex.from_frame(idx[["fo", "crop_code"]]), axis=0).groupby(level=[0, 1]).median()
    rows = []
    for (ok, cc), t in tr.items():
        d = dev.loc[(ok, cc)] if (ok, cc) in dev.index else pd.Series(np.nan, index=years)
        imputed = d.isna()
        key = (fo.get(ok), cc)
        if imputed.any() and key in med.index:
            d = d.fillna(med.loc[key])
        d = d.fillna(0.0)
        for s in years:
            rows.append((ok, cc, s, t * (1 + d[s]), bool(imputed[s])))
    df = pd.DataFrame(rows, columns=["okato", "crop_code", "scenario_year", "yield_t_ha", "imputed"])
    df["weight"] = 1.0
    df["source"] = "hist"
    return df


def load_scenarios(source: str = "auto") -> pd.DataFrame:
    """Таблица сценариев на сезон config.season из выбранного источника (см. докстринг модуля)."""
    cfg = config()
    T = cfg["season"]
    y0, y1 = cfg["scenarios"]["years"]
    if source in ("auto", "final"):
        files = sorted(FINAL.glob("*scen*.parquet")) if FINAL.exists() else []
        if files:
            df = pd.read_parquet(files[0])
            df = _normalize(df, "final:" + files[0].name)
            return df
        if source == "final":
            raise FileNotFoundError(f"нет parquet сценариев в {FINAL}")
    if source in ("auto", "web"):
        f = ROOT / "web" / "data" / "scenarios.json"
        js = json.loads(f.read_text(encoding="utf-8"))
        if not js["meta"].get("mock", True):
            yrs = js["scenario_years"]
            rows = [(ok, cc, s, v) for ok, byc in js["regions"].items() for cc, vals in byc.items()
                    for s, v in zip(yrs, vals) if v is not None]
            df = pd.DataFrame(rows, columns=["okato", "crop_code", "scenario_year", "yield_t_ha"])
            return _normalize(df, "web:scenarios.json")
        if source == "web":
            raise ValueError("web/data/scenarios.json — заглушка (mock = true)")
    return hist_scenarios(T, list(range(y0, y1 + 1)))


def _normalize(df: pd.DataFrame, src: str) -> pd.DataFrame:
    """Приводит чужую таблицу сценариев к схеме okato, crop_code, scenario_year, yield_t_ha, weight, source."""
    ren = {"year_scenario": "scenario_year", "scen_year": "scenario_year", "analog_year": "scenario_year",
           "yield": "yield_t_ha", "yhat": "yield_t_ha", "y": "yield_t_ha"}
    df = df.rename(columns={k: v for k, v in ren.items() if k in df.columns and v not in df.columns})
    if "forecast_date" in df.columns:
        # data/model/final/scenarios.parquet: сценарии итоговой модели на разных датах; для плана посевов —
        # дата до начала сезона (вся погода сезона из года-аналога, о 2026 г. ничего не известно)
        fd = config()["scenarios"].get("forecast_date", "pre_season")
        df = df[df.forecast_date == fd].copy()
        src += f" ({fd})"
    if "crop_code" not in df.columns and "crop" in df.columns:
        slug = {"winter_wheat": "1010400", "spring_wheat": "1010500", "barley": "1030100", "maize": "1080202",
                "sunflower": "3080000", "soy": "3100000", "sugar_beet": "3060100"}
        df["crop_code"] = df.crop.map(slug).fillna(df.crop)
    df["crop_code"] = df.crop_code.astype(str)
    df["okato"] = df.okato.astype(str)
    df["scenario_year"] = df.scenario_year.astype(int)
    if "weight" not in df.columns:
        df["weight"] = 1.0
    df["source"] = src
    df["imputed"] = df.get("imputed", False)
    return df[df.crop_code.isin(CROPS) & df.yield_t_ha.notna()][
        ["okato", "crop_code", "scenario_year", "yield_t_ha", "weight", "source", "imputed"]]


# ---------------------------------------------------------------- цены и затраты
@lru_cache
def prices_wide() -> pd.DataFrame:
    """Цена производителей, руб./т: (okato, crop_code) × год, подстановка «субъект → ФО → РФ» уже в data/clean."""
    p = pd.read_parquet(CLEAN / "prices.parquet", columns=["okato", "product_id", "year", "price"])
    prod = config()["prices"]["product"]
    rows = [p[p.product_id == pid].assign(crop_code=cc) for cc, pid in prod.items()]
    p = pd.concat(rows)
    p["year"] = p.year.astype(int)
    return p.pivot_table(index=["okato", "crop_code"], columns="year", values="price", aggfunc="first")


def price(ok: str, cc: str, year: int) -> float:
    P = prices_wide()
    for key in ((ok, cc), ("643", cc)):
        if key in P.index and year in P.columns and np.isfinite(P.loc[key, year]):
            return float(P.loc[key, year])
    return float("nan")


@lru_cache
def cost_index() -> pd.Series:
    """Затраты на 1 га к 2026 г.: себестоимость растениеводства СХО (ЕМИСС 42381) / посевная СХО (31328)."""
    e = pd.read_parquet(CLEAN / "economics_aux.parquet", columns=["indicator_id", "okato", "year", "value"])
    c = e[(e.indicator_id.astype(str) == "42381") & (e.okato == "643")].groupby("year").value.first()
    a = sown_rf_sxo()
    rub_ha = (c * 1e3 / (a.reindex(c.index) * 1e3)).dropna()
    rub_ha.loc[2026] = rub_ha.loc[rub_ha.index.max()] * config()["costs"]["growth_2026"]
    return (rub_ha / rub_ha.loc[2026]).rename("cost_index")


@lru_cache
def _area31328() -> pd.DataFrame:
    a = pd.read_parquet(CLEAN / "_cache" / "emiss" / "31328.parquet",
                        columns=["okato", "farm_category_code", "crop_code", "year", "value"])
    a["year"] = a.year.astype(int)
    a["crop_code"] = a.crop_code.astype(str)
    a.loc[a.crop_code == "8200000", "crop_code"] = "6"   # «вся посевная» сменила код в 2022 г.
    a.loc[a.okato == "643004.АГ", "okato"] = "643"
    return a


def sown_rf_sxo() -> pd.Series:
    a = _area31328()
    a = a[(a.okato == "643") & (a.farm_category_code.astype(str) == "2") & (a.crop_code == "6")]
    return a.groupby("year").value.first()


def total_area(code: str = "6") -> pd.DataFrame:
    """Площадь группы во всех категориях хозяйств: субъект × год, тыс. га (6 — вся посевная, 1000001 — зерновые)."""
    a = _area31328()
    a = a[(a.farm_category_code.astype(str) == "1") & (a.crop_code == code)]
    t = a.pivot_table(index="okato", columns="year", values="value", aggfunc="first")
    if "71001000000" not in t.index and "71100000000" in t.index:
        t.loc["71001000000"] = t.loc["71100000000"]
    return t


def last_value(t: pd.DataFrame, ok: str, year: int) -> float:
    if ok not in t.index:
        return float("nan")
    s = t.loc[ok, [c for c in t.columns if c <= year]].dropna()
    return float(s.iloc[-1]) if len(s) else float("nan")


@lru_cache
def rf_trend_level() -> pd.Series:
    """Средняя по площади трендовая урожайность культуры по субъектам на сезон (для региональной поправки затрат)."""
    cfg = config()["scenarios"]
    T = config()["season"]
    tr = linear_trend(yields_wide(), T, cfg["trend_window"], cfg["trend_min_points"])
    A = area_wide()
    w = A[[c for c in A.columns if T - 5 <= c < T]].mean(axis=1)
    d = pd.DataFrame({"tr": tr, "w": w}).dropna()
    return d.groupby(level="crop_code").apply(lambda g: np.average(g.tr, weights=g.w))


def cost(cc: str, level_ratio: float, year: int, cost_mult: float = 1.0) -> float:
    """Затраты руб./га: база × (fixed + (1 − fixed)·уровень урожайности субъекта к РФ) × индекс года."""
    c = config()["costs"]
    m = c["fixed_share"] + (1 - c["fixed_share"]) * (level_ratio if np.isfinite(level_ratio) else 1.0)
    m = float(np.clip(m, *c["mult_clip"]))
    idx = cost_index().get(year, np.nan)
    if not np.isfinite(idx):
        idx = float(cost_index().iloc[0])
    return c["base_rub_ha"][cc] * m * idx * cost_mult
