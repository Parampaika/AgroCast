"""NASA POWER daily point API (без ключа) для точек из data/raw/geo/points.csv, 2000-01-01 — вчера.
Сырой CSV ответа -> data/raw/nasa_power/<point_id>.csv. Уже скачанные пропускаются.
Запуск: uv run python -I scripts/download/nasa_power.py
"""
import csv
import datetime as dt
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "nasa_power"
OUT.mkdir(parents=True, exist_ok=True)
URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = ["T2M", "T2M_MAX", "T2M_MIN", "T2MDEW", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN", "CLRSKY_SFC_SW_DWN", "RH2M",
          "QV2M", "WS2M", "WS2M_MAX", "PS", "GWETTOP", "GWETROOT", "GWETPROF", "TS", "EVLAND", "SNODP", "FROST_DAYS",
          "ALLSKY_SFC_PAR_TOT"]
END = (dt.date.today() - dt.timedelta(days=1)).strftime("%Y%m%d")


def one(p):
    fn = OUT / f"{p['point_id']}.csv"
    if fn.exists():
        return
    q = {"parameters": ",".join(PARAMS), "community": "AG", "longitude": p["lon"], "latitude": p["lat"],
         "start": "20000101", "end": END, "format": "CSV", "time-standard": "LST"}
    for attempt in range(5):
        try:
            r = requests.get(URL, params=q, timeout=600)
            if r.status_code == 200 and "-END HEADER-" in r.text:
                fn.write_text(r.text, encoding="utf-8")
                print(p["point_id"], "ok", flush=True)
                return
            print(p["point_id"], r.status_code, r.text[:200].replace("\n", " "), flush=True)
            if r.status_code == 422:  # невалидный параметр — не повторяем
                return
        except requests.RequestException as e:
            print(p["point_id"], repr(e)[:150], flush=True)
        time.sleep(30 * (attempt + 1))


pts = list(csv.DictReader((ROOT / "data" / "raw" / "geo" / "points.csv").open(encoding="utf-8")))
pts.sort(key=lambda p: int(p["rank_in_region"]))
with ThreadPoolExecutor(3) as ex:
    list(ex.map(one, pts))
