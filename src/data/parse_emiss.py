"""Разбор выгрузок ЕМИСС (SDMX-ML Generic) в tidy parquet.

Использование:
    uv run python -I src/data/parse_emiss.py [id ...]      # без аргументов — ключевые показатели

Вход:  data/raw/emiss/<id>/data.xml или data_<год>.xml (если полная выгрузка не прошла).
Выход: data/processed/emiss/<id>.parquet с колонками
    indicator_id, okato, region, region_level, fo, year, crop_code, crop,
    farm_category_code, farm_category, unit, period, value [, value_t_ha] [, прочие измерения]

region_level: rf / rf_part (РФ без Крыма, без новых субъектов и т.п.) / fo / subject / subject_part
(«без АО»: Архангельская без НАО, Тюменская без ХМАО и ЯНАО) / other.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
from lxml import etree

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "emiss"
OUT = ROOT / "data" / "processed" / "emiss"
REGIONS = ROOT / "data" / "raw" / "geo" / "regions.csv"

KEY_IDS = ["31533", "31328", "30950", "33784", "34022", "31454", "57693", "30964",
           "33919", "37662", "33978", "34165"]

NS_S = "{http://www.SDMX.org/resources/SDMXML/schemas/v1_0/structure}"
NS_G = "{http://www.SDMX.org/resources/SDMXML/schemas/v1_0/generic}"
NS_M = "{http://www.SDMX.org/resources/SDMXML/schemas/v1_0/message}"

# Известные измерения → «говорящие» имена колонок
DIM_NAMES = {"s_OKATO": "okato", "s_kultur": "crop", "s_kategor": "farm_category"}

FO_RE = re.compile(r"федеральный округ", re.I)


def data_files(ind: str) -> list[Path]:
    d = RAW / ind
    full = d / "data.xml"
    if full.exists():
        return [full]
    return sorted(d.glob("data_*.xml"))


def is_complete(path: Path) -> bool:
    """Файл дописан до конца (последний тег </GenericData>)."""
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 200))
        return b"</GenericData>" in f.read()


def read_codelists(path: Path) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """Справочники code → описание и шапка показателя (имя, единица)."""
    lists: dict[str, dict[str, str]] = {}
    meta: dict[str, str] = {}
    for ev, el in etree.iterparse(str(path), events=("end",)):
        tag = el.tag
        if tag == NS_S + "CodeList":
            codes = {}
            for c in el.iter(NS_S + "Code"):
                desc = c.find(NS_S + "Description")
                codes[c.get("value")] = (desc.text or "").strip() if desc is not None else ""
            lists[el.get("id")] = codes
            el.clear()
        elif tag == NS_M + "Indicator" or tag.endswith("}Indicator"):
            meta["name"] = el.get("name", "")
            u = el.find(".//" + NS_M + "Unit")
            if u is None:
                u = next((x for x in el.iter() if x.tag.endswith("Unit")), None)
            meta["unit_header"] = u.get("value", "") if u is not None else ""
        elif tag == NS_M + "DataSet" or tag.endswith("}DataSet"):
            break
        elif tag.endswith("}Series"):
            break
    return lists, meta


def iter_obs(path: Path):
    """Потоково отдаёт словари {концепт: код, ..., _time, _value} по каждому наблюдению."""
    ctx = etree.iterparse(str(path), events=("end",), tag=NS_G + "Series")
    for _, s in ctx:
        rec: dict[str, str] = {}
        key = s.find(NS_G + "SeriesKey")
        if key is not None:
            for v in key:
                rec[v.get("concept")] = v.get("value")
        att = s.find(NS_G + "Attributes")
        if att is not None:
            for v in att:
                rec["@" + v.get("concept")] = v.get("value")
        for o in s.iter(NS_G + "Obs"):
            t = o.find(NS_G + "Time")
            v = o.find(NS_G + "ObsValue")
            r = dict(rec)
            r["_time"] = t.text if t is not None else None
            r["_value"] = v.get("value") if v is not None else None
            yield r
        s.clear()
        while s.getprevious() is not None:
            del s.getparent()[0]


def region_level(code: str, name: str) -> str:
    if code is None:
        return "other"
    if code == "643":
        return "rf"
    if code.startswith("643"):
        return "rf_part"
    if FO_RE.search(name or ""):
        return "fo"
    if re.fullmatch(r"\d{11}", code):
        if code[2:5] == "000":
            return "subject"
        if code[2:5] == "001":
            return "subject_part"  # «без АО»
        return "subject_part"
    return "other"


def to_float(s: str | None) -> float:
    if s is None:
        return float("nan")
    s = s.replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def parse_indicator(ind: str) -> pd.DataFrame | None:
    files = data_files(ind)
    if not files:
        print(f"[{ind}] нет data*.xml — пропуск")
        return None
    bad = [f.name for f in files if not is_complete(f)]
    files = [f for f in files if f.name not in bad]
    if bad:
        print(f"[{ind}] недокачаны, пропущены: {bad}")
    if not files:
        return None

    frames = []
    codelists: dict[str, dict[str, str]] = {}
    meta: dict[str, str] = {}
    for f in files:
        cl, m = read_codelists(f)
        for k, v in cl.items():
            codelists.setdefault(k, {}).update(v)
        meta = meta or m
        rows = list(iter_obs(f))
        if rows:
            frames.append(pd.DataFrame(rows))
    if not frames:
        print(f"[{ind}] наблюдений нет")
        return None
    raw = pd.concat(frames, ignore_index=True)

    dims = [c for c in raw.columns if not c.startswith(("@", "_"))]
    df = pd.DataFrame(index=raw.index)
    df["indicator_id"] = int(ind)
    for d in dims:
        name = DIM_NAMES.get(d, d)
        codes = raw[d]
        labels = codes.map(codelists.get(d, {}))
        if name == "okato":
            df["okato"] = codes
            df["region"] = labels
        else:
            df[f"{name}_code"] = codes
            df[name] = labels
    df["year"] = pd.to_numeric(raw["_time"], errors="coerce").astype("Int64")
    df["unit"] = raw.get("@EI", meta.get("unit_header"))
    df["period"] = raw.get("@PERIOD")
    for c in raw.columns:
        if c.startswith("@") and c not in ("@EI", "@PERIOD"):
            df["attr_" + c[1:]] = raw[c]
    df["value_raw"] = raw["_value"]
    df["value"] = raw["_value"].map(to_float)
    # 999999999 — маркер конфиденциальных данных (в основном 2018–2021): не число, а «скрыто»
    df["confidential"] = df["value"] == 999999999
    df.loc[df["confidential"], "value"] = float("nan")

    if "okato" in df:
        df["region_level"] = [region_level(c, n) for c, n in zip(df["okato"], df["region"])]
        reg = pd.read_csv(REGIONS, dtype={"okato": str})
        fo_map = dict(zip(reg["okato"], reg["fo"]))
        # Тюмень в справочнике — «без АО» (71001...), а коду «с АО» ФО тот же
        for c in list(fo_map):
            fo_map.setdefault(c[:2] + "000000000", fo_map[c])
            fo_map.setdefault(c[:2] + "001000000", fo_map[c])
        df["fo"] = df["okato"].map(fo_map)

    # Коды вида «w2:p_kultur:3100009» — копия того же ряда из второй версии справочника
    # (в 31533 значения совпадают с обычным кодом до знака). Сводим к базовому коду.
    for c in [c for c in df.columns if c.endswith("_code")]:
        alt = df[c].astype(str).str.match(r"^w\d+:")
        if alt.any():
            df[c] = df[c].astype(str).str.replace(r"^w\d+:[^:]+:", "", regex=True)
            df["alt_codelist"] = alt
    if "alt_codelist" in df:
        df = df.sort_values("alt_codelist", kind="stable")

    # Дубли: одинаковый ключ и год. Точные копии убираем; разные значения — помечаем.
    key = [c for c in df.columns if c not in ("value", "value_raw", "region", "crop", "farm_category", "alt_codelist")
           and not c.startswith("attr_")]
    n0 = len(df)
    df = df.drop_duplicates(subset=key + ["value_raw"])
    dup = df.duplicated(subset=key, keep=False)
    df["dup_conflict"] = dup
    print(f"[{ind}] {meta.get('name','')[:70]}: {n0} наблюдений, точных дублей {n0-len(df)}, "
          f"конфликтных {int(dup.sum())}")
    df = df.drop(columns=["value_raw"])

    if ind == "31533" or (df["unit"].astype(str).str.contains("центнер").any()):
        mask = df["unit"].astype(str).str.contains("центнер.*гектар", regex=True)
        df["value_t_ha"] = df["value"].where(mask) / 10
    df.attrs["name"] = meta.get("name", "")
    return df


def main(ids: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    names = {}
    for ind in ids:
        df = parse_indicator(ind)
        if df is None:
            continue
        df.to_parquet(OUT / f"{ind}.parquet", index=False)
        names[ind] = df.attrs.get("name", "")
    idx = OUT / "_indicators.csv"
    old = pd.read_csv(idx, dtype=str) if idx.exists() else pd.DataFrame(columns=["indicator_id", "name"])
    new = pd.DataFrame({"indicator_id": list(names), "name": list(names.values())})
    pd.concat([old[~old.indicator_id.isin(new.indicator_id)], new]).sort_values("indicator_id") \
        .to_csv(idx, index=False)


if __name__ == "__main__":
    main(sys.argv[1:] or KEY_IDS)
