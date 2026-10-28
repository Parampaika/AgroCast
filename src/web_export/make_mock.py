"""Собирает данные для веб-прототипа `web/data/*.json` по контракту docs/06_ui_data_contract.md.

Реальное берётся из data/clean и reports/tables: границы, история урожайности, площади,
погода сезона, почвы, цены, предварительный прогноз 2026 и метрики исследовательской модели.
Заглушки (флаг "mock": true): прогнозы по датам, факторы погоды, затраты, поправки.

Запуск: uv run python -I -X utf8 src/web_export/make_mock.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parents[2]
CLEAN = ROOT / "data" / "clean"
TABLES = ROOT / "reports" / "tables"
GEO = ROOT / "data" / "raw" / "geo"
OUT = ROOT / "web" / "data"

SEASON = 2026
HIST_FROM = 2000
NORM_YEARS = (2001, 2021)

# Культуры прототипа: код ЕМИСС, slug, иконка, поправки севооборота и затраты (допущения).
CROPS = [
    dict(crop_code="1010400", slug="winter_wheat", name="Пшеница озимая", short="Озимая пшеница", icon="wheat",
         product="wheat", max_share=0.6, cost_rub_ha=46000, color="#C8962E"),
    dict(crop_code="1010500", slug="spring_wheat", name="Пшеница яровая", short="Яровая пшеница", icon="wheat",
         product="wheat", max_share=0.6, cost_rub_ha=34000, color="#E0B656"),
    dict(crop_code="1030100", slug="barley", name="Ячмень яровой", short="Ячмень", icon="barley",
         product="barley", max_share=0.5, cost_rub_ha=32000, color="#8FA35A"),
    dict(crop_code="1080202", slug="maize", name="Кукуруза на зерно", short="Кукуруза", icon="maize",
         product="maize", max_share=0.4, cost_rub_ha=58000, color="#E6A532"),
    dict(crop_code="3080000", slug="sunflower", name="Подсолнечник", short="Подсолнечник", icon="sunflower",
         product="sunflower", max_share=0.25, cost_rub_ha=44000, color="#F2C230"),
    dict(crop_code="3100000", slug="soy", name="Соя", short="Соя", icon="soy",
         product="soy", max_share=0.3, cost_rub_ha=42000, color="#5E8C4A"),
    dict(crop_code="3060100", slug="sugar_beet", name="Сахарная свёкла", short="Свёкла", icon="beet",
         product="sugar_beet", max_share=0.2, cost_rub_ha=115000, color="#A04A5A"),
]
CODES = [c["crop_code"] for c in CROPS]
NAME_BY_CODE = {c["crop_code"]: c["name"] for c in CROPS}

DATES = [
    dict(id="05-01", label="1 мая", cutoff="1 мая"),
    dict(id="06-01", label="1 июня", cutoff="1 июня"),
    dict(id="07-01", label="1 июля", cutoff="1 июля"),
    dict(id="08-01", label="1 авг", cutoff="1 авг"),
    dict(id="final", label="Конец сезона", cutoff="конец"),
]
# Доля итогового погодного отклонения, известная к дате (по таблице выигрыша leadtime_metrics).
KNOWN_FRAC = {
    "winter_wheat": [0.75, 0.82, 0.88, 0.95, 1.0],
    "spring_wheat": [0.08, 0.15, 0.35, 0.85, 1.0],
    "barley": [0.08, 0.15, 0.4, 0.85, 1.0],
    "maize": [0.05, 0.12, 0.3, 0.75, 1.0],
    "sunflower": [0.03, 0.08, 0.25, 0.6, 1.0],
    "soy": [0.03, 0.08, 0.25, 0.65, 1.0],
    "sugar_beet": [0.05, 0.12, 0.25, 0.55, 1.0],
}

# Факторы погоды для блока «Почему такой прогноз»: переменная, месяц, подпись, ед., знак влияния по культурам.
# Знаки и масштабы — заглушка в духе reports/model_weather.md (раздел 2), не выход модели.
DRIVERS = [
    ("sm28_100", 3, "Влага в почве в марте", "м³/м³", dict(winter_wheat=1, spring_wheat=0.6, barley=0.6, maize=0.8, sunflower=0.5, soy=0.7, sugar_beet=0.7)),
    ("tmean", 5, "Температура мая", "°C", dict(winter_wheat=-1, spring_wheat=-0.4, barley=-0.5, maize=0.3, sunflower=0.2, soy=0.1, sugar_beet=-0.3)),
    ("hot30", 6, "Жаркие дни в июне", "дн.", dict(winter_wheat=-0.7, spring_wheat=-1, barley=-1, maize=-0.6, sunflower=-0.4, soy=-0.6, sugar_beet=-0.5)),
    ("prec", 6, "Осадки июня", "мм", dict(winter_wheat=0.5, spring_wheat=1, barley=1, maize=0.8, sunflower=0.5, soy=0.8, sugar_beet=0.7)),
    ("hot30", 7, "Жаркие дни в июле", "дн.", dict(winter_wheat=-0.2, spring_wheat=-0.8, barley=-0.6, maize=-1, sunflower=-0.7, soy=-1, sugar_beet=-0.8)),
    ("cwb", 7, "Водный баланс июля", "мм", dict(winter_wheat=0.2, spring_wheat=0.8, barley=0.6, maize=1, sunflower=0.6, soy=1, sugar_beet=1)),
    ("prec", 8, "Осадки августа", "мм", dict(winter_wheat=0, spring_wheat=0.2, barley=0.1, maize=0.6, sunflower=0.4, soy=0.7, sugar_beet=1)),
    ("frost0", 5, "Заморозки в мае", "дн.", dict(winter_wheat=-0.3, spring_wheat=-0.3, barley=-0.3, maize=-0.6, sunflower=-0.5, soy=-0.6, sugar_beet=-0.5)),
]

TECH = dict(
    soil=[dict(id="poor", label="Хуже средней по региону", yield_mult=0.88, cost_mult=1.0),
          dict(id="avg", label="Средняя по региону", yield_mult=1.0, cost_mult=1.0),
          dict(id="good", label="Лучше средней (чернозём, ровный участок)", yield_mult=1.1, cost_mult=1.0)],
    variety=[dict(id="standard", label="Районированный стандарт", yield_mult=1.0, cost_mult=1.0, risk_mult=1.0),
             dict(id="high", label="Высокоурожайный гибрид / сорт", yield_mult=1.08, cost_mult=1.06, risk_mult=1.1),
             dict(id="drought", label="Засухоустойчивый", yield_mult=0.97, cost_mult=1.02, risk_mult=0.75)],
    tech=[dict(id="extensive", label="Экстенсивная (минимум удобрений)", yield_mult=0.82, cost_mult=0.75),
          dict(id="base", label="Базовая", yield_mult=1.0, cost_mult=1.0),
          dict(id="intensive", label="Интенсивная (полное питание, защита)", yield_mult=1.18, cost_mult=1.3)],
)


SHORT_NAMES = {
    "Город Москва столица Российской Федерации город федерального значения": "Москва",
    "Город Санкт-Петербург город федерального значения": "Санкт-Петербург",
    "Город федерального значения Севастополь": "Севастополь",
    "Чувашская Республика - Чувашия": "Чувашская Республика",
    "Кемеровская область - Кузбасс": "Кемеровская область — Кузбасс",
    "Республика Северная Осетия-Алания": "Северная Осетия — Алания",
}


def short_name(name: str) -> str:
    import re
    name = SHORT_NAMES.get(name, name)
    if name.startswith("Тюменская область"):
        return "Тюменская область"
    if name.startswith("Архангельская область"):
        return "Архангельская область"
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()


def r3(x, n=3):
    if x is None:
        return None
    x = float(x)
    return round(x, n) if math.isfinite(x) else None


def dump(name: str, obj) -> None:
    path = OUT / name
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    print(f"{name:24s} {path.stat().st_size / 1024:8.0f} КБ")


def meta(mock: bool, source: str, note: str = "") -> dict:
    return {"mock": mock, "season": SEASON, "source": source, "note": note,
            "generated": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")}


# ---------------------------------------------------------------- регионы и границы
def build_regions(regions: pd.DataFrame) -> None:
    feats = {}
    for fn, src in [("geoboundaries_RUS_ADM1_simplified.geojson", "RUS"),
                    ("geoboundaries_UKR_ADM1_simplified.geojson", "UKR")]:
        g = json.loads((GEO / fn).read_text(encoding="utf-8"))
        for f in g["features"]:
            feats[(src, f["properties"]["shapeName"])] = f["geometry"]

    def fix(coords):  # Чукотка через антимеридиан: долготы < 0 переносим в 180…360
        if isinstance(coords[0], (int, float)):
            lon, lat = coords[0], coords[1]
            return [round(lon + 360 if lon < 0 else lon, 3), round(lat, 3)]
        return [fix(c) for c in coords]

    out = []
    for r in regions.itertuples():
        geom = feats.get((r.geo_source, r.geo_name))
        if geom is None:
            print("нет полигона:", r.name_emiss)
            continue
        shp = shape(geom).simplify(0.03, preserve_topology=True)
        # Мелкие острова отбрасываем, чтобы файл был лёгким
        if shp.geom_type == "MultiPolygon":
            parts = sorted(shp.geoms, key=lambda p: p.area, reverse=True)
            big = [p for p in parts if p.area > max(parts[0].area * 0.002, 0.003)] or parts[:1]
            shp = type(shp)(big) if len(big) > 1 else big[0]
        out.append({"type": "Feature",
                    "properties": {"okato": r.okato, "name": short_name(r.name_emiss), "fo": r.fo,
                                   "macro": r.macro_region, "is_city": bool(r.is_city),
                                   "is_new_subject": bool(r.is_new_subject),
                                   "lat": r3(r.cropland_centroid_lat, 2), "lon": r3(r.cropland_centroid_lon, 2)},
                    "geometry": {"type": shp.geom_type, "coordinates": fix(mapping(shp)["coordinates"])}})
    dump("regions.geojson", {"type": "FeatureCollection", "meta": meta(False, "geoBoundaries ADM1 (RUS, UKR), упрощено"),
                             "features": out})


# ---------------------------------------------------------------- история и тренды
def linear_trend(years: np.ndarray, vals: np.ndarray, target: int, window: int = 12):
    m = (years < target) & (years >= target - window) & np.isfinite(vals)
    if m.sum() < 5:
        return None
    k, b = np.polyfit(years[m], vals[m], 1)
    return k * target + b


def build_history(yp: pd.DataFrame):
    rows = yp[(yp.farm_category_code.astype(str) == "1") & yp.crop_code.isin(CODES)
              & yp.region_level.isin(["subject", "rf"]) & (yp.year >= HIST_FROM)].copy()
    rows["okato"] = rows.okato.where(rows.region_level == "subject", "643")
    years = list(range(HIST_FROM, SEASON + 1))
    series = {}
    trend_season = {}
    for (ok, cc), g in rows.groupby(["okato", "crop_code"]):
        g = g.set_index("year").reindex(range(HIST_FROM, SEASON))
        y = g.yield_t_ha.to_numpy(float)
        # 2025: итога Росстата нет — берём расчётную урожайность «сбор / посевная»
        y_est = np.where(np.arange(HIST_FROM, SEASON) == 2025, g.yield_calc_t_ha.to_numpy(float), np.nan)
        yy = np.where(np.isfinite(y), y, y_est)
        if np.isfinite(y).sum() < 6:
            continue
        ya = np.arange(HIST_FROM, SEASON)
        tr = [linear_trend(ya, yy, t) for t in years]
        series.setdefault(ok, {})[cc] = {
            "yield": [r3(v) for v in y] + [None],
            "yield_est": [r3(v) for v in y_est] + [None],
            "trend": [r3(v) for v in tr],
            "area_kha": [r3(v, 1) for v in g.area_kha.to_numpy(float)] + [None],
            "gross_kt": [r3(v, 1) for v in g.gross_kt.to_numpy(float)] + [None],
        }
        trend_season[(ok, cc)] = tr[-1]
    dump("history.json", {"meta": meta(False, "ЕМИСС 31533/31328/30950 через data/clean/yield_panel.parquet",
                                       "Все категории хозяйств. yield_est — 2025 г., сбор / посевная (итогов Росстата ещё нет). "
                                       "trend — линейный тренд по 12 предыдущим годам."),
                          "years": years, "series": series})
    return series, trend_season


# ---------------------------------------------------------------- погода сезона и факторы
def build_weather(wm: pd.DataFrame):
    wm = wm.copy()
    wm["season"] = np.where(wm.month >= 9, wm.year + 1, wm.year)
    wm["tag"] = wm.month
    cols = ["tmean", "prec", "htc", "hot30", "sm28_100", "cwb", "frost0"]
    norm = (wm[(wm.season >= NORM_YEARS[0]) & (wm.season <= NORM_YEARS[1])]
            .groupby(["okato", "month"])[cols].mean())
    cur = wm[wm.season == SEASON].set_index(["okato", "month"])[cols]
    months = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    out = {}
    for ok in wm.okato.unique():
        d = {}
        for v in ["tmean", "prec", "htc"]:
            fact, nrm = [], []
            for i, m in enumerate(months):
                key = (ok, m)
                if i >= 12:  # сентябрь–октябрь года урожая
                    fact.append(r3(wm[(wm.okato == ok) & (wm.year == SEASON) & (wm.month == m)][v].mean(), 2))
                else:
                    fact.append(r3(cur[v].get(key, np.nan), 2) if key in cur.index else None)
                nrm.append(r3(norm[v].get(key, np.nan), 2) if key in norm.index else None)
            d[v] = {"fact": fact, "norm": nrm}
        out[ok] = d
    labels = ["сен", "окт", "ноя", "дек", "янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт"]
    dump("weather_season.json", {"meta": meta(False, "ERA5-Land/ERA5 по точкам пашни, data/clean/weather_region_month.parquet",
                                              f"Сезон {SEASON}: сентябрь {SEASON-1} — октябрь {SEASON}. Норма — средняя за {NORM_YEARS[0]}–{NORM_YEARS[1]}. "
                                              "htc — ГТК Селянинова (NaN в холодные месяцы)."),
                                 "months": labels, "vars": {"tmean": "°C", "prec": "мм", "htc": "—"}, "regions": out})
    # аномалии для факторов
    anom = {}
    sd = (wm[(wm.season >= NORM_YEARS[0]) & (wm.season <= NORM_YEARS[1])]
          .groupby(["okato", "month"])[cols].std())
    for ok in wm.okato.unique():
        for var, m, *_ in DRIVERS:
            key = (ok, m)
            if key in cur.index and key in norm.index:
                a = cur[var].get(key) - norm[var].get(key)
                s = sd[var].get(key) or 1
                anom[(ok, var, m)] = (a, a / s if s else 0.0)
    return anom


def build_drivers(anom, r_final):
    out = {}
    for (ok, cc), r in r_final.items():
        slug = next(c["slug"] for c in CROPS if c["crop_code"] == cc)
        items = []
        for var, m, label, unit, signs in DRIVERS:
            a = anom.get((ok, var, m))
            if a is None or signs.get(slug, 0) == 0:
                continue
            z = max(-3, min(3, a[1]))
            items.append([var, m, label, unit, a[0], z * signs[slug]])
        if not items:
            continue
        raw = np.array([it[5] for it in items])
        # масштабируем вклады так, чтобы сумма совпала с итоговым отклонением прогноза от тренда
        s = raw.sum()
        scale = (r * 100) / s if abs(s) > 0.3 and np.sign(s) == np.sign(r) else 2.0
        scale = max(-6.0, min(6.0, scale))
        res = []
        for (var, m, label, unit, a, w) in items:
            res.append({"feature": f"{var}_{m:02d}", "label": label, "unit": unit,
                        "anomaly": r3(a, 2), "contrib_pct": r3(w * scale, 2)})
        res.sort(key=lambda x: -abs(x["contrib_pct"]))
        out.setdefault(ok, {})[cc] = res[:6]
    dump("drivers.json", {"meta": meta(True, "заглушка: аномалии погоды 2026 реальные, знаки и веса — условные",
                                       "contrib_pct — вклад фактора в отклонение прогноза от тренда, п.п. "
                                       "Позже заменяется SHAP-вкладами модели."),
                          "regions": out})


# ---------------------------------------------------------------- прогноз
def build_forecast(history, trend_season, area_last):
    fr = pd.read_csv(TABLES / "forecast_2026_regions.csv", dtype={"okato": str, "crop_code": str})
    fr["okato"] = fr.okato.str.zfill(11)
    r_model = {(r.okato, r.crop_code): r.r_hat for r in fr.itertuples()}
    calib = pd.read_csv(TABLES / "intervals_calibrated.csv")
    lead = pd.read_csv(TABLES / "leadtime_metrics_ens_lin.csv")
    rng = np.random.default_rng(2026)
    out, r_final = {}, {}
    for ok, crops in history.items():
        if ok == "643":
            continue
        for cc, s in crops.items():
            tr = trend_season.get((ok, cc))
            area = area_last.get((ok, cc))
            if tr is None or tr <= 0 or not area or area < 1:  # меньше 1 тыс. га — не показываем
                continue
            c = next(x for x in CROPS if x["crop_code"] == cc)
            y = np.array([v for v in s["yield"][:-1] if v is not None], float)
            cv = float(np.std(y[-12:] / np.mean(y[-12:]))) if len(y) >= 6 else 0.2
            if (ok, cc) in r_model:
                r_end, src = float(r_model[(ok, cc)]), "model_2026"
            else:
                r_end, src = float(np.clip(rng.normal(0, cv * 0.5), -0.25, 0.25)), "mock"
            r_final[(ok, cc)] = r_end
            area = area_last.get((ok, cc))
            rows = []
            for i, d in enumerate(DATES):
                frac = KNOWN_FRAC[c["slug"]][i]
                wiggle = (1 - frac) * rng.normal(0, 0.04)
                r = r_end * frac + wiggle
                p50 = tr * (1 + r)
                cw = calib[(calib.crop == c["name"]) & (calib.cutoff == d["cutoff"])]
                lw = lead[(lead.crop == c["name"]) & (lead.cutoff == d["cutoff"])]
                width = float(cw.width.iloc[0]) if len(cw) else 55.0
                wwidth = float(lw.width80_pct.iloc[0]) if len(lw) else width * 0.4
                k = float(np.clip(cv / 0.18, 0.75, 1.5))
                half, whalf = width / 200 * k, wwidth / 200 * k
                rows.append({"date": d["id"], "p10": r3(p50 * (1 - half)), "p50": r3(p50),
                             "p90": r3(p50 * (1 + half)), "w_lo": r3(p50 * (1 - whalf)),
                             "w_hi": r3(p50 * (1 + whalf)), "dev_trend_pct": r3(r * 100, 1),
                             "volume_kt": r3(p50 * area, 1) if area else None})
            out.setdefault(ok, {})[cc] = {"trend": r3(tr), "area_kha": r3(area, 1), "source": src, "by_date": rows}
    dump("forecast.json", {"meta": meta(True, "заглушка на основе тренда; итоговое отклонение — предварительная модель "
                                              "«тренд × погода» (reports/tables/forecast_2026_regions.csv), где она есть",
                                        "p10/p90 — откалиброванный 80 % интервал (погода + ошибка модели), "
                                        "w_lo/w_hi — разброс только погодных сценариев. area_kha — посевная 2025 г."),
                           "dates": [{"id": d["id"], "label": d["label"]} for d in DATES], "regions": out})
    return r_final


# ---------------------------------------------------------------- сценарии
def build_scenarios(history, trend_season):
    years = list(range(2005, 2026))
    out = {}
    for ok, crops in history.items():
        res = {}
        for cc, s in crops.items():
            tr = trend_season.get((ok, cc))
            if tr is None or tr <= 0:
                continue
            ys, ts = s["yield"], s["trend"]
            dev = []
            for yr in years:
                i = yr - HIST_FROM
                y = ys[i] if ys[i] is not None else s["yield_est"][i]
                dev.append(y / ts[i] - 1 if (y is not None and ts[i]) else None)
            ok_dev = [d for d in dev if d is not None]
            if len(ok_dev) < 8:
                continue
            med = float(np.median(ok_dev))
            res[cc] = [r3(tr * (1 + np.clip(d if d is not None else med, -0.7, 0.7))) for d in dev]
        if res:
            out[ok] = res
    dump("scenarios.json", {"meta": meta(True, "заглушка: тренд 2026 × (1 + историческое отклонение от тренда года-аналога)",
                                         "Сценарий = погода одного прошлого сезона. Совместность культур сохраняется: "
                                         "засушливый год бьёт по всем культурам сразу. Позже — прогон модели по погоде прошлых лет."),
                            "scenario_years": years, "regions": out})


# ---------------------------------------------------------------- экономика, почвы, метрики
def build_economics(regions):
    pr = pd.read_parquet(CLEAN / "prices.parquet")
    pr = pr[pr.year == SEASON]
    prod = {c["product"] for c in CROPS}
    price = {}
    for r in pr[pr.product_id.isin(prod)].itertuples():
        price.setdefault(r.okato, {})[r.product_id] = round(float(r.price))
    out = {}
    for c in CROPS:
        out[c["crop_code"]] = {"product": c["product"], "cost_rub_ha": c["cost_rub_ha"],
                               "price_rf_rub_t": price.get("643", {}).get(c["product"])}
    region_prices = {ok: {c["crop_code"]: p.get(c["product"]) for c in CROPS} for ok, p in price.items() if ok != "643"}
    dump("economics.json", {"meta": meta(False, "цены — ЕМИСС 57693 (январь–сентябрь 2026, руб./т, подстановка субъект → ФО → РФ); "
                                               "затраты на 1 га и поправки — допущения",
                                         "Затраты — оценка полных затрат на гектар по открытым обзорам отрасли, не норматив."),
                            "assumption": True, "currency": "RUB", "crops": out, "region_prices": region_prices,
                            "adjustments": TECH})


def build_soils():
    s = pd.read_parquet(CLEAN / "soil_region.parquet")
    out = {}
    for r in s.itertuples():
        out[r.okato] = {"clay": r3(r.clay_0_30, 1), "sand": r3(r.sand_0_30, 1), "silt": r3(r.silt_0_30, 1),
                        "soc": r3(r.soc_0_30, 1), "ph": r3(r.phh2o_0_30, 2), "nitrogen": r3(r.nitrogen_0_30, 2),
                        "ocs": r3(r.ocs_0_30, 1), "wrb": r.wrb_dominant, "wrb_share": r3(r.wrb_dominant_share, 2)}
    dump("soils.json", {"meta": meta(False, "SoilGrids 2.0 (ISRIC), слой 0–30 см, среднее по точкам пашни",
                                     "clay/sand/silt — %, soc и nitrogen — г/кг, ocs — т/га, wrb — класс почв WRB"),
                        "regions": out})


def build_metrics():
    t = pd.read_csv(TABLES / "model_summary_rolling_table.csv")
    lead = pd.read_csv(TABLES / "leadtime_metrics_ens_lin.csv")
    names = {c["name"]: c["crop_code"] for c in CROPS}
    methods = ["прошлый год", "среднее 5 лет", "линейный тренд", "тренд × погода"]
    acc = []
    for r in t.itertuples(index=False):
        if r.crop not in names:
            continue
        row = {"crop_code": names[r.crop]}
        for m, v in zip(methods, r[1:5]):
            mae, mape = (float(x) for x in str(v).split(" / "))
            row[m] = {"mae": mae, "mape": mape}
        acc.append(row)
    lt = []
    for r in lead.itertuples():
        if r.crop in names:
            lt.append({"crop_code": names[r.crop], "cutoff": r.cutoff, "mape": r3(r.MAPE, 2),
                       "skill_pct": r3(r.skill_vs_trend * 100, 1)})
    dump("metrics.json", {"meta": meta(True, "предварительная модель «тренд × погода», скользящая проверка 2012–2025 "
                                             "(reports/model_weather.md); финальная модель ещё подбирается",
                                       "mae — т/га, mape — %, skill_pct — снижение MAE к линейному тренду, %"),
                          "methods": methods, "accuracy": acc, "leadtime": lt})


def build_crops():
    cal = pd.read_parquet(CLEAN / "crop_calendar.parquet")
    out = []
    for c in CROPS:
        k = cal[cal.crop_code == c["crop_code"]]
        out.append({**{k2: c[k2] for k2 in ["crop_code", "slug", "name", "short", "icon", "max_share", "color"]},
                    "plant_month": int(k.plant_month.median()) if len(k) else None,
                    "maturity_month": int(k.maturity_month.median()) if len(k) else None})
    dump("crops.json", {"meta": meta(False, "справочник прототипа; max_share — ограничение севооборота (допущение)"),
                        "crops": out})


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    regions = pd.read_parquet(CLEAN / "regions.parquet")
    build_regions(regions)
    build_crops()
    yp = pd.read_parquet(CLEAN / "yield_panel.parquet")
    history, trend_season = build_history(yp)
    area_last = {}
    for ok, crops in history.items():
        for cc, s in crops.items():
            a = [v for v in s["area_kha"] if v is not None]
            if a:
                area_last[(ok, cc)] = a[-1]
    anom = build_weather(pd.read_parquet(CLEAN / "weather_region_month.parquet"))
    r_final = build_forecast(history, trend_season, area_last)
    build_drivers(anom, r_final)
    build_scenarios(history, trend_season)
    build_economics(regions)
    build_soils()
    build_metrics()
    total = sum(p.stat().st_size for p in OUT.glob("*.json*"))
    print(f"итого {total / 1e6:.1f} МБ")


if __name__ == "__main__":
    main()
