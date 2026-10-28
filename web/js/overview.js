// Экран «Обзор»: что это одной фразой, три входа, карта + выбор культуры + одно ключевое число; детали — под «Подробнее».
import { D, crop, fc, regionName, rfSummary } from './data.js';
import { cropIcon } from './icons.js';
import { state, fmt, fmtVol, fmtPct, deltaHtml, chart, opt, css, info, seqStops, divStops, quantile, alpha, dateBtn, dateNote, dateWhat, isFinalDate } from './util.js';

// Коническая равноугольная проекция Ламберта для России
const D2R = Math.PI / 180;
const P = (() => {
  const f1 = 52 * D2R, f2 = 68 * D2R, f0 = 60 * D2R, l0 = 100 * D2R;
  const t = (f) => Math.tan(Math.PI / 4 + f / 2);
  const n = Math.log(Math.cos(f1) / Math.cos(f2)) / Math.log(t(f2) / t(f1));
  const F = Math.cos(f1) * Math.pow(t(f1), n) / n;
  const r0 = F / Math.pow(t(f0), n);
  return {
    project([lon, lat]) {
      const r = F / Math.pow(t(lat * D2R), n), a = n * (lon * D2R - l0);
      return [r * Math.sin(a) * 1000, -(r0 - r * Math.cos(a)) * 1000];
    },
    unproject([x, y]) {
      x /= 1000; y = -y / 1000;
      const ry = r0 - y, r = Math.sign(n) * Math.hypot(x, ry), a = Math.atan2(x, ry);
      const lat = 2 * Math.atan(Math.pow(F / r, 1 / n)) - Math.PI / 2;
      return [(a / n + l0) / D2R, lat / D2R];
    },
  };
})();
export const PROJ = P;

let mapRegistered = false;
export function ensureMap() {
  if (!mapRegistered) { echarts.registerMap('ru', D.regions); mapRegistered = true; }
}

export function cropPicker(selected, onPick, only) {
  return `<div class="crop-picker" role="tablist">${D.cropList.map((c) => {
    const dis = only && !only.includes(c.crop_code);
    return `<button class="crop-btn ${c.crop_code === selected ? 'active' : ''}" data-crop="${c.crop_code}" ${dis ? 'disabled' : ''} title="${c.name}">
      <span class="ico" style="color:${c.crop_code === selected ? '#fff' : c.color}">${cropIcon(c)}</span><span class="t">${c.short}</span></button>`;
  }).join('')}</div>`;
}
export function bindCropPicker(root, onPick) {
  root.querySelectorAll('.crop-btn').forEach((b) => b.addEventListener('click', () => onPick(b.dataset.crop)));
}

// Переключатель даты: компактный сегмент + пояснение, что показано
export function dateSeg(id, i) {
  return `<div class="seg" id="${id}" role="group" aria-label="Дата прогноза">${D.dates.map((d, k) => `<button data-i="${k}" class="${k === i ? 'active' : ''}">${dateBtn(k)}</button>`).join('')}</div>`;
}

const IC = {
  map: '<svg viewBox="0 0 24 24"><path d="M3 6.5 9 4l6 2.5L21 4v13.5L15 20l-6-2.5L3 20V6.5Z"/><path d="M9 4v13.5M15 6.5V20"/></svg>',
  calc: '<svg viewBox="0 0 24 24"><rect x="5" y="3" width="14" height="18" rx="3"/><path d="M8.5 7h7M8.5 11h1M12 11h1M8.5 14.5h1M12 14.5h1M8.5 18h1M12 18h1M15.5 11v7"/></svg>',
  opt: '<svg viewBox="0 0 24 24"><path d="M4 19h16"/><path d="M5 15l4-4 3 3 7-7"/><path d="M15 7h4v4"/></svg>',
};

export function renderOverview(el) {
  ensureMap();
  el.innerHTML = `
  <div class="page-head" style="margin-bottom:14px">
    <div>
      <div class="eyebrow">Регионы · сезон 2026</div>
      <h1>Прогноз урожайности по регионам России</h1>
      <p class="lead">Региональная модель — основа калькулятора участка: где и насколько урожай ожидается выше или ниже обычного.</p>
      <span class="frame">Это прогноз для региона в целом (среднее по хозяйствам субъекта), а не для отдельного поля.</span>
    </div>
  </div>
  <nav class="entry" aria-label="Разделы">
    <a href="#/calc" class="here"><span class="ei">${IC.calc}</span><span><b>Рассчитать урожай моего участка</b><small>Регион, площадь, почва, сорт, агротехника → т/га, сбор, маржа</small></span></a>
    <a href="#/overview" id="goMap"><span class="ei">${IC.map}</span><span><b>Прогноз по регионам</b><small>Карта: где урожай выше или ниже обычного</small></span></a>
    <a href="#/optimize"><span class="ei">${IC.opt}</span><span><b>Что посеять</b><small>Как немного изменить план ради прибыли</small></span></a>
  </nav>
  <div class="toolbar" style="margin-bottom:14px" id="cropBar"></div>
  <div class="grid g-overview" id="mapSection">
    <div class="card map-card">
      <div class="card-head">
        <div><h2 id="mapTitle"></h2></div>
        <div style="display:flex;gap:8px;align-items:center">
          <div class="seg" id="metricSeg"><button data-m="yield">т/га</button><button data-m="dev">к обычному, %</button></div>
          ${info('Прогноз — итоговая модель «тренд × погода», обучена на сезонах до 2025 г.; площади посева — 2025 г. (ЕМИСС).', 'Регионы без цвета — нет данных по культуре или площадь меньше 1 тыс. га. «Обычное» = тренд урожайности региона.')}
        </div>
      </div>
      <div class="map-wrap" id="mapWrap"><div class="map-skel sk"></div><div class="map" id="map"></div></div>
      <div class="legend" id="legend" style="margin-top:6px"></div>
      <p class="howto">Цвет — ожидаемая урожайность региона. Нажмите на регион: история, интервал и причины прогноза.</p>
    </div>
    <div class="stack">
      <div class="kpis" id="kpis" style="grid-template-columns:1fr"></div>
      <div class="card" style="padding:16px">
        <div class="field-label" style="margin-bottom:8px">Дата прогноза</div>
        ${dateSeg('dateSeg', state.dateIdx)}
        <p class="date-note" id="dateNote"></p>
      </div>
    </div>
  </div>
  <details class="more">
    <summary><span>Подробнее<small>как уточняется прогноз, регионы выше и ниже обычного</small></span></summary>
    <div class="more-body">
      <div class="grid g-2">
        <div class="card"><p class="verdict" id="refVerdict"></p><div class="chart sm" id="refine"></div></div>
        <div class="card"><p class="verdict">Крупнейшие регионы по сбору</p><ul class="rank-list" id="rank"></ul></div>
      </div>
      <div class="kpis" id="kpis2" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr))"></div>
    </div>
  </details>`;

  const mapEl = el.querySelector('#map');
  const map = chart(mapEl);
  const mapSize = () => Math.round(Math.min(mapEl.clientWidth * 0.9, mapEl.clientHeight * 1.7));
  new ResizeObserver(() => { if (!map.isDisposed() && map.getOption()?.series?.length) map.setOption({ series: [{ layoutSize: mapSize() }] }); }).observe(mapEl);
  const markReady = () => el.querySelector('#mapWrap')?.classList.add('ready');
  map.on('finished', markReady); setTimeout(markReady, 1500);
  let refine = null;
  const more = el.querySelector('.more');
  const drawRefine = () => { if (!refine) refine = chart(el.querySelector('#refine')); update(false, true); };
  more.addEventListener('toggle', () => { if (more.open) drawRefine(); });

  el.querySelector('#goMap').addEventListener('click', (e) => { e.preventDefault(); el.querySelector('#mapSection').scrollIntoView({ behavior: 'smooth', block: 'start' }); });

  const drawCrops = () => {
    el.querySelector('#cropBar').innerHTML = cropPicker(state.crop);
    bindCropPicker(el.querySelector('#cropBar'), (cc) => { state.crop = cc; drawCrops(); update(true); });
  };
  drawCrops();

  el.querySelectorAll('#metricSeg button').forEach((b) => {
    b.classList.toggle('active', b.dataset.m === state.metric);
    b.addEventListener('click', () => {
      state.metric = b.dataset.m;
      el.querySelectorAll('#metricSeg button').forEach((x) => x.classList.toggle('active', x === b));
      update(true);
    });
  });
  el.querySelectorAll('#dateSeg button').forEach((b) => b.addEventListener('click', () => {
    state.dateIdx = +b.dataset.i;
    el.querySelectorAll('#dateSeg button').forEach((x) => x.classList.toggle('active', x === b));
    update();
  }));

  map.on('click', (p) => { if (p.name && fc(p.name, state.crop)) location.hash = '#/region/' + p.name; });

  function update(full = false, onlyDetails = false) {
    const cc = state.crop, i = state.dateIdx, c = crop(cc);
    const s = rfSummary(cc, i);
    const devMode = state.metric === 'dev';
    const dg = c.crop_code === '3060100' ? 1 : 2;
    el.querySelector('#dateNote').textContent = dateNote(i);

    if (!onlyDetails) {
      el.querySelector('#mapTitle').textContent = devMode
        ? `${c.name}: насколько урожай выше или ниже обычного (${dateWhat(i)})`
        : `${c.name}: ожидаемая урожайность, т/га (${dateWhat(i)})`;
      const data = [];
      for (const f of D.regions.features) {
        const ok = f.properties.okato, x = fc(ok, cc);
        if (!x) { data.push({ name: ok, value: null }); continue; }
        const d = x.by_date[i];
        data.push({ name: ok, value: devMode ? d.dev_trend_pct : d.p50 });
      }
      // шкала т/га — по квантилям всех дат (не прыгает при смене даты), % — симметрично
      const all = Object.values(D.forecast.regions).map((r) => r[cc]).filter(Boolean).flatMap((x) => x.by_date.map((q) => q.p50));
      const lo = devMode ? -20 : quantile(all, 0.05), hi = devMode ? 20 : quantile(all, 0.95);
      const stops = devMode ? divStops() : seqStops();
      el.querySelector('#legend').innerHTML = `<span>${devMode ? 'ниже обычного −20 %' : fmt(lo, 1) + ' т/га'}</span><span class="ramp" style="background:linear-gradient(90deg,${stops.join(',')})"></span><span>${devMode ? 'выше обычного +20 %' : fmt(hi, 1) + ' т/га'}</span>`;
      map.setOption({
        animationDurationUpdate: 600,
        tooltip: {
          trigger: 'item', confine: true, className: 'ec-tip',
          backgroundColor: css('--surface'), borderColor: css('--border'), textStyle: { color: css('--text'), fontSize: 12.5 },
          extraCssText: 'border-radius:12px;box-shadow:' + css('--shadow') + ';padding:10px 12px;',
          formatter: (p) => tipHtml(p.name, cc, i),
        },
        visualMap: { show: false, min: lo, max: hi, inRange: { color: stops }, calculable: false, seriesIndex: 0 },
        series: [{
          type: 'map', map: 'ru', nameProperty: 'okato', projection: P, roam: true, scaleLimit: { min: 1, max: 8 },
          layoutCenter: ['50%', '50%'], layoutSize: mapSize(), zoom: 1,
          itemStyle: { areaColor: css('--map-empty'), borderColor: css('--map-stroke'), borderWidth: 0.6 },
          emphasis: { label: { show: false }, itemStyle: { areaColor: css('--gold'), borderColor: css('--text'), borderWidth: 1 } },
          select: { disabled: true }, label: { show: false },
          data,
        }],
      }, full);

      // одно ключевое число
      el.querySelector('#kpis').innerHTML = `
        <div class="kpi hero">
          <div class="label"><span>Сбор по России · ${c.short.toLowerCase()}</span></div>
          <div class="value num">${fmtVol(s.vol)}</div>
          <div class="foot">${fmt(s.yieldAvg, dg)} т/га в среднем · 80 % интервал: ${fmtVol(s.lo)} — ${fmtVol(s.hi)}</div>
        </div>`;
    }

    if (!more.open) return;
    // Подробнее
    const rTotal = s.up + s.down;
    el.querySelector('#kpis2').innerHTML = `
      <div class="kpi"><div class="label">К ${s.prevYear ?? 'прошлому'} году</div><div class="value num">${deltaHtml(s.devPrev)}</div><div class="foot">${s.prevYear ? 'сбор тогда ' + fmtVol(s.prevVol) : 'нет данных'}</div></div>
      <div class="kpi"><div class="label">К обычному (тренд)</div><div class="value num">${deltaHtml(s.devTrend)}</div><div class="foot">обычно ${fmtVol(s.trendVol)}</div></div>
      <div class="kpi"><div class="label"><span>Регионов выше / ниже обычного</span></div>
        <div class="value num" style="display:flex;justify-content:space-between"><span style="color:var(--pos)">${s.up}</span><span style="color:var(--neg)">${s.down}</span></div>
        <div class="split-bar"><span style="width:${s.up / rTotal * 100}%;background:var(--div-5)"></span><span style="width:${s.down / rTotal * 100}%;background:var(--div-1)"></span></div></div>`;

    const top = s.regs.slice(0, 7), max = top[0]?.vol || 1;
    el.querySelector('#rank').innerHTML = top.map((r, k) => `<li data-ok="${r.ok}"><span class="n">${k + 1}</span>
      <div><div>${regionName(r.ok)}</div><div class="bar" style="width:${r.vol / max * 100}%;background:${c.color}"></div></div>
      <span class="v num">${fmtVol(r.vol)} <small style="color:${r.dev >= 0 ? 'var(--pos)' : 'var(--neg)'}">${fmtPct(r.dev, 0)}</small></span></li>`).join('');
    el.querySelectorAll('#rank li').forEach((li) => li.addEventListener('click', () => { location.hash = '#/region/' + li.dataset.ok; }));

    if (!refine) return;
    const ser = D.dates.map((_, k) => rfSummary(cc, k));
    const y = ser.map((q) => q.vol / q.area), ylo = ser.map((q) => q.lo / q.area), yhi = ser.map((q) => q.hi / q.area);
    const wlo = ser.map((q) => q.wlo / q.area), whi = ser.map((q) => q.whi / q.area);
    const tr = s.trendVol / s.area;
    const w0 = (yhi[0] - ylo[0]) / y[0] * 50, w1 = (yhi.at(-1) - ylo.at(-1)) / y.at(-1) * 50;
    el.querySelector('#refVerdict').textContent = `Чем позже дата, тем уже интервал: ±${fmt(w0, 0)} % на 1 мая и ±${fmt(w1, 0)} % по итогам сезона`;
    const gold = css('--gold'), brand = css('--brand-2');
    refine.setOption(opt({
      grid: { top: 30, bottom: 4, left: 4, right: 10 },
      legend: false,
      tooltip: { formatter: (ps) => { const k = ps[0].dataIndex; return `<b>${dateBtn(k)}</b><br>Ожидаем: ${fmt(y[k], 2)} т/га<br>80 % интервал: ${fmt(ylo[k], 2)}–${fmt(yhi[k], 2)}<br>только из-за погоды: ${fmt(wlo[k], 2)}–${fmt(whi[k], 2)}`; } },
      xAxis: { type: 'category', data: D.dates.map((d, k) => dateBtn(k)), boundaryGap: false },
      yAxis: { type: 'value', scale: true, name: 'т/га', axisLabel: { formatter: (v) => fmt(v, 1) } },
      series: [
        { type: 'line', data: ylo, stack: 'b', symbol: 'none', lineStyle: { opacity: 0 }, silent: true },
        { type: 'line', data: yhi.map((v, k) => v - ylo[k]), stack: 'b', symbol: 'none', lineStyle: { opacity: 0 }, areaStyle: { color: alpha(gold, 0.22) }, silent: true },
        { type: 'line', data: wlo, stack: 'w', symbol: 'none', lineStyle: { opacity: 0 }, silent: true },
        { type: 'line', data: whi.map((v, k) => v - wlo[k]), stack: 'w', symbol: 'none', lineStyle: { opacity: 0 }, areaStyle: { color: alpha(gold, 0.45) }, silent: true },
        { type: 'line', data: y, smooth: true, symbolSize: (v, p) => (p.dataIndex === i ? 12 : 6), lineStyle: { width: 3, color: brand }, itemStyle: { color: brand, borderColor: css('--surface'), borderWidth: 2 },
          markLine: { silent: true, symbol: 'none', data: [{ yAxis: tr, label: { formatter: 'обычно', position: 'insideStartTop', color: css('--text-3'), fontSize: 11 } }], lineStyle: { type: 'dashed', color: css('--text-3') } } },
      ],
    }), true);
  }
  update(true);
}

export function tipHtml(ok, cc, i) {
  const x = fc(ok, cc);
  const name = regionName(ok);
  if (!x) return `<div class="tip-title">${name}</div><div class="tip-row"><span>Нет данных по культуре</span></div>`;
  const d = x.by_date[i];
  const row = (k, v) => `<div class="tip-row"><span>${k}</span><b>${v}</b></div>`;
  return `<div class="tip-title">${name}</div>
    ${row(isFinalDate(i) ? 'Оценка' : 'Прогноз', fmt(d.p50, 2) + ' т/га')}
    ${row('Интервал 80 %', fmt(d.p10, 2) + '–' + fmt(d.p90, 2))}
    ${row('К обычному', fmtPct(d.dev_trend_pct))}
    ${row('Площадь 2025', fmt(x.area_kha, 1) + ' тыс. га')}
    ${row('Сбор', fmtVol(d.volume_kt))}`;
}
