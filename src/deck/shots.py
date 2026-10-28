"""Свежие скриншоты сайта для презентации: headless Edge, сайт на http://localhost:8011.

    uv run python -I -X utf8 src/deck/shots.py [--url http://localhost:8011]

Запускает сервер сам не умеет: `uv run python -I src/web_export/serve.py 8011` (или http.server -d web 8011).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "deck" / "assets" / "shots"
EDGES = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
         r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]

# имя файла, маршрут, размер окна (CSS-пиксели); масштаб 1,5 даёт чёткую картинку
SHOTS = [
    ("overview", "#/overview", (1440, 900)),
    ("region", "#/region/03000000000", (1440, 1500)),
    ("optimize", "#/optimize", (1440, 1280)),
    ("calc", "#/calc", (1440, 1750)),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8011")
    a = ap.parse_args()
    edge = next((p for p in EDGES if Path(p).exists()), None)
    if not edge:
        print("Edge не найден", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for name, route, (w, h) in SHOTS:
        dst = OUT / f"{name}.png"
        subprocess.run([edge, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=1.5", f"--window-size={w},{h}",
                        "--virtual-time-budget=15000", f"--screenshot={dst}", f"{a.url}/{route}"],
                       capture_output=True, timeout=120)
        print(dst, dst.exists() and dst.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
