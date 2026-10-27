"""Итоговые модели по культурам и датам и выгрузка в web/data (docs/06_ui_data_contract.md).

Для каждой пары «культура × дата» из результатов перебора берётся конфигурация с лучшей
MAE на DEV-годах (2012–2018): среднее 2/3/5 лучших моделей, одиночная модель или «тренд».
Выбор по DEV, чтобы отложенные годы 2019–2025 не участвовали в отборе. Модель обучается на
всех годах до 2025 и прогнозирует 2026. Интервал — по относительным ошибкам прошлых
скользящих прогнозов той же конфигурации (конформный, как в перебор).

    uv run python -I -X utf8 src/model/final.py [--results data/model/v2] [--smoke]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model import data as D  # noqa: E402
from model import cv  # noqa: E402
from model.models import Model  # noqa: E402

ROOT = D.ROOT
WEB = ROOT / "web" / "data"
SEASON = 2026
DATE_IDS = ["05-01", "06-01", "07-01", "08-01", "end"]
WEB_DATE = {"05-01": "05-01", "06-01": "06-01", "07-01": "07-01", "08-01": "08-01", "end": "final"}
WEB_LABEL = {"05-01": "1 мая", "06-01": "1 июня", "07-01": "1 июля", "08-01": "1 авг", "end": "Конец сезона"}
WEB_CUTOFF = {"05-01": "1 мая", "06-01": "1 июня", "07-01": "1 июля", "08-01": "1 авг", "end": "конец"}
SCEN_YEARS = list(range(2005, 2026))
WEATHER_PREFIX = ("m:", "w:", "n:", "g:")
CFG_COLS = ["crop", "date", "trend", "target", "feats", "model", "params", "sample", "norm"]


def r3(x, n=3):
    return None if x is None or not np.isfinite(x) else round(float(x), n)


# ---------------------------------------------------------------- выбор конфигураций
def pick(res: pd.DataFrame, crop: str, date: str) -> dict:
    """Лучший кандидат (по DEV) для культуры и даты: ансамбль, одиночная модель или тренд."""
    q = res[(res.eval_crop == crop) & (res.date == date) & res.dev_mae.notna()]
    q = q[q.model.isin(["trend", "ens_mean2", "ens_mean3", "ens_mean5"]) | ~q.model.str.startswith("ens_")]
    row = q.sort_values(["dev_mae", "mae"]).iloc[0]
    if row.model.startswith("ens_"):
        ids = json.loads(row.params)
        members = [res[res.cfg_id == i].iloc[0][CFG_COLS + ["cfg_id"]].to_dict() for i in ids]
    else:
        members = [row[CFG_COLS + ["cfg_id"]].to_dict()]
    return {"row": row, "members": members, "cfg_id": row.cfg_id, "kind": row.model}


# ---------------------------------------------------------------- обучение и прогноз 2026
class Fit:
    """Обученная конфигурация: прогноз на 2026 и пересчёт для сценариев / исключения признаков."""

    def __init__(self, cfg: cv.Config):
        self.cfg = cfg
        T = SEASON
        crops = sorted(D.CROP_NAME) if cfg.crop == "pooled" else [cfg.crop]
        parts = []
        for crop in crops:
            f, X = cv._crop_matrix(crop, cfg, T)
            if cfg.crop == "pooled":
                X["cat:crop"] = cv._code("crop", f.crop)
            parts.append((f, X))
        f = pd.concat([p[0] for p in parts], ignore_index=True)
        X = pd.concat([p[1] for p in parts], ignore_index=True)
        tr = f[f"tr_{cfg.trend}"].to_numpy()
        z = D.make_target(f.y.to_numpy(), tr, cfg.target)
        train = (f.year < T).to_numpy() & np.isfinite(z)
        if cfg.sample == "no_mismatch":
            train &= ~f.flag_mismatch.to_numpy()
        elif cfg.sample == "no_lo":
            train &= ~f.flag_lo.to_numpy()
        self.test = ((f.year == T).to_numpy() & np.isfinite(tr) & (tr > 0))
        self.f, self.X, self.tr = f, X, tr
        self.model = None
        self.const = 0.0
        params = json.loads(cfg.params)
        if cfg.model == "trend":
            pass
        elif X.shape[1] == 0:
            self.const = float(np.mean(z[train]))
        else:
            cats = [c for c in cv.CAT_COLS if c in X]
            self.model = Model(cfg.model, params, cats).fit(X[train], z[train])

    def predict(self, X: pd.DataFrame, tr: np.ndarray) -> np.ndarray:
        if self.cfg.model == "trend":
            zhat = np.zeros(len(X))
        elif self.model is None:
            zhat = np.full(len(X), self.const)
        else:
            zhat = self.model.predict(X)
        yhat = D.invert_target(zhat, tr, self.cfg.target)
        return np.where(np.isfinite(yhat) & (yhat > 0), yhat, tr)

    def rows(self, crop: str) -> np.ndarray:
        m = self.test.copy()
        return m & (self.f.crop.to_numpy() == crop)


def ensemble_predict(fits: list[Fit], crop: str, mod=None, year_from: int | None = None):
    """Среднее прогнозов членов по общим субъектам. mod(X, f, idx) → изменённый X (для сценариев)."""
    preds = []
    for ft in fits:
        idx = np.flatnonzero(ft.rows(crop))
        X = ft.X.iloc[idx].copy()
        if mod is not None:
            X = mod(ft, X, idx)
        yh = ft.predict(X, ft.tr[idx])
        preds.append(pd.Series(yh, index=ft.f.okato.to_numpy()[idx]))
    return pd.concat(preds, axis=1).dropna().mean(axis=1)  # субъекты, прогнозируемые всеми членами


WINTER_W = ("prec_p09_03", "tsoil_min_win", "cold20_win", "snow_win", "thaw_win")


def scenario_mod(year: int, k_known: int | None):
    """Сценарий погоды: месяцы после k_known берутся из года-аналога, до него — как в 2026.

    k_known=None — ничего не известно (весь сезон из аналога). Агрегаты за окно культуры
    смешиваются линейно по доле известных месяцев окна.
    """
    def mod(ft: Fit, X: pd.DataFrame, idx: np.ndarray) -> pd.DataFrame:
        f = ft.f
        key = pd.Series(np.arange(len(f)), index=pd.MultiIndex.from_arrays(
            [f.crop, f.okato, f.year]))
        src = key.reindex(pd.MultiIndex.from_arrays(
            [f.crop.to_numpy()[idx], f.okato.to_numpy()[idx], np.full(len(idx), year)])).to_numpy()
        ok = ~np.isnan(src)
        crops = f.crop.to_numpy()[idx]
        kk = -1 if k_known is None else k_known
        lam = np.array([min(1.0, max(0.0, (kk - D.CROP_MONTHS[c][0] + 1) / (D.CROP_MONTHS[c][1] - D.CROP_MONTHS[c][0] + 1)))
                        for c in crops])
        for col in [c for c in X.columns if c.startswith(WEATHER_PREFIX)]:
            name = col.split(":", 1)[1]
            own = X[col].to_numpy(float)
            an = np.full(len(idx), np.nan)
            an[ok] = ft.X[col].to_numpy(float)[src[ok].astype(int)]
            tag = name.rsplit("_", 1)[-1]
            if col[0] in "mng" and tag in D.TAG_IDX and not name.endswith("_pk"):
                w = np.full(len(idx), 1.0 if D.TAG_IDX[tag] <= kk else 0.0)
            elif col[0] == "w" and name in WINTER_W:
                w = np.full(len(idx), 1.0 if kk >= D.TAG_IDX["03"] else 0.0)
            else:
                w = lam
            X[col] = w * own + (1 - w) * an
        return X
    return mod


# ---------------------------------------------------------------- подписи факторов
VAR_LABEL = {"tmean": ("Температура", "°C"), "tmax": ("Макс. температура", "°C"), "tmin": ("Мин. температура", "°C"),
             "prec": ("Осадки", "мм"), "et0": ("Испаряемость", "мм"), "cwb": ("Водный баланс", "мм"),
             "rad": ("Радиация", "Вт/м²"), "vpd": ("Дефицит влажности воздуха", "кПа"),
             "sm7_28": ("Влага почвы 7–28 см", "м³/м³"), "sm28_100": ("Влага в почве", "м³/м³"),
             "hot30": ("Жаркие дни (>30 °C)", "дн."), "hot35": ("Дни выше 35 °C", "дн."), "gdd5": ("Сумма температур >5 °C", "°C·дн."),
             "gdd10": ("Сумма температур >10 °C", "°C·дн."), "frost0": ("Заморозки", "дн."), "dry_days": ("Сухие дни", "дн."),
             "snow_depth": ("Снежный покров", "м"), "tsoil_min": ("Мин. температура почвы", "°C"),
             "dry_spell": ("Самая длинная засуха", "дн.")}
MONTH = {"p09": "сентябрь", "p10": "октябрь", "p11": "ноябрь", "p12": "декабрь", "01": "январь", "02": "февраль",
         "03": "март", "04": "апрель", "05": "май", "06": "июнь", "07": "июль", "08": "август", "09": "сентябрь", "10": "октябрь"}
SAT_LABEL = {"lai": ("Индекс листовой поверхности (LAI)", "м²/м²"), "fpar": ("Поглощённая радиация (FPAR)", "доля"),
             "lst_day": ("Температура поверхности днём", "°C"), "lst_night": ("Температура поверхности ночью", "°C"),
             "lst_diff": ("Суточный размах температуры поверхности", "°C")}
WIN_OTHER = {"prec_p09_03": ("Осадки осень–март", "мм"), "tsoil_min_win": ("Мин. температура почвы зимой", "°C"),
             "cold20_win": ("Дни с морозом ниже −20 °C", "дн."), "snow_win": ("Снежный покров зимой", "м"),
             "thaw_win": ("Оттепели зимой", "дн.")}


def describe(col: str) -> tuple[str, str, str]:
    """(feature, подпись, единицы) для столбца признака."""
    blk, name = col.split(":", 1)
    if blk == "m":
        # sm28_100_03 → переменная sm28_100, месяц 03
        for tag in MONTH:
            if name.endswith("_" + tag):
                v = name[: -len(tag) - 1]
                lab, unit = VAR_LABEL.get(v, (v, ""))
                return name, f"{lab}, {MONTH[tag]}", unit
    if blk == "w":
        if name in WIN_OTHER:
            lab, unit = WIN_OTHER[name]
            return name, lab, unit
        v = name.removeprefix("win_")
        if v == "htc":
            return name, "ГТК за вегетацию", ""
        lab, unit = VAR_LABEL.get(v, (v, ""))
        return name, f"{lab} за вегетацию", unit
    if blk == "n":
        tag = name.removeprefix("ndvi_")
        return name, ("NDVI, " + MONTH[tag]) if tag in MONTH else ("NDVI: " + tag), ""
    if blk == "g":
        pk = name.endswith("_pk")
        base = name[:-3] if pk else name
        for v, (lab, unit) in SAT_LABEL.items():
            if base == v or base.startswith(v + "_") and base.removeprefix(v + "_") in MONTH:
                if pk:
                    return name, f"{lab}: максимум за сезон", unit
                return name, f"{lab}, {MONTH[base.removeprefix(v + '_')]}", unit
    return name, name, ""


# ---------------------------------------------------------------- задача на одну дату
def run_date(args):
    res_path, date, crops, smoke = args
    res = pd.read_csv(res_path, dtype={"cfg_id": str, "params": str, "sample": str, "norm": str})
    res = res[res.status == "ok"]
    preds_dir = Path(res_path).parent / "preds"
    D.LAST_YEAR = SEASON
    cache: dict[str, Fit] = {}
    out = {"forecast": {}, "meta": {}, "scen": {}, "drivers": {}, "q": {}}
    for crop in crops:
        t0 = time.time()
        ch = pick(res, crop, date)
        fits = []
        for m in ch["members"]:
            cid = m["cfg_id"]
            if cid not in cache:
                cache[cid] = Fit(cv.Config(**{k: m[k] for k in CFG_COLS}))
            fits.append(cache[cid])
        yhat = ensemble_predict(fits, crop)
        pr = pd.read_parquet(preds_dir / f"{ch['cfg_id']}.parquet").query("crop == @crop")
        e = (pr.y / pr.yhat - 1).dropna()
        q = np.quantile(e, [0.1, 0.25, 0.75, 0.9])
        eb = (pr.y / pr.bl_lin10 - 1).dropna()
        qb = np.quantile(eb, [0.1, 0.25, 0.75, 0.9])
        row = ch["row"]
        out["meta"][(crop, date)] = {
            "kind": ch["kind"], "members": [f"{m['model']}/{m['feats']}/{m['trend']}/{m['target']}" for m in ch["members"]],
            "mae": row.mae, "mape": row.mape, "gain_pct": row.gain_pct, "cov80": row.get("cov80"),
            "mae_bl_lin10": row.mae_bl_lin10, "mae_bl_mean5": row.mae_bl_mean5, "mae_bl_lag1": row.mae_bl_lag1,
            "dev_mae": row.dev_mae, "late_gain_pct": row.get("late_gain_pct")}
        out["forecast"][(crop, date)] = yhat
        out["q"][(crop, date)] = {"model": q.tolist(), "bl": qb.tolist(), "bias": float(np.median(e))}
        if date == "end":
            sc = {}
            for dd in ["pre"] + DATE_IDS:
                kk = None if dd == "pre" else D.DATES[dd]
                sc[dd] = pd.DataFrame({y: ensemble_predict(fits, crop, scenario_mod(y, kk)) for y in SCEN_YEARS})
            out["scen"][crop] = sc
            out["drivers"][crop] = drivers(fits, crop, yhat)
        print(f"[{date}] {crop}: {ch['kind']} {out['meta'][(crop, date)]['members']} "
              f"{len(yhat)} субъектов, {time.time() - t0:.0f} с", flush=True)
    return date, out


def drivers(fits: list[Fit], crop: str, yhat: pd.Series) -> dict:
    """Вклад погодных признаков: изменение прогноза при замене аномалии на нормальную (0)."""
    cols = sorted({c for ft in fits for c in ft.X.columns if c.startswith(WEATHER_PREFIX)})
    contrib, anom = {}, {}
    for c in cols:
        def mod(ft, X, idx, c=c):
            if c in X.columns:
                X[c] = 0.0
            return X
        zero = ensemble_predict(fits, crop, mod)
        contrib[c] = (yhat - zero.reindex(yhat.index))
    ft0 = fits[0]
    idx = np.flatnonzero(ft0.rows(crop))
    okatos = ft0.f.okato.to_numpy()[idx]
    for c in cols:
        if c in ft0.X.columns:
            anom[c] = pd.Series(ft0.X.iloc[idx][c].to_numpy(), index=okatos)
    return {"contrib": pd.DataFrame(contrib), "anom": pd.DataFrame(anom)}


# ---------------------------------------------------------------- сборка файлов
def meta(src: str, note: str, mock=False) -> dict:
    return {"mock": mock, "season": SEASON, "source": src, "note": note,
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M")}


def dump(name: str, obj) -> None:
    (WEB / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
                            encoding="utf-8")
    print("записан", name, f"{(WEB / name).stat().st_size / 1024:.0f} КБ")


def write_parquet(results, crops, fc, dates) -> None:
    """data/model/final/: прогнозы по датам и сценарии погоды для оптимизации (см. README.md там же)."""
    out = ROOT / "data" / "model" / "final"
    out.mkdir(parents=True, exist_ok=True)
    f_rows, s_rows = [], []
    for ok, byc in fc.items():
        for cc, v in byc.items():
            for r in v["by_date"]:
                f_rows.append({"okato": ok, "crop_code": cc, "forecast_date": r["date"], "trend_t_ha": v["trend"],
                               "area_kha": v["area_kha"], "source": v["source"], "p10": r["p10"], "p50": r["p50"],
                               "p90": r["p90"], "w_lo": r["w_lo"], "w_hi": r["w_hi"], "volume_kt": r["volume_kt"]})
    pd.DataFrame(f_rows).to_parquet(out / "forecast_by_date.parquet", index=False)
    if "end" in results:
        for crop in crops:
            cc = D.KEY_CROP[crop]
            for dd, df in results["end"]["scen"][crop].items():
                label = "pre_season" if dd == "pre" else WEB_DATE[dd]
                for ok in df.index:
                    for y in df.columns:
                        s_rows.append({"okato": ok, "crop_code": cc, "forecast_date": label, "scenario_year": y,
                                       "yield_t_ha": float(df.loc[ok, y])})
        sc = pd.DataFrame(s_rows)
        sc["scenario_year"] = sc.scenario_year.astype("int16")
        sc["yield_t_ha"] = sc.yield_t_ha.astype("float32")
        sc.to_parquet(out / "scenarios.parquet", index=False)
    print("parquet записан в", out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="data/model/v2")
    ap.add_argument("--smoke", action="store_true", help="одна культура, две даты, без записи в web/data")
    ap.add_argument("--jobs", type=int, default=5)
    ap.add_argument("--crops", default="", help="через запятую; для проверки")
    ap.add_argument("--dates", default="")
    ap.add_argument("--web", default="", help="куда писать JSON (по умолчанию web/data)")
    a = ap.parse_args()
    global WEB
    if a.web:
        WEB = Path(a.web)
        WEB.mkdir(parents=True, exist_ok=True)
        for f in ("history.json", "crops.json"):
            (WEB / f).write_bytes((ROOT / "web" / "data" / f).read_bytes())
    rdir = ROOT / a.results
    rpath = rdir / "sweep_results.csv"
    crops = sorted(D.CROP_NAME)
    dates = DATE_IDS
    if a.crops:
        crops = a.crops.split(",")
    if a.dates:
        dates = a.dates.split(",")
    if a.smoke:
        crops, dates = ["winter_wheat"], ["end"]
    t0 = time.time()
    with ProcessPoolExecutor(min(a.jobs, len(dates))) as ex:
        results = dict(ex.map(run_date, [(str(rpath), d, crops, a.smoke) for d in dates]))
    print(f"обучено за {time.time() - t0:.0f} с")

    hist = json.loads((WEB / "history.json").read_text(encoding="utf-8"))
    crops_js = json.loads((WEB / "crops.json").read_text(encoding="utf-8"))["crops"]
    slug2code = {c["slug"]: c["crop_code"] for c in crops_js}
    years = hist["years"]
    # --- прогноз
    fc = {}
    summary = []
    for ok, byc in hist["series"].items():
        if ok == "643":
            continue
        for cc, s in byc.items():
            crop = D.CROP_KEY[cc]
            if crop not in crops:
                continue
            tr = s["trend"][-1]
            area = next((v for v in reversed(s["area_kha"][:-1]) if v is not None), None)
            if tr is None or tr <= 0 or not area or area < 1:
                continue
            rows, src = [], "trend_only"
            for d in dates:
                yh = results[d]["forecast"][(crop, d)]
                q = results[d]["q"][(crop, d)]
                if ok in yh.index:
                    p50, qq, src = float(yh[ok]), q["model"], "model_2026"
                else:
                    p50, qq = tr, q["bl"]
                lo, lo2, hi2, hi = (p50 * (1 + x) for x in qq)
                lo, hi = min(lo, p50), max(hi, p50)
                sc = results["end"]["scen"].get(crop, {}).get(d) if "end" in results else None
                if sc is not None and ok in sc.index and ok in yh.index:  # погодные сценарии: известное до даты + аналоги
                    v = sc.loc[ok].to_numpy(float)
                    m = np.median(v)
                    wl, wh = p50 * np.quantile(v, 0.1) / m, p50 * np.quantile(v, 0.9) / m
                else:
                    wl, wh = min(lo2, p50), max(hi2, p50)
                wl, wh = max(lo, min(wl, p50)), min(hi, max(wh, p50))
                rows.append({"date": WEB_DATE[d], "p10": r3(lo), "p50": r3(p50), "p90": r3(hi),
                             "w_lo": r3(wl), "w_hi": r3(wh),
                             "dev_trend_pct": r3((p50 / tr - 1) * 100, 1), "volume_kt": r3(p50 * area, 1)})
            # источник: «model_2026», если модель работала на всех датах
            fc.setdefault(ok, {})[cc] = {"trend": r3(tr), "area_kha": r3(area, 1), "source": src, "by_date": rows}
    dates_js = [{"id": WEB_DATE[d], "label": WEB_LABEL[d]} for d in dates]
    note = ("p10/p90 — 80 % интервал по относительным ошибкам прошлых скользящих прогнозов (2009–2025) "
            "той же модели; w_lo/w_hi — 80 % разброс только погодных сценариев (известные месяцы 2026 + месяцы аналогов 2005–2025 в итоговой модели). area_kha — посевная 2025 г. "
            "source=trend_only — малые субъекты вне обучающей выборки: прогноз равен линейному тренду, "
            "интервал по ошибкам тренда.")
    smoke = a.smoke
    suffix = "_check" if a.web else ""
    if not smoke:
        dump("forecast.json", {"meta": meta("итоговые модели по результатам перебора (reports/sweep.md), "
                                            "обучены на сезонах до 2025 г. включительно", note),
                               "dates": dates_js, "regions": fc})
        # --- сценарии
        scen = {}
        for crop in crops:
            cc = slug2code[crop] if crop in slug2code else D.KEY_CROP[crop]
            df = results["end"]["scen"][crop]["pre"]
            med = (df.div(df.median(axis=1), axis=0)).median(axis=0)  # типичный профиль годов-аналогов
            for ok, byc in hist["series"].items():
                if ok == "643" or cc not in byc or ok not in fc or cc not in fc[ok]:
                    continue
                if ok in df.index:
                    vals = df.loc[ok].to_numpy()
                else:
                    vals = fc[ok][cc]["trend"] * med.to_numpy()
                scen.setdefault(ok, {})[cc] = [r3(v) for v in vals]
        dump("scenarios.json", {"meta": meta("итоговая модель «конец сезона» на погоде сезонов-аналогов 2005–2025",
                                             "Сценарий s: признаки погоды, NDVI и спутника 2026 заменены значениями года s "
                                             "(аномалии к норме 2001–2025), остальное — как в 2026. Для малых субъектов "
                                             "вне выборки: тренд × типичный профиль годов по культуре."),
                                "scenario_years": SCEN_YEARS, "regions": scen})
        write_parquet(results, crops, fc, dates)
        # --- факторы
        drv = {}
        for crop in crops:
            cc = D.KEY_CROP[crop]
            dd = results["end"]["drivers"][crop]
            for ok in dd["contrib"].index:
                if ok not in fc or cc not in fc[ok]:
                    continue
                tr = fc[ok][cc]["trend"]
                c = (dd["contrib"].loc[ok] / tr * 100).dropna()
                c = c[c.abs() > 1e-6].sort_values(key=lambda x: -x.abs()).head(6)
                items = []
                for col, v in c.items():
                    feat, lab, unit = describe(col)
                    an = dd["anom"].loc[ok].get(col)
                    items.append({"feature": feat, "label": lab, "unit": unit,
                                  "anomaly": r3(an, 2), "contrib_pct": r3(v, 2)})
                if items:
                    drv.setdefault(ok, {})[cc] = items
        dump("drivers.json", {"meta": meta("итоговая модель «конец сезона»: изменение прогноза при замене признака на норму",
                                           "contrib_pct — вклад признака в отклонение прогноза от тренда, п.п.; "
                                           "anomaly — аномалия 2026 к норме 2001–2025 (для NDVI/спутника — разность значений)."),
                              "regions": drv})
        # --- метрики
        acc, lead = [], []
        for crop in crops:
            cc = D.KEY_CROP[crop]
            m = results["end"]["meta"][(crop, "end")]
            for d in dates:
                mm = results[d]["meta"][(crop, d)]
                lead.append({"crop_code": cc, "cutoff": WEB_CUTOFF[d], "mape": r3(mm["mape"], 2),
                             "skill_pct": r3(100 * (1 - mm["mae"] / mm["mae_bl_lin10"]), 1)})
            acc.append((cc, m))
        # MAPE бейзлайнов — по прогнозам трендовой конфигурации «конец сезона»
        res = pd.read_csv(rpath, dtype={"cfg_id": str, "params": str})
        acc_js = []
        for cc, m in acc:
            crop = D.CROP_KEY[cc]
            tcfg = res[(res.eval_crop == crop) & (res.date == "end") & (res.model == "trend") & (res.status == "ok")]
            p = pd.read_parquet(rdir / "preds" / f"{tcfg.iloc[0].cfg_id}.parquet").query("crop == @crop and year >= 2012")
            mape = {b: float(100 * ((p[f"bl_{b}"] - p.y).abs() / p.y).mean()) for b in ("lag1", "mean5", "lin10")}
            acc_js.append({"crop_code": cc,
                           "прошлый год": {"mae": r3(m["mae_bl_lag1"]), "mape": r3(mape["lag1"], 1)},
                           "среднее 5 лет": {"mae": r3(m["mae_bl_mean5"]), "mape": r3(mape["mean5"], 1)},
                           "линейный тренд": {"mae": r3(m["mae_bl_lin10"]), "mape": r3(mape["lin10"], 1)},
                           "модель": {"mae": r3(m["mae"]), "mape": r3(m["mape"], 1)}})
        dump("metrics.json", {"meta": meta("скользящая проверка по времени 2012–2025 (reports/sweep.md), одна и та же выборка "
                                           "субъектов у модели и бейзлайнов",
                                           "mae — т/га, mape — %, skill_pct — снижение MAE к линейному тренду (10 лет), %. "
                                           "Модель — лучшая по DEV-годам 2012–2018 конфигурация на каждую дату."),
                              "methods": ["прошлый год", "среднее 5 лет", "линейный тренд", "модель"],
                              "accuracy": acc_js, "leadtime": lead})
    # --- журнал выбранных конфигураций
    lines = ["# Выбранные итоговые модели", "",
             "| культура | дата | тип | члены | MAE | выигрыш, % | покрытие 80 % |", "|---|---|---|---|---|---|---|"]
    for crop in crops:
        for d in dates:
            m = results[d]["meta"][(crop, d)]
            lines.append(f"| {D.CROP_NAME[crop]} | {WEB_LABEL[d]} | {m['kind']} | {'; '.join(m['members'])} | "
                         f"{m['mae']:.3f} | {m['gain_pct']:.1f} | {m['cov80'] if m['cov80'] is None else round(m['cov80'], 2)} |")
    out = ROOT / "reports" / ("final_models_smoke.md" if smoke else f"final_models{suffix}.md")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("готово", out)


if __name__ == "__main__":
    main()
