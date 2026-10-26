"""Новости Минсельхоза России (mcx.gov.ru/press-service/news/) за 2025–2026: ход сева и уборки, урожай.
Сохраняются сырые страницы ленты (?PAGEN_1=N) и статьи, у которых slug похож на тему урожая
(уборка, урожай, зерно, сбор, сев, озимые, яровые, подсолнечник, свёкла, картофель, соя, масличные, намолот).
-> data/raw/mcx_news/list/page_NNN.html, data/raw/mcx_news/articles/<slug>.html, articles.tsv (slug, url, дата в ленте)
Запуск: uv run python -I scripts/download/mcx_news.py [число_страниц_ленты=50]
"""
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "mcx_news"
(OUT / "list").mkdir(parents=True, exist_ok=True)
(OUT / "articles").mkdir(parents=True, exist_ok=True)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 50
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (research data download)"
TOPIC = re.compile(r"ubork|urozha|zern|sbor|posev|sev-|-sev|ozim|yarov|obmolot|podsolnech|svekl|kartof|soi|soy|maslichn|"
                   r"pshenits|yachmen|kukuruz|rapsa|raps|gibel|zasukh|chs-|chrezvychayn|zamorozk", re.I)


def get(url, fn):
    if fn.exists():
        return fn.read_text(encoding="utf-8")
    for attempt in range(4):
        try:
            r = S.get(url, timeout=120)
            if r.ok:
                fn.write_text(r.text, encoding="utf-8")
                time.sleep(1)
                return r.text
        except requests.RequestException:
            pass
        time.sleep(10 * (attempt + 1))
    return ""


found = {}
for p in range(1, N + 1):
    html = get(f"https://mcx.gov.ru/press-service/news/?PAGEN_1={p}", OUT / "list" / f"page_{p:03d}.html")
    for m in re.finditer(r'href="(/press-service/news/([^"/]+)/)"', html):
        found.setdefault(m.group(2), m.group(1))
rows = []
for slug, url in sorted(found.items()):
    if TOPIC.search(slug):
        get("https://mcx.gov.ru" + url, OUT / "articles" / f"{slug[:150]}.html")
        rows.append((slug, "https://mcx.gov.ru" + url))
(OUT / "articles.tsv").write_text("\n".join("\t".join(r) for r in rows), encoding="utf-8")
print(len(found), "news in list,", len(rows), "topic articles saved")
