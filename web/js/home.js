// Стартовая страница-«визитка»: что это, куда идти, как работает, цифры проекта, границы, автор и материалы.
import { D } from './data.js';
import { fmt } from './util.js';

const IC = {
  calc: '<svg viewBox="0 0 24 24"><rect x="5" y="3" width="14" height="18" rx="3"/><path d="M8.5 7h7M8.5 11h1M12 11h1M8.5 14.5h1M12 14.5h1M8.5 18h1M12 18h1M15.5 11v7"/></svg>',
  map: '<svg viewBox="0 0 24 24"><path d="M3 6.5 9 4l6 2.5L21 4v13.5L15 20l-6-2.5L3 20V6.5Z"/><path d="M9 4v13.5M15 6.5V20"/></svg>',
  opt: '<svg viewBox="0 0 24 24"><path d="M4 19h16"/><path d="M5 15l4-4 3 3 7-7"/><path d="M15 7h4v4"/></svg>',
  doc: '<svg viewBox="0 0 24 24"><path d="M5 4h10l4 4v12H5z"/><path d="M15 4v4h4M8 12h8M8 16h6"/></svg>',
  arrow: '<svg viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
};

const REPO = 'https://github.com/Parampaika/AgroCast';
const TG = 'https://t.me/Parampayka';

export function renderHome(el) {
  // Числа берём из данных сайта; остальные — из отчётов проекта (reports/ladder.md, reports/preprocess.md, reports/sweep.md)
  const regs = D.forecast.regions;
  const nRegions = Object.keys(regs).length;
  const nCrops = new Set(Object.values(regs).flatMap((r) => Object.keys(r))).size;
  const stats = [
    ['17', 'источников открытых данных', 'ЕМИСС, погода ERA5, спутники, почвы'],
    ['683', 'столбца в таблице модели', 'погода, почвы, спутник, прошлые годы'],
    [`${nRegions} × ${nCrops}`, 'регионов и культур', 'в прогнозе на сезон 2026'],
    ['> 1 000', 'проверенных конфигураций моделей', 'на единой проверке по времени'],
    ['−30 %', 'ошибки к «прошлому году»', 'к концу сезона, проверка 2012–2025'],
  ];
  el.innerHTML = `
  <div class="home">
    <section class="hero">
      <div class="eyebrow">Решение кейса «Своё Фермерство» · задача 5</div>
      <h1>Агрокаст</h1>
      <p class="lead">Калькулятор урожайности участка и подсказка, что посеять: оценка в т/га и тоннах для нескольких культур по погоде, климату, почве, сорту и агротехнике. Основа — прогноз урожайности по регионам России на каждый месяц сезона.</p>
      <div class="hero-cta">
        <a class="btn big" href="#/calc">Рассчитать урожай моего участка ${IC.arrow}</a>
        <a class="btn ghost big" href="#/overview">Прогноз по регионам</a>
      </div>
      <p class="muted-note">Работа участника конкурса РСХБ, не продукт банка.</p>
    </section>

    <section class="block">
      <h2>Что есть на сайте</h2>
      <div class="tiles">
        <a class="tile" href="#/calc"><span class="ei">${IC.calc}</span><b>Калькулятор участка</b><small>Рассчитать урожай, выручку и маржу для вашего участка</small></a>
        <a class="tile" href="#/overview"><span class="ei">${IC.map}</span><b>Прогноз по регионам</b><small>Карта и карточка региона, оценка по месяцам сезона</small></a>
        <a class="tile" href="#/optimize"><span class="ei">${IC.opt}</span><b>Что посеять</b><small>Оптимизация структуры посевов: изменить немного — выиграть заметно</small></a>
        <a class="tile" href="#/method"><span class="ei">${IC.doc}</span><b>Методика</b><small>Данные, модель, проверка и ограничения</small></a>
      </div>
    </section>

    <section class="block">
      <h2>Как это работает</h2>
      <ol class="steps3">
        <li><span class="n">1</span><b>Открытые данные</b><small>Статистика урожайности ЕМИСС, погода ERA5, спутниковые снимки и почвы.</small></li>
        <li><span class="n">2</span><b>Модель «тренд × погода»</b><small>Оценивает, насколько погода сезона сдвигает урожайность региона, на пять дат — с 1 мая до итога сезона.</small></li>
        <li><span class="n">3</span><b>Расчёт для вашего участка</b><small>Пересчитывает региональный прогноз под ваш план и подсказывает, что немного изменить в посевах.</small></li>
      </ol>
    </section>

    <section class="block">
      <h2>Проект в цифрах</h2>
      <div class="stats">${stats.map(([n, t, s]) => `<div class="stat"><div class="num-big">${n}</div><b>${t}</b><small>${s}</small></div>`).join('')}</div>
    </section>

    <section class="block honest">
      <h2>Честно о границах</h2>
      <ul>
        <li><b>Участок — это регион с поправками.</b> Прогноз для участка равен прогнозу региона, скорректированному на почву, сорт и агротехнику; эти поправки — допущения, а не оценки по данным.</li>
        <li><b>«Итог сезона» — не прогноз.</b> Оценка на конец сезона 2026 строится по фактической погоде завершившегося сезона.</li>
      </ul>
      <a class="more-link" href="#/method">Подробнее — в Методике ${IC.arrow}</a>
    </section>

    <footer class="home-foot">
      <div>
        <b>Соболев Даниил</b>, аспирант СПбПУ
        <div class="muted-note">Решение кейса «Своё Фермерство», задача 5 — работа участника конкурса, не продукт банка.</div>
      </div>
      <div class="foot-links">
        <a href="${REPO}" target="_blank" rel="noopener">Репозиторий на GitHub</a>
        <a href="materials/agrokast_presentation.pdf" target="_blank" rel="noopener">Презентация (PDF)</a>
        <a href="materials/rshb_yield_forecast_report.pdf" target="_blank" rel="noopener">Научный отчёт (PDF)</a>
        <a href="${TG}" target="_blank" rel="noopener">Связаться в Telegram</a>
      </div>
    </footer>
  </div>`;
}
