# Выбранные итоговые модели

| культура | дата | тип | члены | MAE | выигрыш, % | покрытие 80 % |
|---|---|---|---|---|---|---|
| Ячмень яровой | 1 мая | lgbm | lgbm/F1/mean5/ratio | 0.325 | 6.7 | 0.87 |
| Ячмень яровой | 1 июня | ens_mean5 | lgbm/F0/mean5/ratio; et/F0/mean5/ratio; rf/F1/mean5/ratio; xgb/F1/mean5/ratio; cat/F1/mean5/ratio | 0.323 | 7.2 | 0.85 |
| Ячмень яровой | 1 июля | ens_mean2 | lgbm/F3/mean5/ratio; et/F6/mean5/ratio | 0.304 | 12.6 | 0.88 |
| Ячмень яровой | 1 авг | ens_mean2 | et/F6/mean5/ratio; lgbm/F3/mean5/ratio | 0.282 | 19.0 | 0.89 |
| Ячмень яровой | Конец сезона | ens_mean5 | cat/F1/mean5/ratio; xgb/F1/mean5/ratio; lgbm/F1/mean5/ratio; ridge/F4/lin15/diff; et/F6/mean5/ratio | 0.271 | 22.3 | 0.88 |
| Кукуруза на зерно | 1 мая | lgbm | lgbm/F7/mean5/diff | 0.858 | 11.4 | 0.87 |
| Кукуруза на зерно | 1 июня | lgbm | lgbm/F7/mean5/diff | 0.866 | 10.6 | 0.86 |
| Кукуруза на зерно | 1 июля | lgbm | lgbm/F7/mean5/diff | 0.870 | 10.1 | 0.86 |
| Кукуруза на зерно | 1 авг | et | et/F8/mean5/diff | 0.790 | 18.4 | 0.87 |
| Кукуруза на зерно | Конец сезона | ens_mean3 | lgbm/F2r/mean5/diff; cat/F2r/mean5/diff; rf/F2r/mean5/diff | 0.764 | 21.1 | 0.88 |
| Соя | 1 мая | et | et/F0/mean5/diff | 0.253 | 8.4 | 0.93 |
| Соя | 1 июня | et | et/F0/mean5/diff | 0.253 | 8.4 | 0.93 |
| Соя | 1 июля | et | et/F7/mean5/diff | 0.252 | 8.6 | 0.92 |
| Соя | 1 авг | et | et/F7/mean5/diff | 0.244 | 11.4 | 0.93 |
| Соя | Конец сезона | ens_mean5 | ridge/F7/mean5/diff; et/F7/mean5/diff; cat/F7/mean5/diff; rf/F7/mean5/diff; xgb/F7/mean5/diff | 0.235 | 15.0 | 0.93 |
| Пшеница яровая | 1 мая | ens_mean3 | et/F6/mean5/ratio; lgbm/F1/mean5/ratio; cat/F8/lin_all/ratio | 0.370 | 4.9 | 0.86 |
| Пшеница яровая | 1 июня | ens_mean3 | cat/F8/lin_all/ratio; lgbm/F2/mean5/ratio; et/F0/mean5/ratio | 0.364 | 6.5 | 0.83 |
| Пшеница яровая | 1 июля | ens_mean2 | cat/F8/lin_all/ratio; et/F1/mean5/ratio | 0.350 | 10.1 | 0.85 |
| Пшеница яровая | 1 авг | ens_mean5 | et/F8/mean5/ratio; lgbm/F1/mean5/ratio; rf/F6/mean5/ratio; xgb/F6/mean5/ratio; cat/F8/lin_all/ratio | 0.314 | 19.4 | 0.86 |
| Пшеница яровая | Конец сезона | ens_mean2 | ridge/F6/lin15/ratio; xgb/F8/lin_all/ratio | 0.319 | 18.1 | 0.83 |
| Сахарная свёкла | 1 мая | ens_mean2 | et/F7/mean5/diff; cat/F5/mean5/diff | 5.835 | 8.2 | 0.86 |
| Сахарная свёкла | 1 июня | et | et/F0/mean5/diff | 6.120 | 3.7 | 0.88 |
| Сахарная свёкла | 1 июля | ens_mean2 | et/F0/mean5/diff; cat/F5/mean5/diff | 6.088 | 4.2 | 0.85 |
| Сахарная свёкла | 1 авг | ens_mean3 | et/F7/mean5/diff; cat/F5/mean5/diff; xgb/F2/mean5/diff | 5.546 | 12.7 | 0.88 |
| Сахарная свёкла | Конец сезона | ens_mean2 | ridge/F6/mean5/diff; cat/F5/mean5/diff | 4.451 | 30.0 | 0.85 |
| Подсолнечник | 1 мая | ens_mean2 | lgbm/F7/mean5/diff; et/F6/mean5/diff | 0.216 | 3.7 | 0.91 |
| Подсолнечник | 1 июня | et | et/F7/mean5/diff | 0.215 | 4.4 | 0.9 |
| Подсолнечник | 1 июля | ens_mean2 | et/F8/mean5/diff; lgbm/F7/mean5/diff | 0.210 | 6.4 | 0.88 |
| Подсолнечник | 1 авг | et | et/F8/mean5/diff | 0.196 | 12.8 | 0.87 |
| Подсолнечник | Конец сезона | ens_mean2 | et/F7/mean5/diff; cat/F8/mean5/diff | 0.201 | 10.7 | 0.88 |
| Пшеница озимая | 1 мая | ens_mean2 | et/F2/mean5/diff; lgbm/F2r/mean5/diff | 0.474 | 13.8 | 0.86 |
| Пшеница озимая | 1 июня | ens_mean2 | et/F8/mean5/diff; lgbm/F2/mean5/diff | 0.460 | 16.4 | 0.85 |
| Пшеница озимая | 1 июля | ens_mean2 | et/F8/mean5/diff; lgbm/F6/mean5/diff | 0.450 | 18.2 | 0.87 |
| Пшеница озимая | 1 авг | et | et/F8/mean5/diff | 0.451 | 18.1 | 0.85 |
| Пшеница озимая | Конец сезона | ens_mean2 | xgb/F2/mean5/diff; ridge/F8/mean5/ratio | 0.409 | 25.8 | 0.86 |
