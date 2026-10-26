"""Файлы раздела Росстата «Сельское хозяйство» (rosstat.gov.ru/enterprise_economy) через Wayback Machine.
rosstat.gov.ru не открывается из текущей сети (прокси/VPN с зарубежным IP), поэтому берём последний архивный
снимок страницы и все приложенные файлы (xls/xlsx/pdf/doc/rar/htm) в ближайших к нему снимках web.archive.org.
-> data/raw/rosstat/enterprise_economy/  (+ page.html, files.tsv: имя, исходный URL, URL снимка, статус)
Запуск: uv run python -I scripts/download/rosstat_wayback.py [другая страница rosstat, напр. folder/...]
"""
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import requests

ROOT = Path(__file__).resolve().parents[2]
PAGE = sys.argv[1] if len(sys.argv) > 1 else "enterprise_economy"
OUT = ROOT / "data" / "raw" / "rosstat" / PAGE.replace("/", "_")
OUT.mkdir(parents=True, exist_ok=True)
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (research data download)"
EXT = r"\.(xlsx|xls|pdf|docx|doc|rar|zip|htm|html|csv)$"


def wb(url, ts="2026"):
    for attempt in range(4):
        try:
            r = S.get(f"https://web.archive.org/web/{ts}id_/{url}", timeout=300)
            if r.status_code in (200, 404):
                return r
        except requests.RequestException as e:
            print("  retry", repr(e)[:100], flush=True)
        time.sleep(10 * (attempt + 1))
    return None


page = OUT / "page.html"
if not page.exists():
    r = wb(f"https://rosstat.gov.ru/{PAGE}")
    page.write_bytes(r.content)
html = page.read_text(encoding="utf-8", errors="replace")
links = sorted(set(re.findall(r'href="(/storage/[^"]+)"', html)))
links = [l for l in links if re.search(EXT, l, re.I) and not l.endswith(".png")]
log = []
for l in links:
    name = unquote(l.rsplit("/", 1)[1])
    fn = OUT / name
    if fn.exists():
        log.append((name, l, "", "cached"))
        continue
    r = wb("https://rosstat.gov.ru" + l)
    if r is None or r.status_code != 200 or (b"<html" in r.content[:500].lower() and not re.search(r"\.html?$", name)):
        print(name, "NOT ARCHIVED", flush=True)
        log.append((name, l, "", "not_archived"))
        continue
    fn.write_bytes(r.content)
    print(name, len(r.content) // 1024, "KB", flush=True)
    log.append((name, l, r.url, "ok"))
    time.sleep(2)
(OUT / "files.tsv").write_text("\n".join("\t".join(x) for x in log), encoding="utf-8")
print(sum(x[3] in ("ok", "cached") for x in log), "of", len(log))
