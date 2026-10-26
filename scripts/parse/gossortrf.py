"""Разбор страниц списка Госреестра сортов (data/raw/gossortrf/tom1/page_*.html) -> data/interim/gossortrf/tom1.csv.
Колонки: culture, culture_group, code, name, year, regions (номера зон допуска через ';', '*' = вся РФ / без зонирования),
p1..p7 (параметры, popup-расшифровка: 1 назначение, 2 группа спелости, 3 ..., 6 направление использования, ...), url.
Запуск: uv run python -I scripts/parse/gossortrf.py
"""
import csv
import html as H
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "raw" / "gossortrf" / "tom1"
OUT = ROOT / "data" / "interim" / "gossortrf"
OUT.mkdir(parents=True, exist_ok=True)


def txt(s):
    return H.unescape(re.sub(r"<[^>]+>", " ", s)).split() and " ".join(H.unescape(re.sub(r"<[^>]+>", " ", s)).split())


rows = []
for fn in sorted(SRC.glob("page_*.html")):
    s = fn.read_text(encoding="utf-8", errors="replace")
    for li in re.findall(r'<li id="bx_[^"]*">(.*?)</li>', s, flags=re.S):
        cult = re.search(r'cell__culture">(.*?)</span>', li, re.S)
        c = txt(cult.group(1)) if cult else ""
        m = re.match(r"(.*?)\s*\((.*)\)$", c or "")
        r = {"culture": m.group(1) if m else c, "culture_group": m.group(2) if m else "",
             "code": txt(re.search(r'cell__code">(.*?)</span>', li, re.S).group(1)),
             "name": txt(re.search(r'cell__name">(.*?)</span>', li, re.S).group(1)),
             "year": txt(re.search(r'cell__year">(.*?)</span>', li, re.S).group(1)),
             "regions": ";".join(txt(x) for x in re.findall(r'results-table-region">(.*?)</span>', li, re.S)),
             "url": "https://gossortrf.ru" + re.search(r'href="([^"]+)"', li).group(1)}
        for k in range(1, 8):
            v = re.search(rf'params__value_{k}">(.*?)</div>', li, re.S)
            pop = re.search(r'results-table-popup[^"]*">(.*?)</span>', v.group(1), re.S) if v else None
            r[f"p{k}"] = txt(pop.group(1)) if pop else ""
        rows.append(r)
with (OUT / "tom1.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(len(rows), "rows")
