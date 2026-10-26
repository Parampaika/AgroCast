"""Ночной перебор моделей прогноза урожайности.

    uv run python -I -X utf8 src/model/sweep.py                 # полный прогон
    uv run python -I -X utf8 src/model/sweep.py --smoke         # пробный: одна культура, мини-сетка
    uv run python -I -X utf8 src/model/sweep.py --stages report # только перестроить отчёт

Этапы (у каждого лимит времени; не уложился — берутся лучшие на текущий момент):
1. coarse    — Ridge + LightGBM, конец сезона: тренд × цель × признаки по культурам (+ общая модель);
2. models    — топ-3 сочетания на культуру × 8 моделей, Optuna по годам 2012–2018;
3. dates     — победители на датах 1 мая, 1 июня, 1 июля, 1 августа;
4. ensembles — среднее и стекинг лучших, калибровка конформного интервала;
5. report    — reports/sweep.md и графики reports/figures/sweep/.

Результаты дописываются в data/model/sweep_results.csv сразу после каждой конфигурации,
перезапуск продолжает с места остановки. Лог — data/model/sweep.log.
"""
from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait  # noqa: E402
from dataclasses import asdict, replace  # noqa: E402
from functools import partial  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from model import cv  # noqa: E402
from model import data as D  # noqa: E402
from model.models import MODELS  # noqa: E402
from model.runner import MODEL_DIR, Runner, evaluate, setup_log  # noqa: E402

STAGES = ["coarse", "models", "dates", "ensembles", "report"]

FULL = {
    "crops": list(D.CROP_NAME),
    "trends": ["lin_all", "lin15", "ts15", "lin10", "ts10", "mean5"],  # lag1 — заведомо плохо
    "targets": ["ratio", "diff", "log"],
    "feats": ["F1", "F2", "F3", "F4", "F5", "F2r"],
    "coarse_models": ["ridge", "lgbm"],
    "pooled_models": ["lgbm"],          # общая модель помогает только деревьям
    "pooled_targets": ["ratio", "log"],  # diff смешивает масштабы (свёкла — десятки т/га)
    "sample": "no_mismatch",
    "top_combos": 3,
    "models": MODELS,
    "pooled_tune_models": ["lgbm", "xgb", "hgb"],  # CatBoost на общей выборке слишком медленный
    "trials": 30,
    "top_dates": 4,
    "date_tune_models": ["ridge", "lgbm"],
    "date_trials": 25,
    "dates": ["05-01", "06-01", "07-01", "08-01"],
    "budget_min": {"coarse": 45, "models": 240, "dates": 90, "ensembles": 30},
    "n_jobs": 12,
}
SMOKE = {
    **FULL,
    "crops": ["winter_wheat"],
    "trends": ["lin_all", "mean5"],
    "targets": ["ratio", "diff"],
    "feats": ["F2", "F5"],
    "pooled_models": [],
    "top_combos": 1,
    "models": ["ridge", "lgbm", "cat"],
    "trials": 3,
    "top_dates": 2,
    "date_trials": 3,
    "dates": ["05-01", "07-01"],
    "budget_min": {"coarse": 5, "models": 6, "dates": 5, "ensembles": 3},
}


# ---------------------------------------------------------------- этап 1
def stage_coarse(G, runner, deadline):
    C = partial(cv.Config, sample=G["sample"])
    cfgs = [C(c, trend=t, target=g, feats=f, model=m)
            for c in G["crops"] for t in G["trends"] for g in G["targets"]
            for f in G["feats"] for m in G["coarse_models"]]
    cfgs += [C(c, trend=t, model="trend") for c in G["crops"] for t in G["trends"]]
    cfgs += [C("pooled", trend=t, target=g, feats=f, model=m)
             for t in G["trends"] for g in G["pooled_targets"] for f in G["feats"]
             for m in G["pooled_models"]]
    # дорогие общие модели — первыми
    cfgs.sort(key=lambda c: c.crop != "pooled")
    return runner.run(cfgs, "coarse", deadline)


def top_combos(res: pd.DataFrame, crop: str, k: int) -> list[tuple]:
    """Лучшие сочетания (схема, тренд, цель, признаки) культуры по MAE лучшей из моделей этапа 1."""
    q = res[(res.eval_crop == crop) & (res.date == "end") & (res.model != "trend")]
    g = q.groupby(["crop", "trend", "target", "feats"]).mae.min().sort_values()
    return list(g.index[:k])


# ---------------------------------------------------------------- Optuna
def tune_study(cfg_dict: dict, trials: int, timeout: float, preds_dir: str, journal: str) -> list[dict]:
    """Optuna по годам DEV_YEARS (без разогрева), затем полный прогон лучших параметров.

    feats="*" — набор признаков тоже подбирается. У общей модели цель — средняя по культурам
    MAE / MAE бейзлайна lin10.
    """
    import optuna
    from optuna.storages import JournalStorage
    from optuna.storages.journal import JournalFileBackend, JournalFileOpenLock

    from model.models import suggest
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    base = cv.Config(**cfg_dict)
    # блокировка через symlink на Windows требует прав администратора
    storage = JournalStorage(JournalFileBackend(journal, lock_obj=JournalFileOpenLock(journal)))
    study = optuna.create_study(study_name=base.id, storage=storage, load_if_exists=True,
                                direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=0, n_startup_trials=8))

    def obj(trial):
        params = suggest(trial, base.model)
        fs = trial.suggest_categorical("feats", list(cv.FEATSETS)) if base.feats == "*" else base.feats
        c = replace(base, feats=fs, params=json.dumps(params, sort_keys=True))
        p = cv.run_config(c, years=cv.DEV_YEARS)
        if base.crop == "pooled":
            return float(((p.yhat - p.y).abs().groupby(p.crop).mean()
                          / (p.bl_lin10 - p.y).abs().groupby(p.crop).mean()).mean())
        return float((p.yhat - p.y).abs().mean())

    done = len([t for t in study.trials if t.state.is_finished()])
    t0 = time.time()
    if done < trials:
        study.optimize(obj, n_trials=trials - done, timeout=timeout, catch=(Exception,))
    bp = dict(study.best_params)
    fs = bp.pop("feats", base.feats)
    best = replace(base, feats=fs, params=json.dumps(bp, sort_keys=True))
    rows = evaluate(asdict(best), preds_dir)
    for r in rows:
        r["seconds"] = round(time.time() - t0 + r.get("seconds", 0), 1)
        r["error"] = (r.get("error") or "") + f" trials={len(study.trials)} best_dev={study.best_value:.4f}"
    return rows


def run_studies(G, runner, tasks, stage, trials, deadline, log):
    """Исследования Optuna параллельно (по одному на процесс); готовые не повторяются."""
    res = runner.load()
    done = set(res[(res.stage == stage) & (res.status == "ok")].error.dropna().astype(str).str.extract(r"base=(\w+)")[0])
    tasks = list(dict.fromkeys(tasks))
    todo = [c for c in tasks if c.id not in done]
    log.info("[%s] Optuna: исследований %d, уже готово %d", stage, len(tasks), len(tasks) - len(todo))
    if not todo:
        return
    jdir = runner.results.parent / "optuna"
    jdir.mkdir(exist_ok=True)
    # дорогие модели и общая схема — первыми, чтобы не остаться в хвосте
    order = {"cat": 0, "rf": 1, "xgb": 2, "et": 3, "lgbm": 4, "hgb": 5, "enet": 6, "ridge": 7}
    todo.sort(key=lambda c: (c.crop != "pooled", order.get(c.model, 9)))
    with ProcessPoolExecutor(G["n_jobs"]) as ex:
        running = {}
        while todo or running:
            while todo and len(running) < G["n_jobs"] and time.time() < deadline - 120:
                c = todo.pop(0)
                left = max(60.0, deadline - time.time() - 300)
                fu = ex.submit(tune_study, asdict(c), trials, min(left, 3600.0),
                               str(runner.preds_dir), str(jdir / f"{c.id}.log"))
                running[fu] = c
            if time.time() >= deadline - 120 and todo:
                log.warning("[%s] лимит времени: не начато %d исследований", stage, len(todo))
                todo = []
            if not running:
                break
            fin, _ = wait(list(running), timeout=30, return_when=FIRST_COMPLETED)
            for fu in fin:
                c = running.pop(fu)
                try:
                    rows = fu.result()
                except Exception as e:  # noqa: BLE001
                    rows = [{**c.as_dict(), "eval_crop": c.crop, "status": "error",
                             "error": f"optuna: {type(e).__name__}: {e}"}]
                    log.error("[%s] %s %s: %s", stage, c.id, c.model, e)
                for r in rows:
                    r["error"] = f"base={c.id} " + (r.get("error") or "")
                runner._append(rows, stage)
                for r in rows:
                    if r.get("status") == "ok":
                        log.info("[%s] %s→%s %s %s/%s/%s %s: MAE %.4f, выигрыш %.1f%% (%s)", stage,
                                 c.crop, r.get("eval_crop"), c.model, c.trend, c.target, r.get("feats"),
                                 c.date, r.get("mae", np.nan), r.get("gain_pct", np.nan),
                                 str(r.get("error", ""))[-34:])


# ---------------------------------------------------------------- этап 2
def stage_models(G, runner, coarse, deadline, log):
    tasks = []
    for crop in G["crops"]:
        for sch, tr, tg, fs in top_combos(coarse, crop, G["top_combos"]):
            models = G["pooled_tune_models"] if sch == "pooled" else G["models"]
            for m in models:
                tasks.append(cv.Config(sch, trend=tr, target=tg, feats=fs, model=m, sample=G["sample"]))
    tasks = list(dict.fromkeys(tasks))
    # дефолтные параметры всех моделей — дёшево и даёт опору, если Optuna не успеет
    runner.run(tasks, "models_default", time.time() + 0.25 * (deadline - time.time()))
    run_studies(G, runner, tasks, "models", G["trials"], deadline, log)


# ---------------------------------------------------------------- этап 3
def stage_dates(G, runner, deadline, log):
    res = runner.load().query("status == 'ok'")
    coarse = res[res.stage == "coarse"]
    models = res[res.stage.isin(["models", "models_default"])]
    cfgs, studies = [], []
    for crop in G["crops"]:
        q = models[models.eval_crop == crop].sort_values("mae").drop_duplicates("model")
        for r in q.head(G["top_dates"]).itertuples():
            for d in G["dates"]:
                cfgs.append(cv.Config(r.crop, date=d, trend=r.trend, target=r.target, feats=r.feats,
                                      model=r.model, params=r.params, sample=r.sample))
        # на ранних датах нужны другие признаки и регуляризация: подбираем их заново
        per_crop = [c for c in top_combos(coarse, crop, 10) if c[0] != "pooled"][:1]
        for _, tr, tg, _ in per_crop:
            for d in G["dates"] + ["end"]:
                cfgs.append(cv.Config(crop, date=d, trend=tr, model="trend", sample=G["sample"]))
                for m in G["date_tune_models"]:
                    studies.append(cv.Config(crop, date=d, trend=tr, target=tg, feats="*", model=m,
                                             sample=G["sample"]))
    runner.run(cfgs, "dates", time.time() + 0.3 * (deadline - time.time()))
    run_studies(G, runner, studies, "dates_tuned", G["date_trials"], deadline, log)


# ---------------------------------------------------------------- этап 4: ансамбли и интервалы
def _load_preds(runner, cfg_id):
    return pd.read_parquet(runner.preds_dir / f"{cfg_id}.parquet")


def stack_weights(P: np.ndarray, y: np.ndarray) -> np.ndarray:
    from scipy.optimize import nnls
    w, _ = nnls(P, y)
    return w / w.sum() if w.sum() > 0 else np.full(P.shape[1], 1 / P.shape[1])


def stage_ensembles(G, runner, deadline, log):
    res = runner.load()
    res = res[(res.status == "ok") & res.stage.isin(["coarse", "models", "models_default", "dates", "dates_tuned"])]
    res = res[res.model != "trend"]
    done = set(runner.load().cfg_id.astype(str))
    rows, calib = [], []
    for crop in G["crops"]:
        for date in ["end"] + G["dates"]:
            if time.time() > deadline:
                log.warning("[ensembles] лимит времени")
                break
            q = res[(res.eval_crop == crop) & (res.date == date)].sort_values("dev_mae")
            q = q.drop_duplicates("model")  # разнообразие: лучшая конфигурация каждой модели
            if len(q) < 2:
                continue
            ids = list(q.cfg_id)
            preds = {i: _load_preds(runner, i).query('crop == @crop') for i in ids[:6]}
            key = ["okato", "year"]
            base = preds[ids[0]].drop(columns=["yhat"])
            M = base[key].copy()
            for i, p in preds.items():
                M = M.merge(p[key + ["yhat"]].rename(columns={"yhat": i}), on=key, how="left")
            M = base.merge(M, on=key)
            for k in (2, 3, 5):
                if len(preds) < k:
                    continue
                sel = ids[:k]
                p = M.copy()
                p["yhat"] = M[sel].mean(axis=1)
                rows.append((f"ens_mean{k}", sel, p))
            # стекинг: веса года T — NNLS по прогнозам лет < T (с 2009 г.)
            sel = ids[:min(5, len(preds))]
            p = M.copy()
            p["yhat"] = np.nan
            for T in sorted(M.year.unique()):
                past = M.year < T
                cur = M.year == T
                w = (stack_weights(M.loc[past, sel].to_numpy(), M.loc[past, "y"].to_numpy())
                     if past.sum() >= 50 else np.full(len(sel), 1 / len(sel)))
                p.loc[cur, "yhat"] = M.loc[cur, sel].to_numpy() @ w
            rows.append(("ens_stack", sel, p))
            for name, sel, p in rows:
                cfg = cv.Config(crop, date=date, model=name, params=json.dumps(sel))
                if cfg.id in done:
                    continue
                p.drop(columns=[c for c in p.columns if c in ids]).to_parquet(
                    runner.preds_dir / f"{cfg.id}.parquet", index=False)
                out = cv.summarize(cfg, p.drop(columns=[c for c in p.columns if c in ids]))
                for r in out:
                    r["status"] = "ok"
                runner._append(out, "ensembles")
            rows = []
            # калибровка интервала для лучшей одиночной модели и среднего
            for cid in ids[:1]:
                p = _load_preds(runner, cid).query('crop == @crop')
                for kind in ("rel", "abs"):
                    for win in (None, 8, 5):
                        pc = cv.conformal(p, window=win, kind=kind)
                        for yrs, lab in ((cv.DEV_YEARS, "dev"), (cv.LATE_YEARS, "late"),
                                         (cv.EVAL_YEARS, "all")):
                            m = cv.metrics(pc, yrs)
                            calib.append({"crop": crop, "date": date, "cfg_id": cid, "kind": kind,
                                          "window": win or 0, "years": lab,
                                          "cov80": m.get("cov80"), "width80_pct": m.get("width80_pct")})
    pd.DataFrame(calib).to_csv(runner.results.parent / "sweep_calibration.csv", index=False)


# ---------------------------------------------------------------- main
def keep_awake():
    """Не давать Windows уснуть, пока жив процесс (запрос снимается при выходе, настройки не меняются)."""
    if sys.platform == "win32":
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


def main():
    keep_awake()
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--stages", default=",".join(STAGES))
    ap.add_argument("--out", default=None, help="папка результатов (по умолчанию data/model)")
    ap.add_argument("--finish", default=None, help="крайний срок всего прогона, 'YYYY-MM-DD HH:MM'")
    ap.add_argument("--n-jobs", type=int, default=None)
    a = ap.parse_args()
    G = dict(SMOKE if a.smoke else FULL)
    if a.n_jobs:
        G["n_jobs"] = a.n_jobs
    out = Path(a.out) if a.out else (MODEL_DIR / "smoke" if a.smoke else MODEL_DIR)
    out.mkdir(parents=True, exist_ok=True)
    log = setup_log(out / "sweep.log")
    runner = Runner(out / "sweep_results.csv", G["n_jobs"], log)
    finish = pd.Timestamp(a.finish).timestamp() if a.finish else None
    stages = a.stages.split(",")
    log.info("старт: этапы %s, культуры %s, папка %s, финиш %s", stages, G["crops"], out, a.finish)

    def dl(stage):
        d = time.time() + 60 * G["budget_min"][stage]
        return min(d, finish - 20 * 60) if finish else d

    if "coarse" in stages:
        t = time.time()
        stage_coarse(G, runner, dl("coarse"))
        log.info("[coarse] готово за %.1f мин", (time.time() - t) / 60)
    if "models" in stages:
        coarse = runner.load().query("stage == 'coarse' and status == 'ok'")
        t = time.time()
        stage_models(G, runner, coarse, dl("models"), log)
        log.info("[models] готово за %.1f мин", (time.time() - t) / 60)
    if "dates" in stages:
        t = time.time()
        stage_dates(G, runner, dl("dates"), log)
        log.info("[dates] готово за %.1f мин", (time.time() - t) / 60)
    if "ensembles" in stages:
        t = time.time()
        stage_ensembles(G, runner, dl("ensembles"), log)
        log.info("[ensembles] готово за %.1f мин", (time.time() - t) / 60)
    if "report" in stages:
        from model.report import build_report
        build_report(out, G, smoke=a.smoke)
        log.info("[report] отчёт записан")
    log.info("финиш")


if __name__ == "__main__":
    main()
