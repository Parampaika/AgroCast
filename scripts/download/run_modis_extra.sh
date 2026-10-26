#!/usr/bin/env bash
# Последовательно: LAI/FPAR, LST, GPP для точек rank<=1; при падении (сеть) перезапуск до 20 раз на продукт.
cd "$(dirname "$0")/../.."
for prod in lai lst gpp; do
  for i in $(seq 1 20); do
    uv run python -I scripts/download/modis_pc.py $prod 1 && break
    echo "$(date) $prod retry $i"; sleep 60
  done
done
echo "$(date) extra done"
