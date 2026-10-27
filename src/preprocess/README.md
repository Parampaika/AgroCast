# src/preprocess — сборка `data/clean/`

Что получается на выходе и как этим пользоваться — в [reports/preprocess.md](../../reports/preprocess.md) и [data/clean/DATA_DICTIONARY.md](../../data/clean/DATA_DICTIONARY.md). Код читай, только если меняешь сборку.

| модуль | шаг `build_all.py` | выход |
|---|---|---|
| `common.py` | — | пути, `Config`, кэш разбора ЕМИСС (`emiss(id)` → `data/clean/_cache/emiss/`) |
| `regions.py` | `regions` | `regions` |
| `crops.py` | `crops` | `crops` |
| `yield_panel.py` | `yield` | `yield_panel`, `yield_operational`; `harmonize_regions()` — общая склейка кодов территорий |
| `weather.py` | `weather` | `weather_region_month`, `weather_region_season` (+ кэш суточной погоды) |
| `soil.py` | `soil` | `soil_region` (почвы, WRB, рельеф `elev_*`) |
| `ndvi.py` | `ndvi` | `ndvi_region`, `ndvi_region_year` (+ кэш точек) |
| `modis_extra.py` | `modis` | `modis_extra_region`, `modis_extra_region_year` (LAI/FPAR, LST, GPP; + кэш в `_cache/modis/`) |
| `calendar.py` | `calendar` | `crop_calendar` |
| `prices.py` | `prices` | `prices`, `prices_crop_map` |
| `economics.py` | `economics` | `economics_aux` |
| `model_table.py` | `model_table` | `weather_crop_window`, `model_table` |

Порядок зависимостей: `regions` → `crops` → `yield` → остальные → `model_table`. Он соблюдается, если запускать без аргументов. Разбор SDMX и суточная погода импортируются из `src/data/parse_emiss.py` и `src/data/build_weather_daily.py`; эти файлы не правь. Сводки шагов пишутся в `data/clean/_stats/*.json`.
