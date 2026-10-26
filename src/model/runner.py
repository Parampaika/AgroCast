"""Параллельный запуск конфигураций с дозаписью результатов и продолжением с места остановки.

Каждая оценённая конфигурация сразу дописывается строкой (по культуре) в CSV результатов,
прогнозы — в `preds/<cfg_id>.parquet`. Конфигурации, которые уже есть в CSV (включая
упавшие), повторно не считаются. Ошибка конфигурации пишется в лог и в CSV (status=error).
"""
from __future__ import annotations

import json
import logging
import os
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from model import cv

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "data" / "model"

COLS = ["stage", "status", "cfg_id", "crop", "date", "trend", "target", "feats", "model", "params",
        "sample", "norm", "eval_crop", "n", "mae", "mape", "wmape", "bias_pct", "gain_pct",
        "mae_best_bl", "mae_bl_lin10", "mae_bl_mean5", "mae_bl_lag1", "dev_mae", "dev_gain_pct",
        "late_mae", "late_gain_pct", "cov80", "width80_pct", "seconds", "error", "mae_by_year",
        "finished_at"]


def setup_log(path: Path) -> logging.Logger:
    log = logging.getLogger("sweep")
    if not log.handlers:
        log.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
        for h in (logging.FileHandler(path, encoding="utf-8"), logging.StreamHandler()):
            h.setFormatter(fmt)
            log.addHandler(h)
    return log


def _init_worker():
    os.environ.setdefault("OMP_NUM_THREADS", "1")


def evaluate(cfg_dict: dict, preds_dir: str) -> list[dict]:
    """Работа одного процесса: прогнать конфигурацию, сохранить прогнозы, вернуть метрики."""
    t0 = time.time()
    cfg = cv.Config(**cfg_dict)
    try:
        p = cv.run_config(cfg)
        p.to_parquet(Path(preds_dir) / f"{cfg.id}.parquet", index=False)
        rows = cv.summarize(cfg, p)
        for r in rows:
            r["status"] = "ok"
    except Exception as e:  # noqa: BLE001 — одна конфигурация не должна валить прогон
        rows = [{**cfg.as_dict(), "eval_crop": cfg.crop, "status": "error",
                 "error": f"{type(e).__name__}: {e} | {traceback.format_exc(limit=3)[-600:]}"}]
    for r in rows:
        r["seconds"] = round(time.time() - t0, 2)
    return rows


class Runner:
    def __init__(self, results: Path, n_jobs: int, log: logging.Logger):
        self.results = results
        self.preds_dir = results.parent / "preds"
        self.preds_dir.mkdir(parents=True, exist_ok=True)
        self.n_jobs = n_jobs
        self.log = log

    def load(self) -> pd.DataFrame:
        if not self.results.exists():
            return pd.DataFrame(columns=COLS)
        return pd.read_csv(self.results, dtype={"cfg_id": str, "params": str, "error": str})

    def _append(self, rows: list[dict], stage: str):
        df = pd.DataFrame(rows)
        df["stage"] = stage
        df["finished_at"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        df = df.reindex(columns=COLS)
        df.to_csv(self.results, mode="a", header=not self.results.exists(), index=False)

    def run(self, cfgs: list[cv.Config], stage: str, deadline: float | None = None) -> pd.DataFrame:
        """Посчитать недостающие конфигурации; вернуть строки результатов по всем cfgs."""
        done = set(self.load().cfg_id.astype(str))
        uniq = {c.id: c for c in cfgs}
        todo = [c for i, c in uniq.items() if i not in done]
        self.log.info("[%s] конфигураций %d, уже посчитано %d, осталось %d",
                      stage, len(uniq), len(uniq) - len(todo), len(todo))
        if todo:
            self._run(todo, stage, deadline)
        res = self.load()
        return res[res.cfg_id.isin(uniq) & (res.status == "ok")]

    def _run(self, todo: list[cv.Config], stage: str, deadline: float | None):
        n_ok = n_err = 0
        t0 = time.time()
        pending = list(todo)
        with ProcessPoolExecutor(self.n_jobs, initializer=_init_worker) as ex:
            running = {}
            while pending or running:
                late = deadline is not None and time.time() > deadline
                while pending and len(running) < 2 * self.n_jobs and not late:
                    c = pending.pop(0)
                    running[ex.submit(evaluate, asdict(c), str(self.preds_dir))] = c
                if late and pending:
                    self.log.warning("[%s] лимит времени: не запущено %d конфигураций", stage,
                                     len(pending))
                    pending = []
                if not running:
                    break
                fin, _ = wait(list(running), timeout=30, return_when=FIRST_COMPLETED)
                for fu in fin:
                    c = running.pop(fu)
                    try:
                        rows = fu.result()
                    except Exception as e:  # noqa: BLE001 — упал сам процесс
                        rows = [{**c.as_dict(), "eval_crop": c.crop, "status": "error",
                                 "error": f"worker: {type(e).__name__}: {e}"}]
                    self._append(rows, stage)
                    if rows[0].get("status") == "ok":
                        n_ok += 1
                    else:
                        n_err += 1
                        self.log.error("[%s] %s %s: %s", stage, c.id, json.dumps(asdict(c)),
                                       rows[0].get("error", "")[:400])
                    k = n_ok + n_err
                    if k % 25 == 0 or k == len(todo):
                        el = time.time() - t0
                        self.log.info("[%s] %d/%d готово (ошибок %d), %.0f с, осталось ~%.0f мин",
                                      stage, k, len(todo), n_err, el,
                                      el / k * (len(todo) - k) / 60)
