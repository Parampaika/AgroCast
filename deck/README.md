# Презентация для жюри

12 слайдов на 5–7 минут: `deck/out/agrokast_presentation.pptx` (+ PDF), сценарий доклада — [script.md](script.md) (он же лежит в заметках докладчика к слайдам). Числа в слайды руками не вписываются: генератор берёт их из `reports/tables/*`, `reports/final_models.md`, `web/data/*.json` и кэшей отчёта (`report/build/data_stats.json`, `shap_features.csv`).

```bash
uv run python -I -X utf8 src/deck/build_deck.py            # pptx + PDF (через установленный PowerPoint) + script.md
uv run python -I -X utf8 src/deck/build_deck.py --no-pdf   # без PDF
uv run python -I -X utf8 src/deck/build_deck.py --png      # плюс PNG слайдов в deck/build/png, чтобы посмотреть глазами
uv run python -I -X utf8 src/deck/shots.py                 # переснять скриншоты сайта (сервер на :8011) в deck/assets/shots
```

| где | что |
|---|---|
| `deck/config.toml` | ФИО, контакты, ссылка на репозиторий и сайт: пустые поля на слайдах видны как «[заполнить]» |
| `src/deck/facts.py` | все числа: данные, лесенка моделей, интервалы, SHAP, оптимизация |
| `src/deck/slides.py` | вёрстка 12 слайдов (диаграммы нативные, редактируются в PowerPoint) |
| `src/deck/script.py` | текст доклада, вопросы жюри, контроль свежести источников |
| `src/deck/kit.py` | палитра сайта «Агрокаст» и помощники python-pptx |

Если оптимизацию пересчитали (`src/optimize/run.py all`), достаточно пересобрать презентацию: слайд 9 и сценарий возьмут новые таблицы. В конце `script.md` — даты изменения источников и проверка, что расчёт оптимизации новее итоговых прогнозов. Без PowerPoint PDF не собирается — тогда только `--no-pdf`.
