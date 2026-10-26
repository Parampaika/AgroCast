"""Поиск показателей ЕМИСС по ключевым словам (список QUERIES ниже).
Сырые страницы поиска -> data/raw/emiss/_search/, сводка -> data/interim/emiss/search_hits.tsv
Запуск: uv run python -I scripts/download/emiss_search.py"""
import re, time
from pathlib import Path
import requests
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "emiss" / "_search"
OUT.mkdir(parents=True, exist_ok=True)
QUERIES = ["валовой сбор", "убранная площадь", "посевная площадь", "посевные площади", "урожайность",
           "себестоимость", "цены приобретения", "дизельное топливо", "минеральные удобрения", "органические удобрения",
           "тракторы", "комбайны", "мелиорированных", "орошаемых", "элитными семенами", "семена", "затраты",
           "растениеводства", "энергетические мощности", "цены производителей сельскохозяйственной",
           "индекс цен производителей сельскохозяйственной", "продукция сельского хозяйства", "рентабельность",
           "сельскохозяйственные угодья", "пашня", "гибели посевов", "зерно", "подсолнечник", "сельскохозяйственных организаций",
           "материально-технических ресурсов", "известкование", "сортовыми", "химической мелиорации", "пестицид",
           "сельскохозяйственной техники", "приобретенных сельскохозяйственными"]
rows = {}
for q in QUERIES:
    fn = OUT / f"{q}.html"
    if not fn.exists():
        r = requests.get("https://www.fedstat.ru/indicators/search", params={"searchText": q}, timeout=120,
                         headers={"User-Agent": "Mozilla/5.0"})
        fn.write_text(r.text, encoding="utf-8")
        time.sleep(1)
    html = fn.read_text(encoding="utf-8")
    for i, t in re.findall(r'href="/indicator/(\d+)"[^>]*>\s*([^<]+)<', html):
        rows.setdefault(i, [" ".join(t.split()), set()])[1].add(q)
dst = ROOT / "data" / "interim" / "emiss" / "search_hits.tsv"
dst.write_text("\n".join(f"{i}\t{t}\t{'; '.join(sorted(qs))}" for i, (t, qs) in sorted(rows.items(), key=lambda x: int(x[0]))),
               encoding="utf-8")
print(len(rows), "indicators ->", dst)
