# Научный отчёт

Отчёт собирается скриптом, цифры в тексте не пишутся руками.

```bash
uv run --group report python -I -X utf8 src/report/build_report.py
```

Около минуты: графики → `.docx` → Word обновляет оглавление и сохраняет PDF. Результат — `report/out/rshb_yield_forecast_report.{docx,pdf}`. Без Word: флаг `--no-pdf` (оглавление тогда обновляется в Word клавишей F9).

| где | что |
|---|---|
| `report/text/*.md` | текст разделов; порядок — по имени файла |
| `report/meta.toml` | титульный лист (ФИО автора — заполнить) |
| `src/report/build_report.py` | разметка, ключи `{{…}}`, таблицы, вёрстка docx, PDF через Word |
| `src/report/figures.py`, `style.py` | все графики в одной палитре |
| `src/report/sources.py` | чтение результатов: перебор `data/model/v*/`, лесенка и оптимизация из `reports/tables/` |
| `src/report/data_stats.py` | инвентарь `data/` (кэш `report/build/data_stats.json`, пересчёт — `--stats`, ≈10 мин) |
| `src/report/shap_calc.py` | SHAP для раздела интерпретации (кэш `report/build/shap_features.csv`, пересчёт — `--shap`) |

Разметка текста: `# / ## / ###`, списки, таблицы markdown, `**жирный**`, `x_{c}`, формулы `$$ … $$`, директивы `::figure id | подпись`, `::image путь | подпись`, `::table id | подпись`, `::keyfigures`, `::pending текст`, `::if флаг … ::else … ::endif`.

Если результата ещё нет (например, `reports/tables/ladder_*.csv`), на его месте стоит жёлтая пометка «ждёт данных», а список таких мест пишется в `report/build/missing.txt`. Появился файл — достаточно пересобрать.
