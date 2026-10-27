"""Инвентарь данных проекта: размер, число файлов и строк по слоям и источникам.

Обход `data/` медленный (десятки тысяч мелких CSV), поэтому результат кэшируется
в `report/build/data_stats.json`; пересчёт — флагом `--force` у build_report.py
или прямым запуском этого модуля.

    uv run python -I -X utf8 src/report/data_stats.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CACHE = ROOT / "report" / "build" / "data_stats.json"
LAYERS = ["raw", "interim", "processed", "clean", "model"]
CSV_MAX = 400 * 2**20  # строки считаем только в файлах до 400 МБ


def _rows_parquet(p: Path) -> int | None:
    try:
        import pyarrow.parquet as pq
        return pq.ParquetFile(p).metadata.num_rows
    except Exception:
        return None


def _rows_text(p: Path, size: int) -> int | None:
    if size > CSV_MAX:
        return None
    n = 0
    with open(p, "rb") as f:
        while chunk := f.read(1 << 22):
            n += chunk.count(b"\n")
    return max(n - 1, 0)  # без заголовка


def scan(top: Path) -> dict:
    out = {"bytes": 0, "files": 0, "rows": 0, "tabular_files": 0, "ext": {}}
    for dirpath, _, files in os.walk(top):
        if "_cache" in Path(dirpath).parts:
            continue
        for fn in files:
            p = Path(dirpath) / fn
            try:
                size = p.stat().st_size
            except OSError:
                continue
            ext = p.suffix.lower() or "-"
            out["bytes"] += size
            out["files"] += 1
            out["ext"][ext] = out["ext"].get(ext, 0) + 1
            rows = None
            if ext == ".parquet":
                rows = _rows_parquet(p)
            elif ext in (".csv", ".tsv"):
                rows = _rows_text(p, size)
            if rows is not None:
                out["rows"] += rows
                out["tabular_files"] += 1
    return out


def collect() -> dict:
    t0 = time.time()
    res = {"layers": {}, "raw_sources": {}, "clean_tables": {}}
    for layer in LAYERS:
        d = DATA / layer
        if d.exists():
            res["layers"][layer] = scan(d)
            print(layer, res["layers"][layer]["files"], "файлов", flush=True)
    for d in sorted((DATA / "raw").iterdir()):
        if d.is_dir():
            res["raw_sources"][d.name] = scan(d)
    for p in sorted((DATA / "clean").glob("*.parquet")):
        try:
            import pyarrow.parquet as pq
            md = pq.ParquetFile(p).metadata
            res["clean_tables"][p.stem] = {"rows": md.num_rows, "cols": md.num_columns,
                                           "bytes": p.stat().st_size}
        except Exception:
            pass
    cache = DATA / "clean" / "_cache"
    res["clean_cache_bytes"] = sum(f.stat().st_size for f in cache.rglob("*") if f.is_file()) if cache.exists() else 0
    res["seconds"] = round(time.time() - t0, 1)
    res["computed_at"] = time.strftime("%Y-%m-%d %H:%M")
    return res


def load(force: bool = False) -> dict:
    if CACHE.exists() and not force:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    res = collect()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


if __name__ == "__main__":
    r = load(force=True)
    print(json.dumps({k: {"GB": round(v["bytes"] / 2**30, 2), "files": v["files"], "rows": v["rows"]}
                      for k, v in r["layers"].items()}, ensure_ascii=False, indent=1))
    print("за", r["seconds"], "с", file=sys.stderr)
