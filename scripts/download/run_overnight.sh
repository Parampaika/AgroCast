#!/usr/bin/env bash
# Ночная докачка: ждёт снятия блокировки fedstat (403), затем докачивает недостающие показатели ЕМИСС
# (медленно, с паузами), парсит их в data/interim и повторно проходит ERA5, SoilGrids, NDVI и ВСХП,
# чтобы заполнить пропущенные из-за сетевых сбоев файлы. Уже скачанное во всех скриптах пропускается.
# Запуск: nohup bash scripts/download/run_overnight.sh > data/cache/logs/overnight.log 2>&1 &
cd "$(dirname "$0")/../.."
export PYTHONIOENCODING=utf-8
PY="uv run python -I"
EMISS_MISSING="30950 31454 57740 31110 58667 58670 38122 57741 40510 57697 42302 31360 33944 37066 40556 42305 42337 42357 42371 42372 43362 43922 45420 58562 58600"

echo "$(date) wait for ERA5/SoilGrids first pass"
running() {  # число живых процессов первого прохода (по командной строке)
  powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'era5_openmeteo_s3|soilgrids.py' }).Count"
}
while n=$(running | tr -dc '0-9'); [ -n "$n" ] && [ "$n" != "0" ]; do sleep 300; done

echo "$(date) second pass: ERA5 (fill gaps)"
$PY scripts/download/era5_openmeteo_s3.py era5_land temperature_2m dew_point_2m snow_depth soil_moisture_0_to_7cm soil_moisture_7_to_28cm soil_moisture_28_to_100cm soil_moisture_100_to_255cm soil_temperature_0_to_7cm soil_temperature_7_to_28cm soil_temperature_28_to_100cm
$PY scripts/download/era5_openmeteo_s3.py era5 precipitation shortwave_radiation temperature_2m dew_point_2m direct_radiation wind_u_component_10m wind_v_component_10m wind_gusts_10m cloud_cover snowfall_water_equivalent soil_moisture_0_to_7cm soil_moisture_7_to_28cm soil_moisture_28_to_100cm soil_temperature_0_to_7cm
echo "$(date) second pass: SoilGrids, VSHP"
$PY scripts/download/soilgrids.py
$PY scripts/download/wayback_files.py rosstat/vshp2016 gks.ru/free_doc/new_site/business/sx/vsxp2016/

echo "$(date) wait for fedstat"
for i in $(seq 1 96); do
  c=$(curl -s -m 30 -o /dev/null -w "%{http_code}" -A Mozilla/5.0 https://www.fedstat.ru/indicator/31533 || true)
  [ "$c" = "200" ] && break
  sleep 300
done
echo "$(date) fedstat status $c, EMISS retry"
for i in $EMISS_MISSING; do
  $PY scripts/download/emiss.py --sdmx-only $i
  sleep 60
done
$PY scripts/parse/emiss_sdmx.py
echo "$(date) overnight done"
