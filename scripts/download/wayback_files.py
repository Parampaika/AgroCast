"""Скачивание файлов по префиксу исходного URL из Wayback Machine.
uv run python -I scripts/download/wayback_files.py <папка в data/raw> <cdx-префикс URL> [regex имени]
Пример (ВСХП-2016): wayback_files.py rosstat/vshp2016 gks.ru/free_doc/new_site/business/sx/vsxp2016/ "\\.(pdf|xlsx?|zip|rar)$"

Часть снимков Wayback обрезана (например, ровно 1 МБ), поэтому для каждого файла перебираются все снимки
со статусом 200 от новых к старым, пока не найдётся целый: у PDF в конце должен быть %%EOF, у zip/rar/xlsx —
корректная сигнатура и размер больше 1 МБ или не кратный 2^20. Неполные файлы сохраняются как *.partial.
В папке пишется files.tsv: имя, исходный URL, снимок, статус (ok / partial / failed).
"""
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import requests

ROOT = Path(__file__).resolve().parents[2]
folder, prefix = sys.argv[1], sys.argv[2]
pat = re.compile(sys.argv[3] if len(sys.argv) > 3 else r"\.(pdf|xlsx?|docx?|zip|rar|csv)$", re.I)
OUT = ROOT / "data" / "raw" / folder
OUT.mkdir(parents=True, exist_ok=True)


def complete(name, b):
    if not b:
        return False
    if name.lower().endswith(".pdf"):
        return b"%%EOF" in b[-2048:]
    return len(b) % (1 << 20) != 0  # обрезанные снимки обычно ровно N МБ


for attempt in range(6):
    try:
        cdx = requests.get("https://web.archive.org/cdx/search/cdx", timeout=300, params={
            "url": prefix, "matchType": "prefix", "output": "json", "filter": "statuscode:200", "limit": 20000}).json()
        break
    except Exception as e:
        print("cdx retry", repr(e)[:100], flush=True)
        time.sleep(60)
if not cdx:
    print("no captures"); sys.exit(0)
hdr, rows = cdx[0], cdx[1:]
caps = {}
for r in rows:
    d = dict(zip(hdr, r))
    name = unquote(d["original"].split("?")[0].rsplit("/", 1)[-1])
    if pat.search(name):
        caps.setdefault(name, []).append(d)
log = []
for name, lst in sorted(caps.items()):
    fn = OUT / name
    status, used = ("ok", "cached") if fn.exists() else ("failed", "")
    best = b""
    if not fn.exists():
        for d in sorted(lst, key=lambda x: x["timestamp"], reverse=True)[:6]:
            try:
                r = requests.get(f"https://web.archive.org/web/{d['timestamp']}id_/{d['original']}", timeout=900)
            except requests.RequestException as e:
                print(name, repr(e)[:100], flush=True)
                time.sleep(20)
                continue
            if r.ok and complete(name, r.content):
                fn.write_bytes(r.content)
                status, used = "ok", d["timestamp"]
                break
            if r.ok and len(r.content) > len(best):
                best, used = r.content, d["timestamp"]
            time.sleep(3)
        if status != "ok" and best:
            (OUT / (name + ".partial")).write_bytes(best)
            status = "partial"
        print(name, status, used, flush=True)
    log.append((name, lst[0]["original"], used, status))
(OUT / "files.tsv").write_text("\n".join("\t".join(x) for x in log), encoding="utf-8")
print(sum(x[3] == "ok" for x in log), "ok of", len(log))
