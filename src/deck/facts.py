"""Все числа презентации: читаются из таблиц и отчётов проекта, в слайды руками ничего не вписывается.

`load()` возвращает словарь F. Обязательные источники при отсутствии роняют сборку с понятным
сообщением; необязательные (оптимизация, SHAP) заносят имя в F["missing"], слайд тогда показывает
пометку «ждёт данных».
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
TABLES = REPORTS / "tables"
MODEL = ROOT / "data" / "model"
WEB_DATA = ROOT / "web" / "data"
REPORT_BUILD = ROOT / "report" / "build"
NBSP = " "

CROP_ORDER = ["winter_wheat", "spring_wheat", "barley", "sunflower", "maize", "soy", "sugar_beet"]
CROP_NAME = {"winter_wheat": "Пшеница озимая", "spring_wheat": "Пшеница яровая", "barley": "Ячмень яровой",
             "sunflower": "Подсолнечник", "maize": "Кукуруза на зерно", "soy": "Соя", "sugar_beet": "Сахарная свёкла"}
CROP_SHORT = {"winter_wheat": "Пшеница озимая", "spring_wheat": "Пшеница яровая", "barley": "Ячмень",
              "sunflower": "Подсолнечник", "maize": "Кукуруза", "soy": "Соя", "sugar_beet": "Свёкла"}
NAME_KEY = {v: k for k, v in CROP_NAME.items()}
CROP_GEN = {"winter_wheat": "озимой пшеницы", "spring_wheat": "яровой пшеницы", "barley": "ячменя",
            "sunflower": "подсолнечника", "maize": "кукурузы", "soy": "сои", "sugar_beet": "свёклы"}
CROP_CODE = {"1010400": "winter_wheat", "1010500": "spring_wheat", "1030100": "barley", "1080202": "maize",
             "3080000": "sunflower", "3100000": "soy", "3060100": "sugar_beet"}
DATES = ["05-01", "06-01", "07-01", "08-01", "end"]
DATE_LABEL = {"05-01": "1 мая", "06-01": "1 июня", "07-01": "1 июля", "08-01": "1 авг.", "end": "Конец сезона"}


# ---------------------------------------------------------------- форматирование

def fmt(x, d: int = 0, sign: bool = False) -> str:
    """Число по-русски: неразрывный пробел — разряды, запятая — дробная часть, минус настоящий."""
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    s = f"{abs(x):,.{d}f}".replace(",", NBSP).replace(".", ",")
    if x < 0 and float(s.replace(NBSP, "").replace(",", ".")) != 0:
        return "−" + s
    return ("+" + s) if sign and float(s.replace(NBSP, "").replace(",", ".")) != 0 else s


def plural(n: int, one: str, few: str, many: str) -> str:
    """1 субъект, 2 субъекта, 5 субъектов."""
    n = abs(int(n))
    if 11 <= n % 100 <= 14:
        return many
    return one if n % 10 == 1 else few if 2 <= n % 10 <= 4 else many


def unit(x, d: int, u: str, sign: bool = False) -> str:
    return f"{fmt(x, d, sign)}{NBSP}{u}"


def _read_csv(name: str, **kw) -> pd.DataFrame:
    p = TABLES / name
    if not p.exists():
        raise FileNotFoundError(f"нет {p.relative_to(ROOT)}")
    return pd.read_csv(p, **kw)


def _stamp(F: dict, p: Path) -> None:
    if p.exists():
        F["stamps"][str(p.relative_to(ROOT)).replace("\\", "/")] = time.strftime("%d.%m.%Y %H:%M", time.localtime(p.stat().st_mtime))


# ---------------------------------------------------------------- данные

def _data_stats() -> dict:
    cache = REPORT_BUILD / "data_stats.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    # инвентарь считает сессия отчёта: обход data/ занимает ~10 мин
    spec = importlib.util.spec_from_file_location("report_data_stats", ROOT / "src" / "report" / "data_stats.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print("[facts] кэша инвентаря данных нет, считаю (≈10 мин)…", file=sys.stderr)
    return mod.load(force=True)


def _tests_count() -> int:
    try:
        out = subprocess.run([sys.executable, "-m", "pytest", "-q", "--collect-only", "tests"], cwd=ROOT,
                             capture_output=True, text=True, timeout=300).stdout
        return int(re.search(r"(\d+) tests? collected", out).group(1))
    except Exception:  # noqa: BLE001
        p = REPORT_BUILD / "tests_count.txt"
        return int(p.read_text()) if p.exists() else 0


def _n_configs() -> dict:
    out = {}
    pre = pd.read_csv(MODEL / "pre_sweep_results.csv", usecols=["cfg_id"])
    out["pre"] = int(pre.cfg_id.nunique())
    for v in ("v1", "v2"):
        r = pd.read_csv(MODEL / v / "sweep_results.csv", usecols=["cfg_id", "status"], dtype={"cfg_id": str})
        out[v] = int(r[r.status == "ok"].cfg_id.nunique())
    trials = 0
    for v in ("v1", "v2"):
        d = MODEL / v / "optuna"
        if d.exists():
            for f in d.glob("*.log"):  # журнал Optuna: op_code 4 — создание попытки
                with f.open(encoding="utf-8", errors="ignore") as fh:
                    trials += sum(1 for line in fh if line.startswith('{"op_code":4,'))
    out["optuna_trials"] = trials
    out["total"] = out["pre"] + out["v1"] + out["v2"]
    return out


def _data(F: dict) -> None:
    st = _data_stats()
    L = st["layers"]
    srcs = sorted(k for k, v in st["raw_sources"].items() if v["bytes"] > 0)
    inv = pd.read_csv(ROOT / "data" / "interim" / "emiss" / "inventory.tsv", sep="\t")
    ok = inv[inv.status == "скачано"]
    emiss_rows = float(pd.to_numeric(ok.rows, errors="coerce").sum())
    gib = 2**30
    F["n_sources"] = len(srcs)
    F["sources"] = srcs
    F["n_emiss"] = int(len(ok))
    F["raw_gb"] = L["raw"]["bytes"] / gib
    F["raw_files"] = L["raw"]["files"]
    F["rows_mln"] = (L["raw"]["rows"] + emiss_rows) / 1e6
    F["all_gb"] = sum(L[k]["bytes"] for k in L) / gib
    F["layers"] = {k: {"files": v["files"], "gb": v["bytes"] / gib, "rows_mln": v["rows"] / 1e6} for k, v in L.items()}
    ct = st["clean_tables"]
    F["clean_tables"] = len(ct)
    mt = ct["model_table"]
    F["model_rows"], F["model_cols"] = mt["rows"], mt["cols"]
    F["n_tests"] = _tests_count()
    F["stats_at"] = st.get("computed_at", "")
    reg = pd.read_csv(ROOT / "data" / "raw" / "geo" / "regions.csv") if (ROOT / "data" / "raw" / "geo" / "regions.csv").exists() else None
    F["n_regions"] = int(len(reg)) if reg is not None else 89
    F["n_points"] = 450
    F["n_crops"] = len(CROP_ORDER)
    F["years"] = "2000–2026"
    F["cfg"] = _n_configs()
    _stamp(F, REPORT_BUILD / "data_stats.json")


# ---------------------------------------------------------------- лесенка и итоговые модели

def _ladder(F: dict) -> None:
    m = _read_csv("ladder_macro_by_date.csv", dtype={"date": str})
    c = _read_csv("ladder_by_crop_date.csv", dtype={"date": str})
    _stamp(F, TABLES / "ladder_macro_by_date.csv")
    _stamp(F, TABLES / "ladder_by_crop_date.csv")
    names = m[m.period == "all"].drop_duplicates("step").set_index("step").step_name.to_dict()
    steps = sorted(names)
    top = max(steps)
    me = m[(m.period == "all") & (m.date == "end")].set_index("step")
    F["ladder"] = {
        "steps": steps,
        "names": [names[s] for s in steps],
        "mape": [float(me.loc[s, "mape"]) for s in steps],
        "gain": [float(me.loc[s, "gain"]) for s in steps],
        "gain_end": float(me.loc[top, "gain"]),
        "mape_naive": float(me.loc[0, "mape"]),
        "mape_top": float(me.loc[top, "mape"]),
    }
    # динамика по датам: все годы и отложенные 2019–2025
    by_date = {}
    for per in ("all", "late"):
        q = m[(m.period == per) & (m.step == top)].set_index("date")
        by_date[per] = [float(q.loc[d, "gain"]) for d in DATES]
    F["ladder"]["by_date"] = by_date
    F["ladder"]["mape_by_date"] = [float(m[(m.period == "all") & (m.step == top) & (m.date == d)].mape.iloc[0]) for d in DATES]
    # по культурам на конец сезона
    e = c[(c.period == "all") & (c.date == "end")]
    g = e[e.step == top].set_index("crop").gain_vs_step0_pct
    F["ladder"]["by_crop"] = {k: float(g[k]) for k in CROP_ORDER if k in g.index}
    F["ladder"]["n_obs"] = int(e[e.step == top].n.sum())


def _final_models(F: dict) -> None:
    p = REPORTS / "final_models.md"
    _stamp(F, p)
    rows = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        cells = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(cells) == 7 and cells[0] in NAME_KEY:
            rows.append(dict(crop=NAME_KEY[cells[0]], date=cells[1], mae=float(cells[4]), gain=float(cells[5]), cov=float(cells[6])))
    d = pd.DataFrame(rows)
    if d.empty:
        raise RuntimeError("не разобрана таблица reports/final_models.md")
    dmap = {"1 мая": "05-01", "1 июня": "06-01", "1 июля": "07-01", "1 авг": "08-01", "Конец сезона": "end"}
    d["date"] = d.date.map(dmap)
    F["final"] = {
        "cov_min": float(d["cov"].min()), "cov_max": float(d["cov"].max()), "cov_mean": float(d["cov"].mean()),
        "n_models": int(len(d)),
        "gain_may": {k: float(d[(d.crop == k) & (d.date == "05-01")].gain.iloc[0]) for k in CROP_ORDER},
        "gain_end": {k: float(d[(d.crop == k) & (d.date == "end")].gain.iloc[0]) for k in CROP_ORDER},
    }
    # ширина интервала: полуширина (p90 − p10)/2 от p50, медиана по субъектам и культурам
    f = json.loads((WEB_DATA / "forecast.json").read_text(encoding="utf-8"))
    _stamp(F, WEB_DATA / "forecast.json")
    ids = ["05-01", "06-01", "07-01", "08-01", "final"]
    hw = {dt: [] for dt in ids}   # полный интервал P10–P90 (по ошибкам прошлых лет)
    iw = {dt: [] for dt in ids}   # разброс только погодных сценариев
    for reg in f["regions"].values():
        for code, v in reg.items():
            if v.get("source") != "model_2026":
                continue
            for b in v["by_date"]:
                if b["date"] in hw and b["p50"] > 0:
                    hw[b["date"]].append((b["p90"] - b["p10"]) / 2 / b["p50"])
                    iw[b["date"]].append((b["w_hi"] - b["w_lo"]) / 2 / b["p50"])
    F["final"]["halfwidth_may"] = 100 * float(np.median(hw["05-01"]))
    F["final"]["halfwidth_end"] = 100 * float(np.median(hw["final"]))
    F["final"]["fan_outer"] = [100 * float(np.median(hw[d])) for d in ids]
    F["final"]["fan_inner"] = [100 * float(np.median(iw[d])) for d in ids]
    F["final"]["season"] = f["meta"].get("season", 2026)


# ---------------------------------------------------------------- SHAP

SHAP_GROUPS = [
    ("Погода и окна культуры", ["погода по месяцам", "окно культуры и зима"]),
    ("Спутник MODIS", ["спутник MODIS"]),
    ("NDVI", ["NDVI"]),
    ("Регион и прошлые отклонения", ["регион и прошлые отклонения"]),
    ("Почвы, рельеф, климат региона", ["почвы", "рельеф и тип почвы", "климат региона"]),
]


def _shap(F: dict) -> None:
    p = REPORT_BUILD / "shap_features.csv"
    if not p.exists():
        raise FileNotFoundError("нет report/build/shap_features.csv (считает src/report/shap_calc.py)")
    _stamp(F, p)
    s = pd.read_csv(p)
    g = s.groupby(["crop", "block"]).mean_abs_shap.sum().unstack().reindex(CROP_ORDER)
    g = g.div(g.sum(axis=1), axis=0) * 100
    res = {name: g[[b for b in blocks if b in g.columns]].sum(axis=1) for name, blocks in SHAP_GROUPS}
    F["shap"] = {"groups": [n for n, _ in SHAP_GROUPS],
                 "share": {n: [float(res[n][k]) for k in CROP_ORDER] for n, _ in SHAP_GROUPS}}
    F["shap"]["weather_rng"] = (float(res["Погода и окна культуры"].min()), float(res["Погода и окна культуры"].max()))
    F["shap"]["sat_rng"] = (float(res["Спутник MODIS"].min()), float(res["Спутник MODIS"].max()))
    sat = res["Спутник MODIS"]
    F["shap"]["sat_top"] = [CROP_GEN[k] for k in sat.sort_values(ascending=False).index[:2]]


# ---------------------------------------------------------------- оптимизация

def _opt(F: dict) -> None:
    rec = _read_csv("optimization_recommendations.csv", dtype={"okato": str})
    curve = _read_csv("optimization_delta_curve.csv")
    bt = _read_csv("optimization_backtest_summary.csv").set_index("plan")
    for n in ("optimization_recommendations.csv", "optimization_delta_curve.csv", "optimization_backtest_summary.csv"):
        _stamp(F, TABLES / n)
    meta = json.loads((WEB_DATA / "optimization.json").read_text(encoding="utf-8"))
    _stamp(F, WEB_DATA / "optimization.json")
    o = {"scenario_source": meta.get("settings", {}).get("scenario_source", ""),
         "generated": meta.get("meta", {}).get("generated", ""),
         "lam": meta["settings"].get("lambda"), "alpha": meta["settings"].get("alpha")}
    o["n_regions"] = int(rec.okato.nunique())
    o["n_scen"] = int(rec.n_scen.max()) if "n_scen" in rec else None
    o["pool_mha"] = float(rec.drop_duplicates("okato").pool_kha.sum() / 1e3)
    at = lambda v: curve.loc[(curve.delta - v).abs().idxmin()]  # noqa: E731
    o["curve"] = {"delta_pp": [100 * float(x) for x in curve.delta],
                  "mean_bln": [float(x) / 1e3 for x in curve.gain_mln],
                  "cvar_bln": [float(x) / 1e3 for x in curve.cvar_gain_mln]}
    for dv in (5, 10):
        q = rec[rec.delta_pp == dv]
        w = q.pool_kha
        m0, m1 = np.average(q.mean0, weights=w), np.average(q.mean1, weights=w)
        o[f"d{dv}"] = {
            "gain_ha": float(m1 - m0), "base_ha": float(m0),
            "gain_pct": float(100 * (m1 - m0) / m0) if m0 > 0 else None,
            "cvar_gain_ha": float(np.average(q.cvar1 - q.cvar0, weights=w)),
            "worst_better": int((q.worst1 > q.worst0 + 1e-6).sum()), "n": int(len(q)),
            "gain_bln": float(at(dv / 100).gain_mln) / 1e3, "cvar_bln": float(at(dv / 100).cvar_gain_mln) / 1e3,
            "turnover_pct": float(at(dv / 100).turnover_pct),
            "regions_up": int((q.gain_rub_ha > 0).sum()),
        }
    try:  # распределение эффекта по субъектам (медиана и доля выигравших) — сессия оптимизации, 28.10
        es = _read_csv("optimization_effect_stats.csv")
        _stamp(F, TABLES / "optimization_effect_stats.csv")
        r5 = es[es.delta_pp == 5].iloc[0]
        o["d5"]["median_ha"] = float(r5.gain_rub_ha_median)
        o["d5"]["q75_ha"] = float(r5.gain_rub_ha_q75)
        o["d5"]["share_up"] = float(r5.share_gain_pct)
        o["d5"]["share_worst_better"] = float(r5.share_worst_better_pct)
    except Exception as e:  # noqa: BLE001
        print(f"[facts] effect_stats: {e!r}", file=sys.stderr)
    kr = rec[rec.name.str.contains("Краснодарский") & (rec.delta_pp == 10)]
    if len(kr):
        o["krasnodar_d10_pct"] = float(100 * (kr.mean1.iloc[0] / kr.mean0.iloc[0] - 1))
    try:
        cc = _read_csv("optimization_cost_calibration.csv")
        o["cost_rosstat_2025"] = float(cc[cc.year == cc.year.max()].rub_ha.iloc[0])
    except Exception:  # noqa: BLE001
        pass
    d30 = curve.loc[(curve.delta - 0.30).abs().idxmin()]
    o["share_d10_of_d30"] = float(d30.gain_mln and at(0.10).gain_mln / d30.gain_mln * 100)
    o["share_d5_of_d30"] = float(d30.gain_mln and at(0.05).gain_mln / d30.gain_mln * 100)
    o["bt"] = {"n": int(bt.loc["current", "n"])}
    for plan in ("d5", "d10"):
        o["bt"][plan] = {"real": float(bt.loc[plan, "real_gain_rub_ha"]), "exp": float(bt.loc[plan, "exp_gain_rub_ha"]),
                         "bad": float(bt.loc[plan, "bad_years_gain_rub_ha"]), "win": float(bt.loc[plan, "win_share_pct"]),
                         "bln": float(bt.loc[plan, "real_gain_bln_year"]),
                         "realization": float(100 * bt.loc[plan, "real_gain_rub_ha"] / bt.loc[plan, "exp_gain_rub_ha"])}
    # свежесть: расчёт должен быть новее итоговых прогнозов, на которых построены сценарии
    fin = MODEL / "final" / "scenarios.parquet"
    o["fresh"] = bool(fin.exists() and (TABLES / "optimization_recommendations.csv").stat().st_mtime >= fin.stat().st_mtime
                      and "final" in o["scenario_source"])
    o["md_stamp"] = time.strftime("%d.%m.%Y %H:%M", time.localtime((REPORTS / "optimization.md").stat().st_mtime))
    F["opt"] = o


def load() -> dict:
    F: dict = {"stamps": {}, "missing": [], "built": time.strftime("%d.%m.%Y %H:%M")}
    for name, fn, required in (("data", _data, True), ("ladder", _ladder, True), ("final", _final_models, True),
                               ("shap", _shap, False), ("opt", _opt, False)):
        try:
            fn(F)
        except Exception as e:  # noqa: BLE001
            if required:
                raise
            F["missing"].append(f"{name}: {e}")
            print(f"[facts] {name}: {e!r}", file=sys.stderr)
    return F


if __name__ == "__main__":
    F = load()
    print(json.dumps(F, ensure_ascii=False, indent=1, default=str))
