"""Выборка из bulk-архивов FAOSTAT и USDA PSD по России, Казахстану, Украине (+ Беларусь) -> data/interim/.
Без чистки: строки как в исходнике, только фильтр по стране.
Запуск: uv run python -I scripts/parse/faostat_psd_subset.py
"""
import io
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FAO = ROOT / "data" / "raw" / "faostat"
OUT = ROOT / "data" / "interim"
(OUT / "faostat").mkdir(parents=True, exist_ok=True)
(OUT / "usda_psd").mkdir(parents=True, exist_ok=True)
FAO_COUNTRIES = {"Russian Federation", "Kazakhstan", "Ukraine", "Belarus"}

for z in sorted(FAO.glob("*.zip")):
    with zipfile.ZipFile(z) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".csv") and "All_Data" in n and "Flag" not in n)
        with zf.open(name) as f:
            df = pd.read_csv(f, encoding="latin-1", low_memory=False)
    col = "Area" if "Area" in df.columns else next(c for c in df.columns if c.lower().startswith("area"))
    sub = df[df[col].isin(FAO_COUNTRIES)]
    out = OUT / "faostat" / (z.stem.replace("_E_All_Data_(Normalized)", "") + "_RU_KZ_UA_BY.csv")
    sub.to_csv(out, index=False, encoding="utf-8")
    print(z.name, len(df), "->", len(sub))

with zipfile.ZipFile(ROOT / "data" / "raw" / "usda_psd" / "psd_alldata_csv.zip") as zf:
    name = zf.namelist()[0]
    df = pd.read_csv(io.BytesIO(zf.read(name)), low_memory=False)
sub = df[df["Country_Name"].isin(["Russia", "Kazakhstan", "Ukraine", "Belarus"])]
sub.to_csv(OUT / "usda_psd" / "psd_RU_KZ_UA_BY.csv", index=False, encoding="utf-8")
print("PSD", len(df), "->", len(sub), "years", sub["Market_Year"].min(), sub["Market_Year"].max())
