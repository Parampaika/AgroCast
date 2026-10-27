"""Данные для перебора моделей: выборка, тренды, цели и признаки на дату прогноза.

Всё строится только из `data/clean/`. Главные правила:
- тренд года t считается только по годам < t (ряд `y_hist`);
- погода, окна культуры и NDVI обрезаются по дате прогноза: месяц входит,
  только если он закончился до даты;
- нормы погоды (для аномалий) считаются внутри фолда по сезонам 2001…T−1
  (`norm_mode="fold"`), а не по 2001–2021, как в чистом слое.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CLEAN = ROOT / "data" / "clean"

# код ЕМИСС → (ключ, название)
CROPS = {
    "1010400": ("winter_wheat", "Пшеница озимая"),
    "1010500": ("spring_wheat", "Пшеница яровая"),
    "1030100": ("barley", "Ячмень яровой"),
    "3080000": ("sunflower", "Подсолнечник"),
    "1080202": ("maize", "Кукуруза на зерно"),
    "3100000": ("soy", "Соя"),
    "3060100": ("sugar_beet", "Сахарная свёкла"),
}
CROP_KEY = {c: k for c, (k, _) in CROPS.items()}
KEY_CROP = {k: c for c, k in CROP_KEY.items()}
CROP_NAME = {k: n for _, (k, n) in CROPS.items()}

# месяцы сезона Y: сентябрь Y−1 … октябрь Y
TAGS = ["p09", "p10", "p11", "p12"] + [f"{m:02d}" for m in range(1, 11)]
TAG_IDX = {t: i for i, t in enumerate(TAGS)}
# дата прогноза → индекс последнего полностью известного месяца
DATES = {"05-01": TAG_IDX["04"], "06-01": TAG_IDX["05"], "07-01": TAG_IDX["06"],
         "08-01": TAG_IDX["07"], "end": TAG_IDX["10"]}
# месяцы, которые вообще имеют смысл для культуры (индексы TAGS, включительно)
CROP_MONTHS = {
    "winter_wheat": (TAG_IDX["p09"], TAG_IDX["08"]),
    "spring_wheat": (TAG_IDX["03"], TAG_IDX["08"]),
    "barley": (TAG_IDX["03"], TAG_IDX["08"]),
    "sunflower": (TAG_IDX["03"], TAG_IDX["09"]),
    "maize": (TAG_IDX["03"], TAG_IDX["09"]),
    "soy": (TAG_IDX["03"], TAG_IDX["09"]),
    "sugar_beet": (TAG_IDX["03"], TAG_IDX["09"]),
}
COLD_TAGS = {"p11", "p12", "01", "02", "03"}
VARS_GROW = ["tmean", "tmax", "tmin", "prec", "et0", "cwb", "rad", "vpd", "sm7_28",
             "sm28_100", "hot30", "gdd5", "frost0"]
VARS_COLD = ["tmean", "tmin", "prec", "sm28_100", "snow_depth", "tsoil_min"]
WIN_SUM = ["prec", "et0", "cwb", "gdd5", "gdd10", "hot30", "hot35", "frost0", "dry_days"]
WIN_MEAN = ["tmean", "tmax", "sm28_100", "sm7_28", "vpd"]
SOIL = ["soil_clay_0_30", "soil_sand_0_30", "soil_soc_0_30", "soil_phh2o_0_30",
        "soil_nitrogen_0_30", "soil_cec_0_30", "soil_bdod_0_30", "soil_ocs_0_30"]
NDVI_MONTHS = ["04", "05", "06", "07", "08", "09"]
# спутник MODIS (LAI, FPAR, LST день/ночь, GPP): месячные средние по 8-дневным композитам, апрель–октябрь
SAT_VARS = ["lai", "fpar", "lst_day", "lst_night", "lst_diff", "gpp"]
SAT_MONTHS = ["04", "05", "06", "07", "08", "09"]
SAT_PEAK = ["lai", "fpar", "lst_day"]      # максимум за известные месяцы
SAT_CUM = ["gpp"]                           # сумма месячных значений за известные месяцы
SAT_PATH = CLEAN / "modis_extra_region_year.parquet"

TREND_TYPES = ["lin_all", "lin10", "lin15", "ts10", "ts15", "mean5", "lag1"]
BASELINES = ["lin10", "mean5", "lag1"]  # официальные бейзлайны из EDA (tr_* чистого слоя)
TARGETS = ["ratio", "diff", "log"]
FIRST_YEAR = 2000
LAST_YEAR = 2025


# ---------------------------------------------------------------- выборка и цель
@lru_cache(maxsize=1)
def load_panel() -> pd.DataFrame:
    cols = ["okato", "fo", "crop_code", "year", "yield_t_ha", "yield_calc_t_ha", "harvest_share",
            "area_kha", "flag_outlier_hi", "flag_outlier_lo", "flag_calc_mismatch",
            "series_max_run", "y_hist", "tr_lin10", "tr_mean5", "tr_lag1", "tr_lin_all"]
    m = pd.read_parquet(CLEAN / "model_table.parquet", columns=cols)
    m = m[m.crop_code.isin(list(CROPS))].copy()
    m["crop"] = m.crop_code.map(CROP_KEY)
    m["year"] = m.year.astype(int)
    # 2025: итогов Росстата нет → сбор / (посевная × медиана h за 2020–2024), как в eda_emiss.md
    h = (m[(m.year >= 2020) & (m.year <= 2024)].groupby(["okato", "crop"]).harvest_share
         .median().rename("h_med"))
    m = m.join(h, on=["okato", "crop"])
    proxy = m.yield_calc_t_ha / m.h_med.clip(0.5, 1.05)
    m["is_proxy"] = (m.year == 2025) & m.yield_t_ha.isna() & proxy.notna()
    m["y"] = np.where(m.is_proxy, proxy, m.yield_t_ha)
    return m.drop(columns=["h_med"])


def select_regions(panel: pd.DataFrame, crop: str, min_area: float = 5.0,
                   min_run: int = 15) -> list[str]:
    """Субъекты культуры: средняя посевная ≥ min_area тыс. га и ряд ≥ min_run лет."""
    p = panel[(panel.crop == crop) & (panel.year <= 2024)]
    g = p.groupby("okato").agg(area=("area_kha", "mean"), run=("series_max_run", "max"))
    return sorted(g[(g.area >= min_area) & (g.run >= min_run)].index)


# ---------------------------------------------------------------- тренды
def _theil_sen(x: np.ndarray, v: np.ndarray, t: float) -> float:
    i, j = np.triu_indices(len(x), 1)
    b = np.median((v[j] - v[i]) / (x[j] - x[i]))
    a = np.median(v - b * x)
    return a + b * t


def _ols(x: np.ndarray, v: np.ndarray, t: float) -> float:
    b, a = np.polyfit(x, v, 1)
    return a + b * t


def trend_matrix(values: np.ndarray, years: np.ndarray) -> dict[str, np.ndarray]:
    """Тренды одного ряда на каждый год по годам < t. values — y_hist по years."""
    out = {k: np.full(len(years), np.nan) for k in TREND_TYPES}
    ok = ~np.isnan(values)
    for n, t in enumerate(years):
        past = ok & (years < t)
        if not past.any():
            continue
        xp, vp = years[past].astype(float), values[past]
        last = years[past].max()
        if last == t - 1:
            out["lag1"][n] = vp[-1]
        w5 = xp >= t - 5
        if w5.sum() >= 3:
            out["mean5"][n] = vp[w5].mean()
        m10 = vp[xp >= t - 10].mean() if (xp >= t - 10).any() else np.nan
        lo, hi = 0.5 * m10, 1.5 * m10  # защита от экстраполяции линейного тренда в ноль
        if len(xp) >= 5:
            out["lin_all"][n] = np.clip(_ols(xp, vp, t), lo, hi)
        for win, need, keys in ((10, 5, ("lin10", "ts10")), (15, 7, ("lin15", "ts15"))):
            w = xp >= t - win
            if w.sum() >= need:
                out[keys[0]][n] = np.clip(_ols(xp[w], vp[w], t), lo, hi)
                out[keys[1]][n] = np.clip(_theil_sen(xp[w], vp[w], t), lo, hi)
    return out


@lru_cache(maxsize=None)
def crop_frame(crop: str) -> pd.DataFrame:
    """Строки «субъект × год» культуры с целью, трендами и прошлыми отклонениями."""
    panel = load_panel()
    regs = select_regions(panel, crop)
    p = panel[(panel.crop == crop) & panel.okato.isin(regs)]
    years = np.arange(FIRST_YEAR, LAST_YEAR + 1)
    rows = []
    for okato, g in p.groupby("okato"):
        g = g.set_index("year").reindex(years)
        tr = trend_matrix(g.y_hist.to_numpy(float), years)
        d = pd.DataFrame({"okato": okato, "year": years, "y": g.y.to_numpy(float),
                          "y_hist": g.y_hist.to_numpy(float),
                          "area_kha": g.area_kha.to_numpy(float),
                          "is_proxy": g.is_proxy.fillna(False).to_numpy(bool),
                          "flag_lo": g.flag_outlier_lo.fillna(False).to_numpy(bool),
                          "flag_mismatch": g.flag_calc_mismatch.fillna(False).to_numpy(bool),
                          "bl_lin10": g.tr_lin10.to_numpy(float),
                          "bl_mean5": g.tr_mean5.to_numpy(float),
                          "bl_lag1": g.tr_lag1.to_numpy(float),
                          "fo": g.fo.dropna().iloc[0] if g.fo.notna().any() else ""})
        for k, v in tr.items():
            d[f"tr_{k}"] = v
            # прошлые отклонения от «своего» тренда: y_{t−1}/T_{t−1} − 1 (известны к году t)
            r = d.y_hist / v - 1
            d[f"r1_{k}"] = r.shift(1).to_numpy()
            d[f"r2_{k}"] = r.shift(2).to_numpy()
        rows.append(d)
    f = pd.concat(rows, ignore_index=True)
    f["crop"] = crop
    return f


def make_target(y: np.ndarray, tr: np.ndarray, kind: str) -> np.ndarray:
    if kind == "ratio":
        return y / tr - 1
    if kind == "diff":
        return y - tr
    if kind == "log":
        return np.log(y / tr)
    raise ValueError(kind)


def invert_target(z: np.ndarray, tr: np.ndarray, kind: str) -> np.ndarray:
    if kind == "ratio":
        return tr * (1 + z)
    if kind == "diff":
        return tr + z
    if kind == "log":
        return tr * np.exp(z)
    raise ValueError(kind)


# ---------------------------------------------------------------- погода и NDVI
@lru_cache(maxsize=1)
def load_weather() -> pd.DataFrame:
    w = pd.read_parquet(CLEAN / "weather_region_season.parquet")
    w = w[[c for c in w.columns if not c.startswith(("a_", "clim_"))]].copy()
    w["year"] = w.year.astype(int)
    return w.set_index(["okato", "year"]).sort_index()


@lru_cache(maxsize=1)
def load_ndvi() -> pd.DataFrame:
    n = pd.read_parquet(CLEAN / "ndvi_region_year.parquet")
    n["year"] = n.year.astype(int)
    return n.set_index(["okato", "year"]).sort_index()


@lru_cache(maxsize=1)
def load_sat() -> pd.DataFrame | None:
    """Месячные значения спутниковых индексов «регион × год»; None, если слой ещё не собран."""
    if not SAT_PATH.exists():
        return None
    keep = ["okato", "year"] + [f"{v}_{m}" for v in SAT_VARS for m in SAT_MONTHS]
    import pyarrow.parquet as pq
    have = set(pq.read_schema(SAT_PATH).names)
    n = pd.read_parquet(SAT_PATH, columns=[c for c in keep if c in have])
    n["year"] = n.year.astype(int)
    return n.set_index(["okato", "year"]).sort_index()


@lru_cache(maxsize=1)
def load_elev() -> pd.DataFrame | None:
    """Рельеф региона (колонки elev_*), где бы препроцессинг их ни положил."""
    import pyarrow.parquet as pq
    for name in ("regions", "soil_region", "elevation_region", "model_table"):
        f = CLEAN / f"{name}.parquet"
        if not f.exists():
            continue
        cols = [c for c in pq.read_schema(f).names if c.startswith("elev_")]
        if cols:
            e = pd.read_parquet(f, columns=["okato"] + cols).drop_duplicates("okato")
            return e.set_index("okato")
    return None


@lru_cache(maxsize=1)
def load_soil() -> pd.DataFrame:
    return pd.read_parquet(CLEAN / "soil_region.parquet").set_index("okato")


@lru_cache(maxsize=1)
def load_calendar() -> pd.DataFrame:
    return pd.read_parquet(CLEAN / "crop_calendar.parquet").set_index(["okato", "crop_code"])


def _window_idx(plant_month: int, maturity_month: int, winter: bool) -> tuple[int, int]:
    """Окно культуры в индексах TAGS (у озимых — не раньше сентября Y−1)."""
    if winter:
        a = TAG_IDX["p09"] if plant_month < 9 else TAG_IDX[f"p{plant_month:02d}"]
    else:
        a = TAG_IDX[f"{plant_month:02d}"]
    b = TAG_IDX[f"{min(maturity_month, 10):02d}"]
    return a, max(a, b)


@dataclass
class FeatureGrid:
    """Сырые признаки культуры на дату на полной сетке «субъект × год» (2001…2025).

    blocks: имя блока → список колонок. Колонки блоков m, w, n переводятся в аномалии
    внутри фолда; c — климат региона (норма фолда); s — почвы (константы).
    """
    crop: str
    date: str
    grid: pd.DataFrame
    blocks: dict[str, list[str]] = field(default_factory=dict)

    ANOM_BLOCKS = ("m", "w", "n", "g")


@lru_cache(maxsize=None)
def feature_grid(crop: str, date: str) -> FeatureGrid:
    k = DATES[date]
    a0, a1 = CROP_MONTHS[crop]
    known = [t for i, t in enumerate(TAGS) if a0 <= i <= min(a1, k)]
    w = load_weather()
    regs = sorted(crop_frame(crop).okato.unique())
    idx = pd.MultiIndex.from_product([regs, range(2001, LAST_YEAR + 1)], names=["okato", "year"])
    wr = w.reindex(idx)
    out = {}
    blocks: dict[str, list[str]] = {"m": [], "w": [], "c": [], "s": [], "n": [], "g": [], "e": []}
    # F1: месячные значения (в фолде → аномалии)
    for t in known:
        for v in (VARS_COLD if t in COLD_TAGS else VARS_GROW):
            col = f"{v}_{t}"
            if col in wr:
                out[f"m:{col}"] = wr[col].to_numpy(np.float32)
                blocks["m"].append(f"m:{col}")
    # F2: окно культуры до даты + зима + запас влаги
    cal = load_calendar()
    winter = crop == "winter_wheat"
    code = KEY_CROP[crop]
    agg = {f"w:win_{v}": np.full(len(idx), np.nan, np.float32) for v in WIN_SUM + WIN_MEAN}
    agg["w:win_htc"] = np.full(len(idx), np.nan, np.float32)
    agg["w:win_dry_spell"] = np.full(len(idx), np.nan, np.float32)
    okatos = idx.get_level_values(0)
    for reg in regs:
        rows = np.flatnonzero(okatos == reg)
        try:
            c = cal.loc[(reg, code)]
            a, b = _window_idx(int(c.plant_month), int(c.maturity_month), winter)
        except KeyError:
            a, b = CROP_MONTHS[crop]
        tags = [TAGS[i] for i in range(a, min(b, k) + 1)]
        if not tags:
            continue
        sub = wr.iloc[rows]
        for v in WIN_SUM:
            agg[f"w:win_{v}"][rows] = sub[[f"{v}_{t}" for t in tags]].sum(axis=1, min_count=len(tags))
        for v in WIN_MEAN:
            agg[f"w:win_{v}"][rows] = sub[[f"{v}_{t}" for t in tags]].mean(axis=1)
        pa = sub[[f"prec_act_{t}" for t in tags]].sum(axis=1, min_count=len(tags))
        ta = sub[[f"t_act_{t}" for t in tags]].sum(axis=1, min_count=len(tags))
        agg["w:win_htc"][rows] = np.where(ta >= 100, 10 * pa / ta.where(ta > 0), np.nan)
        agg["w:win_dry_spell"][rows] = sub[[f"dry_spell_{t}" for t in tags]].max(axis=1)
    out.update(agg)
    blocks["w"] += list(agg)
    if k >= TAG_IDX["03"]:
        for col in ["prec_p09_03"] + (["tsoil_min_win", "cold20_win", "snow_win", "thaw_win"]
                                      if winter else []):
            out[f"w:{col}"] = wr[col].to_numpy(np.float32)
            blocks["w"].append(f"w:{col}")
    # F3: климат (норма фолда) и почвы
    for col in ["tmean_4_8", "prec_4_8", "htc_5_8"]:
        out[f"c:{col}"] = wr[col].to_numpy(np.float32)
        blocks["c"].append(f"c:{col}")
    soil = load_soil().reindex(okatos)
    for col in SOIL:
        out[f"s:{col}"] = soil[col.removeprefix("soil_")].to_numpy(np.float32)
        blocks["s"].append(f"s:{col}")
    # F4: NDVI по закончившимся месяцам
    nd = load_ndvi().reindex(idx)
    for t in NDVI_MONTHS:
        if TAG_IDX[t] <= k and TAG_IDX[t] <= a1:
            out[f"n:ndvi_{t}"] = nd[f"ndvi_{t}"].to_numpy(np.float32)
            blocks["n"].append(f"n:ndvi_{t}")
    if k >= TAG_IDX["09"]:
        for col in ["ndvi_max", "ndvi_integral"]:
            out[f"n:{col}"] = nd[col].to_numpy(np.float32)
            blocks["n"].append(f"n:{col}")
    # F6: спутник MODIS по закончившимся месяцам (как NDVI: месяц входит, если закончился до даты)
    sat = load_sat()
    if sat is not None:
        sr = sat.reindex(idx)
        known_m = [t for t in SAT_MONTHS if TAG_IDX[t] <= k and TAG_IDX[t] <= a1]
        for v in SAT_VARS:
            cols = [f"{v}_{t}" for t in known_m if f"{v}_{t}" in sr]
            for c in cols:
                out[f"g:{c}"] = sr[c].to_numpy(np.float32)
                blocks["g"].append(f"g:{c}")
            if cols and v in SAT_PEAK:
                out[f"g:{v}_pk"] = sr[cols].max(axis=1).to_numpy(np.float32)
                blocks["g"].append(f"g:{v}_pk")
            if cols and v in SAT_CUM:
                out[f"g:{v}_cum"] = sr[cols].sum(axis=1, min_count=1).to_numpy(np.float32)
                blocks["g"].append(f"g:{v}_cum")
    # рельеф и класс почвы WRB — константы региона
    el = load_elev()
    if el is not None:
        el = el.reindex(okatos)
        for c in el.columns:
            out[f"e:{c}"] = el[c].to_numpy(np.float32)
            blocks["e"].append(f"e:{c}")
    wrb = load_soil()["wrb_dominant"]
    levels = {v: i for i, v in enumerate(sorted(wrb.dropna().unique()))}
    out["e:wrb"] = wrb.reindex(okatos).map(levels).to_numpy(np.float32)
    blocks["e"].append("e:wrb")
    grid = pd.DataFrame(out, index=idx)
    return FeatureGrid(crop, date, grid, blocks)


def fold_features(fg: FeatureGrid, T: int, cols: list[str], norm_mode: str = "fold") -> pd.DataFrame:
    """Признаки для фолда с тестовым годом T: аномалии к норме 2001…T−1 (или 2001–2021)."""
    g = fg.grid[cols]
    end = T - 1 if norm_mode == "fold" else 2021
    years = g.index.get_level_values(1)
    norm = g[(years >= 2001) & (years <= end)].groupby(level=0).mean()
    norm_full = norm.reindex(g.index.get_level_values(0)).to_numpy()
    x = g.to_numpy(np.float64, copy=True)
    is_anom = np.array([c[0] in FeatureGrid.ANOM_BLOCKS for c in cols])
    is_clim = np.array([c[0] == "c" for c in cols])
    x[:, is_anom] -= norm_full[:, is_anom]
    x[:, is_clim] = norm_full[:, is_clim]
    return pd.DataFrame(x, index=g.index, columns=cols)
