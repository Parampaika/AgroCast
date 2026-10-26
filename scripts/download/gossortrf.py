"""Госреестр селекционных достижений, допущенных к использованию, том 1 «Сорта растений» (gossortrf.ru).
Выгрузки в таблицу на сайте нет, поэтому качаем все страницы списка (~1400 стр. по ~20 сортов):
культура, код, название, год включения, регионы допуска (номера зон 1–12), параметры.
-> data/raw/gossortrf/tom1/page_NNNN.html; плюс реестр оригинаторов (xlsx) и страница бюллетеней.
Парсинг: scripts/parse/gossortrf.py. Запуск: uv run python -I scripts/download/gossortrf.py
"""
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "gossortrf"
(OUT / "tom1").mkdir(parents=True, exist_ok=True)
BASE = "https://gossortrf.ru/registry/gosudarstvennyy-reestr-selektsionnykh-dostizheniy-dopushchennykh-k-ispolzovaniyu-tom-1-sorta-rasteni/"
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (research data download)"


def get(url, fn, binary=False):
    if fn.exists():
        return fn.read_bytes()
    for attempt in range(5):
        try:
            r = S.get(url, timeout=120)
            if r.ok:
                fn.write_bytes(r.content)
                return r.content
        except requests.RequestException:
            pass
        time.sleep(10 * (attempt + 1))
    print("FAILED", url, flush=True)
    return b""


get("https://gossortrf.ru/upload/out/Реестр оригинаторов - Основной 05.05.2025.xlsx", OUT / "reestr_originatorov_2025-05-05.xlsx")
get("https://gossortrf.ru/publication/byulleteni.php", OUT / "byulleteni_page.html")
first = get(BASE, OUT / "tom1" / "page_0001.html").decode("utf-8", "replace")
last = max(int(x) for x in re.findall(r"PAGEN_1=(\d+)", first))
print("pages:", last, flush=True)
for p in range(2, last + 1):
    fn = OUT / "tom1" / f"page_{p:04d}.html"
    if fn.exists():
        continue
    get(f"{BASE}?PAGEN_1={p}", fn)
    if p % 100 == 0:
        print(p, flush=True)
    time.sleep(1)
print("done")
