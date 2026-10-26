"""Сборка чистого слоя данных data/clean/.

Запуск всех шагов:
    uv run python -I -X utf8 src/preprocess/build_all.py
Отдельные шаги (порядок зависимостей соблюдается автоматически только при запуске всех):
    uv run python -I -X utf8 src/preprocess/build_all.py regions crops yield
Параметры:
    --train-end-year 2021   последний год «обучения»: нормы климата считаются только по годам ≤ него
    --category 1            категория хозяйств для model_table (1 — все, 2 — СХО, 8 — КФХ и ИП, 17 — население)
    --price-base-year 2021  базовый год реальных цен
    --crops 1010400,3080000 фильтр культур для model_table (по умолчанию — все)
    --force                 пересобрать кэш (разбор ЕМИСС, суточная погода, точки NDVI)

Тяжёлые шаги — weather (первый запуск ~10–20 мин: почасовые ERA5 → сутки) и ndvi (чтение ~25 тыс. CSV).
Промежуточные файлы лежат в data/clean/_cache/ и переиспользуются.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import importlib  # noqa: E402

from preprocess.common import Config, ensure_dirs, log, write_stats  # noqa: E402

STEPS = {  # шаг → модуль src/preprocess/<модуль>.py с функцией build(cfg)
    "regions": "regions", "crops": "crops", "yield": "yield_panel", "weather": "weather", "soil": "soil",
    "ndvi": "ndvi", "calendar": "calendar", "prices": "prices", "economics": "economics",
    "model_table": "model_table",
}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("steps", nargs="*", help=f"шаги из {list(STEPS)} (по умолчанию все)")
    ap.add_argument("--train-end-year", type=int, default=2021)
    ap.add_argument("--category", default="1")
    ap.add_argument("--price-base-year", type=int, default=2021)
    ap.add_argument("--crops", default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    cfg = Config(train_end_year=a.train_end_year, category=a.category, price_base_year=a.price_base_year,
                 force=a.force, crops=a.crops.split(",") if a.crops else None)
    ensure_dirs()
    steps = a.steps or list(STEPS)
    bad = [s for s in steps if s not in STEPS]
    if bad:
        ap.error(f"неизвестные шаги {bad}; есть {list(STEPS)}")
    for s in steps:
        t0 = time.time()
        log(f"=== {s}")
        importlib.import_module(f"preprocess.{STEPS[s]}").build(cfg)
        cfg.stats.setdefault("_timing", {})[s] = round(time.time() - t0, 1)
    write_stats("_build_" + "_".join(steps) if a.steps else "_build_all",
                {"params": {"train_end_year": cfg.train_end_year, "category": cfg.category,
                            "price_base_year": cfg.price_base_year, "crops": cfg.crops}, **cfg.stats})
    log("готово:", ", ".join(steps))


if __name__ == "__main__":
    main()
