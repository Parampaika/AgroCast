"""SDMX-ML (Generic) ЕМИСС -> длинная таблица data/interim/emiss/<id>.parquet.
Колонки: по одной на измерение SeriesKey (код) + <измерение>_name (расшифровка из CodeLists), атрибуты, time, value.
Без чистки: значение как есть (строка) + value_num (запятая -> точка).
Запуск: uv run python -I scripts/parse/emiss_sdmx.py [id ...]   (без аргументов — все скачанные)
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "emiss"
OUT = ROOT / "data" / "interim" / "emiss"
OUT.mkdir(parents=True, exist_ok=True)
NS = {"g": "http://www.SDMX.org/resources/SDMXML/schemas/v1_0/generic",
      "s": "http://www.SDMX.org/resources/SDMXML/schemas/v1_0/structure"}


def tag(t):
    return t.rsplit("}", 1)[-1]


def parse(path):
    codes, rows = {}, []
    cur_list = None
    key, attrs = {}, {}
    for ev, el in ET.iterparse(path, events=("start", "end")):
        t = tag(el.tag)
        if ev == "start":
            if t == "CodeList":
                cur_list = el.get("id")
                codes[cur_list] = {}
            elif t == "Series":
                key, attrs = {}, {}
            continue
        if t == "Code" and cur_list:
            desc = next((c.text for c in el if tag(c.tag) == "Description"), None)
            codes[cur_list][el.get("value")] = desc
        elif t == "CodeList":
            cur_list = None
        elif t == "Value" and el.get("concept"):
            pass
        elif t == "SeriesKey":
            key = {v.get("concept"): v.get("value") for v in el}
        elif t == "Attributes":
            attrs = {v.get("concept"): v.get("value") for v in el}
        elif t == "Obs":
            time_, val = None, None
            for c in el:
                if tag(c.tag) == "Time":
                    time_ = c.text
                elif tag(c.tag) == "ObsValue":
                    val = c.get("value")
            rows.append({**key, **attrs, "time": time_, "value": val})
        elif t == "Series":
            el.clear()
    df = pd.DataFrame(rows)
    for col in list(key):
        if col in codes and col in df:
            df[col + "_name"] = df[col].map(codes[col])
    df["value_num"] = pd.to_numeric(df["value"].str.replace(",", ".", regex=False).str.replace(" ", ""), errors="coerce")
    return df


if __name__ == "__main__":
    ids = sys.argv[1:] or sorted(p.name for p in RAW.iterdir() if p.is_dir() and not p.name.startswith("_"))
    for i in ids:
        files = sorted((RAW / i).glob("data*.xml"))
        if not files:
            continue
        out = OUT / f"{i}.parquet"
        if out.exists() and out.stat().st_mtime > max(f.stat().st_mtime for f in files):
            continue
        try:
            df = pd.concat([parse(f) for f in files], ignore_index=True)
            df.to_parquet(out)
            print(i, len(df), "rows", flush=True)
        except Exception as e:
            print(i, "FAILED", repr(e)[:200], flush=True)
