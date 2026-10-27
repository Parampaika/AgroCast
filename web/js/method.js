// Экран «О методике»: источники, схема, точность против бейзлайнов, ошибка по дате прогноза, ограничения.
import { D, crop } from './data.js';
import { SRC_ICONS } from './icons.js';
import { chart, opt, css, demoBadge, fmt } from './util.js';

const SOURCES = [
  ['stats', 'ЕМИСС / Росстат', 'Урожайность, посевные площади и валовой сбор по 89 субъектам, 2000–2025; цены производителей.'],
  ['weather', 'ERA5 и ERA5-Land', 'Почасовая погода в 450 точках пашни: температура, осадки, влага в почве, ГТК, жаркие дни.'],
  ['soil', 'SoilGrids 2.0', 'Почвы пашни: гранулометрия, pH, органический углерод, азот, класс WRB.'],
  ['sat', 'MODIS NDVI', 'Спутниковый индекс зелёной массы по 16-дневным композитам, 2000–2026.'],
  ['cal', 'GGCMI', 'Календари посева и созревания культур: окна погоды для каждой культуры.'],
  ['price', 'Цены производителей', 'ЕМИСС 31454 и 57693: цена тонны по субъектам с подстановкой ФО → РФ.'],
];

export function renderMethod(el) {
  el.innerHTML = `
  <div class="page-head"><div>
    <div class="eyebrow">О методике</div>
    <h1>Открытые данные → модель → прогноз → решение</h1>
    <p class="lead">Модель предсказывает не урожайность «в лоб», а отклонение от технологического тренда, которое объясняет погода сезона. Выход — распределение по погодным сценариям, а не одна точка.</p>
  </div></div>
  <div class="card" style="margin-bottom:18px"><div class="card-head"><h3>Источники данных</h3><span class="chip-note">все открытые, без ключей</span></div>
    <div class="sources" style="grid-template-columns:repeat(auto-fit,minmax(210px,1fr))">${SOURCES.map(([ic, h, p]) => `<div class="source"><div class="ic">${SRC_ICONS[ic]}</div><h4>${h}</h4><p>${p}</p></div>`).join('')}</div>
  </div>
  <div class="card" style="margin-bottom:18px"><div class="card-head"><h3>Как устроен расчёт</h3></div>
    <div class="pipeline">
      <div class="pipe"><div class="k">1 · Данные</div><h4>Чистый слой</h4><p>Субъект × культура × год: урожайность, тренды, погодные аномалии по месяцам, почвы, NDVI.</p></div>
      <div class="pipe"><div class="k">2 · Модель</div><h4>Тренд × погода</h4><p>Урожайность = тренд × (1 + отклонение). Отклонение — ансамбль Ridge и бустинга на аномалиях погоды.</p></div>
      <div class="pipe"><div class="k">3 · Прогноз на дату</div><h4>Сценарии погоды</h4><p>Известные месяцы — факт, остальные — из прошлых сезонов. Интервал = сценарии + ошибка модели.</p></div>
      <div class="pipe"><div class="k">4 · Решение</div><h4>Оптимизация плана</h4><p>Сценарии урожайности × цены − затраты → прибыль. Ищем план с лучшей прибылью при ограничениях.</p></div>
    </div>
  </div>
  <div class="grid g-2">
    <div class="card"><div class="card-head"><div><h3>Точность: MAPE по субъектам, %</h3><div class="sub">Скользящая проверка 2012–2025, меньше — лучше</div></div>${demoBadge('предварительная модель', 'Результаты исследовательской модели (reports/model_weather.md); финальная модель ещё подбирается')}</div><div class="chart lg" id="mAcc"></div></div>
    <div class="card"><div class="card-head"><div><h3>Выигрыш погоды к тренду по дате прогноза</h3><div class="sub">Снижение MAE относительно линейного тренда, %</div></div>${demoBadge('предварительная модель')}</div><div class="chart lg" id="mLead"></div></div>
  </div>
  <div class="card" style="margin-top:18px"><div class="card-head"><h3>Честные ограничения</h3></div>
    <ul class="limits">
      <li><b>Уровень региона, не поля.</b> Статистика есть по субъектам, поэтому прогноз для участка — региональный с пользовательскими поправками на почву, сорт и агротехнику.</li>
      <li><b>Интервал широкий.</b> 80 % интервал — около ±25–35 % даже в конце сезона: в нём учтена и погода, и ошибка самой модели.</li>
      <li><b>Яровые весной ≈ тренд.</b> Для яровых, кукурузы и свёклы погода начинает помогать с июля–августа; для озимой пшеницы — уже с апреля.</li>
      <li><b>Затраты — допущения.</b> Открытых нормативов затрат по культурам нет; цены — фактические средние производителей.</li>
      <li><b>Урожайность «на убранную площадь».</b> Гибель посевов в засуху статистика видит слабо; в оптимизации это учитывается через сценарии.</li>
    </ul>
    <p class="chip-note" style="margin-top:14px">Подробно: <a href="../docs/04_research_agroforecast.md">обзор методик агропрогноза</a>, <a href="../reports/model_weather.md">отчёт о модели «тренд × погода»</a>, <a href="../docs/06_ui_data_contract.md">формат данных интерфейса</a>.</p>
  </div>`;

  const acc = D.metrics.accuracy;
  const methods = D.metrics.methods;
  const cols = [css('--border-strong'), css('--div-2'), css('--gold'), css('--brand-2')];
  chart(el.querySelector('#mAcc')).setOption(opt({
    legend: { data: methods, left: 0, right: 'auto' },
    grid: { top: 40, left: 4, right: 8, bottom: 4 },
    tooltip: { axisPointer: { type: 'shadow' }, valueFormatter: (v) => fmt(v, 1) + ' %' },
    xAxis: { type: 'category', data: acc.map((a) => crop(a.crop_code).short), axisLabel: { interval: 0, fontSize: 10.5, rotate: 30 } },
    yAxis: { type: 'value', axisLabel: { formatter: '{value} %' } },
    series: methods.map((m, k) => ({ name: m, type: 'bar', data: acc.map((a) => a[m].mape), itemStyle: { color: cols[k], borderRadius: [3, 3, 0, 0] }, barGap: '8%' })),
  }));

  const order = ['1 апр', '1 мая', '1 июня', '1 июля', '1 авг', '1 сен', 'конец'];
  const crops = [...new Set(D.metrics.leadtime.map((x) => x.crop_code))];
  chart(el.querySelector('#mLead')).setOption(opt({
    legend: { data: crops.map((c) => crop(c).short), left: 0, right: 'auto', type: 'scroll' },
    grid: { top: 40, left: 4, right: 12, bottom: 4 },
    tooltip: { valueFormatter: (v) => fmt(v, 1) + ' %' },
    xAxis: { type: 'category', data: order, boundaryGap: false },
    yAxis: { type: 'value', axisLabel: { formatter: '{value} %' } },
    series: crops.map((cc) => ({
      name: crop(cc).short, type: 'line', smooth: true, symbolSize: 6,
      data: order.map((o) => D.metrics.leadtime.find((x) => x.crop_code === cc && x.cutoff === o)?.skill_pct ?? null),
      lineStyle: { width: cc === '1010400' ? 3.5 : 2, color: crop(cc).color }, itemStyle: { color: crop(cc).color },
    })),
  }));
}
