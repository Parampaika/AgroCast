#!/usr/bin/env bash
# Перезапускает modis_ndvi.py при падении (сетевые сбои) до полного прохода; готовые файлы пропускаются.
cd "$(dirname "$0")/../.."
for i in $(seq 1 30); do
  uv run python -I scripts/download/modis_ndvi.py "${1:-2}" ${2:-0} && break
  echo "$(date) retry $i"; sleep 60
done
