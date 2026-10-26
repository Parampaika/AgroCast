"""Таблица скачанных показателей ЕМИСС -> data/interim/emiss/inventory.tsv (id, название, ед., годы, число строк, территорий, размер xml МБ)."""
import glob, json, os
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
rows = []
for d in sorted(glob.glob(str(ROOT / "data/raw/emiss/[0-9]*")), key=lambda p: int(os.path.basename(p))):
    i = os.path.basename(d)
    fj = Path(d) / "filters.json"
    title = json.loads(fj.read_text(encoding="utf-8"))["title"] if fj.exists() else ""
    xmls = glob.glob(d + "/data*.xml")
    pq = ROOT / "data/interim/emiss" / f"{i}.parquet"
    if pq.exists():
        df = pd.read_parquet(pq)
        ok = df[df.value_num.notna()]
        r = dict(rows=len(ok), years=f"{ok.time.min()}–{ok.time.max()}" if len(ok) else "", terr=ok.s_OKATO.nunique() if "s_OKATO" in ok else "",
                 unit="; ".join(map(str, df["EI"].dropna().unique()[:2])) if "EI" in df else "")
    else:
        r = dict(rows="", years="", terr="", unit="")
    rows.append(dict(id=i, title=title.replace("\t", " ")[:140], status="скачано" if xmls else "нет данных", mb=round(sum(os.path.getsize(x) for x in xmls) / 2**20, 1), **r))
pd.DataFrame(rows).to_csv(ROOT / "data/interim/emiss/inventory.tsv", sep="\t", index=False)
print(len(rows), "indicators")
