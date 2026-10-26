"""SPEIbase v2.9 (CSIC, DOI 10.20350/digitalCSIC/16497): глобальный индекс засухи SPEI, 0.5°, месячный, 1901–2022.
Скачиваем масштабы 1, 3, 6, 9, 12, 24 месяца + README -> data/raw/spei/. Остальные масштабы (по 375 МБ) не нужны.
Запуск: uv run python -I scripts/download/spei.py
"""
import re
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "spei"
OUT.mkdir(parents=True, exist_ok=True)
html = requests.get("https://digital.csic.es/handle/10261/332007", timeout=120).text
links = sorted(set(re.findall(r'href="(/bitstream/10261/332007/\d+/[^"]+)"', html)))
want = {f"spei{n:02d}.nc" for n in (1, 3, 6, 9, 12, 24)} | {"README.pdf", "file-list.txt"}
for l in links:
    name = l.rsplit("/", 1)[1]
    if name not in want:
        continue
    fn = OUT / name
    if fn.exists() and fn.stat().st_size > 1000:
        continue
    with requests.get("https://digital.csic.es" + l, stream=True, timeout=900) as r:
        r.raise_for_status()
        with open(fn.with_suffix(fn.suffix + ".part"), "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    fn.with_suffix(fn.suffix + ".part").rename(fn)
    print(name, fn.stat().st_size // 2**20, "MB", flush=True)
