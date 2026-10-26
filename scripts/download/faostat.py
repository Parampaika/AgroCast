"""FAOSTAT bulk-архивы (все страны, нормализованный формат) -> data/raw/faostat/.
QCL — производство/площадь/урожайность культур 1961–; PP — цены производителей; RFN — удобрения (N, P2O5, K2O);
RL — землепользование; QV — стоимость продукции; QI — индексы производства; RP/RT — пестициды (использование/торговля).
Фильтрация по России/Казахстану/Украине делается потом, архивы сохраняются целиком.
Запуск: uv run python -I scripts/download/faostat.py
"""
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "faostat"
OUT.mkdir(parents=True, exist_ok=True)
BASE = "https://bulks-faostat.fao.org/production/"
FILES = ["Production_Crops_Livestock_E_All_Data_(Normalized).zip",
         "Prices_E_All_Data_(Normalized).zip",
         "Inputs_FertilizersNutrient_E_All_Data_(Normalized).zip",
         "Inputs_LandUse_E_All_Data_(Normalized).zip",
         "Value_of_Production_E_All_Data_(Normalized).zip",
         "Production_Indices_E_All_Data_(Normalized).zip",
         "Inputs_Pesticides_Use_E_All_Data_(Normalized).zip",
         "Environment_Temperature_change_E_All_Data_(Normalized).zip"]
for name in FILES:
    fn = OUT / name
    if fn.exists() and fn.stat().st_size > 1000:
        continue
    try:
        with requests.get(BASE + name, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(fn.with_suffix(".part"), "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        fn.with_suffix(".part").rename(fn)
        print(name, fn.stat().st_size // 1024, "KB", flush=True)
    except Exception as e:
        print(name, "FAILED", repr(e)[:200], flush=True)
