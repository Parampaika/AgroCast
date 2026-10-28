// Экран «Карточка региона»: история + тренд + веер прогноза, факторы погоды, погода сезона, почвы.
import { D, crop, fc, hist, regionName, regionsAll } from './data.js';
import { cropPicker, bindCropPicker, dateSeg } from './overview.js';
import { state, fmt, fmtVol, fmtPct, deltaHtml, chart, opt, css, info, alpha, esc, dateNote, dateWhat, isFinalDate } from './util.js';

export function renderRegion(el) {
  let ok = state.region;
  if (!D.forecast.regions[ok]) ok = state.region = '03000000000';
  const avail = Object.keys(D.forecast.regions[ok]);
  if (!avail.includes(state.crop)) state.crop = avail[0];

  el.innerHTML = `
  <div class="page-head" style="margin-bottom:14px">
    <div>
      <div class="eyebrow">Регион · ${esc(D.regionBy[ok]?.fo || '')}</div>
      <div class="region-hero">
        <select class="select" id="regSel" aria-label="Регион">${regionsAll().map((r) => `<option value="${r}" ${r === ok ? 'selected' : ''}>${esc(regionName(r))}</option>`).join('')}</select>
      </div>
      <span class="frame">Прогноз — для региона в целом (среднее по хозяйствам), а не для отдельного поля.</span>
    </div>
    <div>${dateSeg('dateSeg', state.dateIdx)}</div>
  </div>
  <div class="toolbar" style="margin-bottom:14px" id="cropBar"></div>
  <p class="date-note" id="dNote" style="margin:0 0 14px"></p>
  <h2 class="verdict" id="rVerdict" style="font-size:18px;margin-bottom:12px"></h2>
  <div class="kpis" id="rk" style="grid-template-columns:repeat(auto-fit,minmax(170px,1fr));margin-bottom:18px"></div>
  <div class="card">
    <div class="card-head"><div><h3 id="histT"></h3><div class="sub">Линия — факт по годам, пунктир — обычный уровень (тренд), золотой веер — диапазон прогноза</div></div>
      ${info('История — ЕМИСС (все категории хозяйств); 2025 г. — оценка по сбору и посевной площади (итогов Росстата ещё нет).', 'Внешняя полоса веера — 80 % интервал с учётом погоды и ошибки модели; внутренняя — только разброс погоды.')}</div>
    <div class="chart lg" id="hist"></div>
  </div>
  <div class="tabs" id="tabs" role="tablist">
    <button data-t="why" class="active">Почему такой прогноз</button><button data-t="weather">Погода сезона</button><button data-t="soil">Почвы</button><button data-t="all">Все культуры региона</button>
  </div>
  <div class="tab-pane" data-p="why">
    <div class="card">
      <div class="card-head"><div><h3 id="drvT">Что повлияло на прогноз</h3><div class="sub">Вклад погоды сезона в отклонение от обычного уровня, п.п.</div></div>${info('Вклады считаются по аномалиям погоды сезона относительно нормы 2001–2021 и оценивают влияние факторов в модели.', 'Это связь по данным, а не доказанная причина.')}</div>
      <div class="chart" id="drv" style="height:340px"></div>
      <div class="factor-note" id="drvNote"></div>
    </div>
  </div>
  <div class="tab-pane" data-p="weather" hidden>
    <div class="grid g-3">
      <div class="card"><div class="card-head"><h3>Температура, °C</h3></div><div class="chart sm" id="wT"></div></div>
      <div class="card"><div class="card-head"><h3>Осадки, мм</h3></div><div class="chart sm" id="wP"></div></div>
      <div class="card"><div class="card-head"><h3>Влагообеспеченность (ГТК)</h3>${info('ГТК Селянинова: осадки за период, делённые на сумму температур. Ниже 0,7 — засуха, 1,0–1,5 — влаги достаточно.', 'Погода — ERA5, нормы — средние за 2001–2021.')}</div><div class="chart sm" id="wH"></div></div>
    </div>
  </div>
  <div class="tab-pane" data-p="soil" hidden><div class="card" id="soil"></div></div>
  <div class="tab-pane" data-p="all" hidden><div class="card" id="cropsTbl"></div></div>`;

  el.querySelector('#regSel').addEventListener('change', (e) => { location.hash = '#/region/' + e.target.value; });
  el.querySelectorAll('#dateSeg button').forEach((b) => b.addEventListener('click', () => {
    state.dateIdx = +b.dataset.i;
    el.querySelectorAll('#dateSeg button').forEach((x) => x.classList.toggle('active', x === b));
    draw();
  }));
  const drawCrops = () => {
    el.querySelector('#cropBar').innerHTML = cropPicker(state.crop, null, avail);
    bindCropPicker(el.querySelector('#cropBar'), (cc) => { state.crop = cc; drawCrops(); draw(); });
  };
  drawCrops();

  const hc = chart(el.querySelector('#hist')), dc = chart(el.querySelector('#drv'));
  let weatherDone = false;
  el.querySelectorAll('#tabs button').forEach((b) => b.addEventListener('click', () => {
    el.querySelectorAll('#tabs button').forEach((x) => x.classList.toggle('active', x === b));
    el.querySelectorAll('.tab-pane').forEach((pn) => { pn.hidden = pn.dataset.p !== b.dataset.t; });
    if (b.dataset.t === 'weather' && !weatherDone) { weatherDone = true; drawWeather(el, ok); }
    if (b.dataset.t === 'why') dc.resize();
  }));
  drawSoil(el, ok);

  function draw() {
    const cc = state.crop, c = crop(cc), f = fc(ok, cc), h = hist(ok, cc), i = state.dateIdx, d = f.by_date[i];
    const yi = D.history.years;
    const last = [...yi].reverse().find((y) => h.yield[yi.indexOf(y)] != null || h.yield_est[yi.indexOf(y)] != null);
    const lastY = h.yield[yi.indexOf(last)] ?? h.yield_est[yi.indexOf(last)];
    const dg = cc === '3060100' ? 1 : 2;
    const fcName = isFinalDate(i) ? 'Оценка по итогам сезона' : 'Прогноз';
    el.querySelector('#dNote').textContent = dateNote(i);
    const dv = d.dev_trend_pct;
    el.querySelector('#rVerdict').textContent = `${c.name}, ${regionName(ok)}: ${fmt(d.p50, dg)} т/га — ${Math.abs(dv) < 1 ? 'около обычного уровня' : fmt(Math.abs(dv), 0) + ' % ' + (dv > 0 ? 'выше' : 'ниже') + ' обычного'} (${dateWhat(i)})`;
    el.querySelector('#histT').textContent = `Урожайность 2008–2025 и ${isFinalDate(i) ? 'оценка' : 'прогноз'} на 2026`;
    el.querySelector('#rk').innerHTML = `
      <div class="kpi hero"><div class="label">${isFinalDate(i) ? 'Оценка' : 'Прогноз'}, т/га</div><div class="value num">${fmt(d.p50, dg)}</div><div class="foot">80 % интервал: ${fmt(d.p10, dg)}–${fmt(d.p90, dg)}</div></div>
      <div class="kpi"><div class="label">К обычному уровню</div><div class="value">${deltaHtml(d.dev_trend_pct)}</div><div class="foot">обычно ${fmt(f.trend, dg)} т/га (тренд)</div></div>
      <div class="kpi"><div class="label">К ${last} году</div><div class="value">${deltaHtml((d.p50 / lastY - 1) * 100)}</div><div class="foot">тогда ${fmt(lastY, dg)} т/га${last === 2025 ? ' (оценка по сбору)' : ''}</div></div>
      <div class="kpi"><div class="label">Сбор по региону</div><div class="value num">${fmtVol(d.volume_kt)}</div><div class="foot">на ${fmt(f.area_kha, 1)} тыс. га (посевы 2025)</div></div>`;

    // история + веер
    const yrs = yi.map(String);
    const actual = yi.map((y, k) => h.yield[k] ?? null);
    const est = yi.map((y, k) => (h.yield[k] == null && h.yield_est[k] != null ? h.yield_est[k] : null));
    const s25 = yi.indexOf(2025), s26 = yi.indexOf(2026);
    const anchor = actual[s25] ?? est[s25] ?? actual[s25 - 1];
    const fan = (lo, hi) => yi.map((y, k) => (k === s25 ? [anchor, anchor] : k === s26 ? [lo, hi] : [null, null]));
    const outer = fan(d.p10, d.p90), inner = fan(d.w_lo, d.w_hi);
    const gold = css('--gold'), brand = css('--brand-2');
    const band = (arr, name, color) => [
      { name, type: 'line', data: arr.map((x) => x[0]), stack: name, symbol: 'none', lineStyle: { opacity: 0 }, silent: true, tooltip: { show: false } },
      { name, type: 'line', data: arr.map((x) => (x[0] == null ? null : x[1] - x[0])), stack: name, symbol: 'none', lineStyle: { opacity: 0 }, areaStyle: { color }, silent: true, tooltip: { show: false } },
    ];
    hc.setOption(opt({
      legend: { data: ['Факт', 'Оценка 2025', 'Обычный уровень', fcName] },
      tooltip: { formatter: (ps) => {
        const k = ps[0].dataIndex, y = yi[k];
        let s = `<b>${y}</b>`;
        if (actual[k] != null) s += `<br>Факт: ${fmt(actual[k], dg)} т/га`;
        if (est[k] != null) s += `<br>Оценка по сбору: ${fmt(est[k], dg)} т/га`;
        if (h.trend[k] != null) s += `<br>Обычный уровень: ${fmt(h.trend[k], dg)} т/га`;
        if (k === s26) s += `<br>${fcName}: <b>${fmt(d.p50, dg)}</b> (${fmt(d.p10, dg)}–${fmt(d.p90, dg)})`;
        return s;
      } },
      xAxis: { type: 'category', data: yrs, boundaryGap: false, min: yi.indexOf(2008), axisLabel: { interval: 2 } },
      yAxis: { type: 'value', name: 'т/га', min: (v) => Math.max(0, Math.floor(v.min * 0.8)), axisLabel: { formatter: (v) => fmt(v, cc === '3060100' ? 0 : 1) } },
      series: [
        ...band(outer, 'outer', alpha(gold, 0.22)),
        ...band(inner, 'inner', alpha(gold, 0.45)),
        { name: 'Факт', type: 'line', data: actual, symbol: 'circle', symbolSize: 6, lineStyle: { width: 2.5, color: brand }, itemStyle: { color: brand }, connectNulls: false },
        { name: 'Оценка 2025', type: 'line', data: est, symbol: 'emptyCircle', symbolSize: 8, lineStyle: { opacity: 0 }, itemStyle: { color: brand } },
        { name: 'Обычный уровень', type: 'line', data: h.trend.map((v, k) => (k >= 5 ? v : null)), symbol: 'none', lineStyle: { width: 1.5, type: 'dashed', color: css('--text-3') }, itemStyle: { color: css('--text-3') } },
        { name: fcName, type: 'line', data: yi.map((y, k) => (k === s25 ? anchor : k === s26 ? d.p50 : null)), symbol: 'circle', symbolSize: (v, p) => (p.dataIndex === s26 ? 13 : 0), lineStyle: { width: 2.5, type: [6, 4], color: css('--gold-2') }, itemStyle: { color: css('--gold'), borderColor: css('--surface'), borderWidth: 3 },
          label: { show: true, position: 'right', formatter: (p) => (p.dataIndex === s26 ? fmt(d.p50, dg) : ''), fontWeight: 800, color: css('--text') } },
      ],
    }), true);

    // факторы
    const drv = D.drivers.regions[ok]?.[cc] || [];
    const items = [...drv].reverse();
    const pos = css('--div-5'), neg = css('--div-1');
    dc.setOption(opt({
      grid: { left: 4, right: 40, top: 6, bottom: 4 },
      legend: false,
      tooltip: { trigger: 'item', formatter: (p) => { const x = items[p.dataIndex]; return `<b>${x.label}</b><br>Аномалия: ${fmtSignedU(x.anomaly, x.unit)}<br>Вклад: ${fmtPct(x.contrib_pct)} к урожайности`; } },
      xAxis: { type: 'value', splitNumber: 3, axisLabel: { formatter: (v) => fmtPct(v, 0), hideOverlap: true }, splitLine: { show: true, lineStyle: { color: css('--border'), type: [3, 4] } } },
      yAxis: { type: 'category', data: items.map((x) => x.label), axisLabel: { color: css('--text'), fontSize: 12.5, fontWeight: 600, width: 210, overflow: 'break' }, splitLine: { show: false } },
      series: [{ type: 'bar', barWidth: 16, data: items.map((x) => ({ value: x.contrib_pct, itemStyle: { color: x.contrib_pct >= 0 ? pos : neg, borderRadius: x.contrib_pct >= 0 ? [0, 6, 6, 0] : [6, 0, 0, 6] } })),
        label: { show: true, position: 'right', formatter: (p) => fmtPct(p.value, 1), color: css('--text-2'), fontSize: 11.5 } }],
    }), true);
    const sum = drv.reduce((s, x) => s + x.contrib_pct, 0);
    el.querySelector('#drvT').textContent = drv.length ? (sum >= 0 ? 'Погода сезона в основном помогла урожаю' : 'Погода сезона в основном помешала урожаю') : 'Что повлияло на прогноз';
    el.querySelector('#drvNote').innerHTML = drv.length
      ? `Сумма вкладов: <b>${fmtPct(sum)}</b>. Зелёный — погода помогла урожаю, коричневый — помешала.`
      : 'Для этой культуры в регионе факторы не рассчитаны.';

    // таблица по всем культурам региона
    el.querySelector('#cropsTbl').innerHTML = `<div class="card-head"><h3>Все культуры региона · ${dateWhat(i)}</h3></div>
      <div class="table-wrap"><table class="table"><thead><tr><th>Культура</th><th>т/га</th><th>к обычному</th><th>площадь, тыс. га</th><th>сбор</th></tr></thead><tbody>
      ${avail.map((k) => { const ff = fc(ok, k), dd = ff.by_date[i], cr = crop(k); return `<tr data-cc="${k}" style="cursor:pointer">
        <td><div class="crop-cell"><span class="ico" style="color:${cr.color};background:${alpha(cr.color, .14)}">${iconOf(cr)}</span>${cr.short}</div></td>
        <td class="num"><b>${fmt(dd.p50, k === '3060100' ? 1 : 2)}</b></td><td>${deltaHtml(dd.dev_trend_pct, 0)}</td><td class="num">${fmt(ff.area_kha, 1)}</td><td class="num">${fmtVol(dd.volume_kt)}</td></tr>`; }).join('')}
      </tbody></table></div>`;
    el.querySelectorAll('#cropsTbl tr[data-cc]').forEach((tr) => tr.addEventListener('click', () => { state.crop = tr.dataset.cc; drawCrops(); draw(); }));
  }
  draw();
}

import { cropIcon as iconOf } from './icons.js';
const fmtSignedU = (v, u) => (v > 0 ? '+' : v < 0 ? '−' : '') + fmt(Math.abs(v), Math.abs(v) < 1 ? 2 : 1) + ' ' + u;

function drawWeather(el, ok) {
  const w = D.weather_season.regions[ok];
  if (!w) return;
  const m = D.weather_season.months.map((x, k) => (k === 12 || k === 13 ? x + '*' : x));
  const brand = css('--brand-2'), gold = css('--gold-2'), muted = css('--text-3');
  const mk = (id, v, kind) => {
    const c = chart(el.querySelector(id));
    const fact = w[v].fact, norm = w[v].norm;
    c.setOption(opt({
      grid: { top: 30, left: 4, right: 6, bottom: 4 },
      legend: { data: ['2026', 'Норма'], right: 0 },
      tooltip: { valueFormatter: (x) => (x == null ? '—' : fmt(x, v === 'htc' ? 2 : 1)) },
      xAxis: { type: 'category', data: m, axisLabel: { interval: 1, fontSize: 10.5 } },
      yAxis: { type: 'value', axisLabel: { formatter: (x) => fmt(x, v === 'htc' ? 1 : 0) } },
      series: kind === 'bar'
        ? [{ name: '2026', type: 'bar', data: fact, barWidth: '55%', itemStyle: { color: brand, borderRadius: [4, 4, 0, 0] } },
           { name: 'Норма', type: 'line', data: norm, symbol: 'circle', symbolSize: 5, lineStyle: { color: gold, width: 2 }, itemStyle: { color: gold } }]
        : [{ name: '2026', type: 'line', data: fact, smooth: true, symbol: 'circle', symbolSize: 5, lineStyle: { color: v === 'htc' ? brand : gold, width: 2.5 }, itemStyle: { color: v === 'htc' ? brand : gold }, areaStyle: v === 'htc' ? { color: alpha(brand, .12) } : undefined, connectNulls: false,
            markArea: v === 'htc' ? { silent: true, itemStyle: { color: alpha(css('--neg'), .08) }, data: [[{ yAxis: 0 }, { yAxis: 0.7 }]] } : undefined },
           { name: 'Норма', type: 'line', data: norm, smooth: true, symbol: 'none', lineStyle: { color: muted, width: 1.5, type: 'dashed' }, itemStyle: { color: muted } }],
    }));
  };
  mk('#wT', 'tmean', 'line');
  mk('#wP', 'prec', 'bar');
  mk('#wH', 'htc', 'line');
}

const WRB = { Chernozems: 'Чернозёмы', Kastanozems: 'Каштановые', Phaeozems: 'Тёмно-серые лесные (феоземы)', Luvisols: 'Серые лесные (лювисоли)', Retisols: 'Дерново-подзолистые (ретисоли)', Podzols: 'Подзолы', Albeluvisols: 'Дерново-подзолистые', Cambisols: 'Бурые (камбисоли)', Gleysols: 'Глеевые', Histosols: 'Торфяные', Solonetz: 'Солонцы', Calcisols: 'Карбонатные', Fluvisols: 'Аллювиальные', Cryosols: 'Мерзлотные', Regosols: 'Слаборазвитые', Arenosols: 'Песчаные', Umbrisols: 'Умбрисоли', Planosols: 'Планосоли', Stagnosols: 'Стагнозёмы', Leptosols: 'Маломощные' };

function drawSoil(el, ok) {
  const s = D.soils.regions[ok];
  const box = el.querySelector('#soil');
  if (!s) { box.innerHTML = '<div class="empty">Нет данных о почвах</div>'; return; }
  const cl = css('--div-1'), si = css('--gold'), sa = css('--div-2');
  const ph = s.ph;
  const phTxt = ph < 5.5 ? 'кислые' : ph < 6.5 ? 'слабокислые' : ph < 7.5 ? 'нейтральные' : 'щелочные';
  box.innerHTML = `<div class="card-head"><h3>Почвы пашни региона</h3>${info('Почвы — SoilGrids 2.0 (ISRIC), слой 0–30 см, среднее по точкам пашни региона.', 'Это региональные средние, а не данные вашего поля.')}</div>
    <div style="font-size:20px;font-weight:800;letter-spacing:-.01em">${esc(WRB[s.wrb] || s.wrb || '—')}</div>
    <div class="chip-note">доминирующий класс WRB на ${fmt((s.wrb_share || 0) * 100, 0)} % точек пашни</div>
    <div style="margin-top:14px" class="field-label">Гранулометрия, 0–30 см</div>
    <div class="texture"><span style="width:${s.clay}%;background:${cl}"></span><span style="width:${s.silt}%;background:${si}"></span><span style="width:${s.sand}%;background:${sa}"></span></div>
    <div class="texture-legend"><span><i style="background:${cl}"></i>глина ${fmt(s.clay, 0)} %</span><span><i style="background:${si}"></i>пыль ${fmt(s.silt, 0)} %</span><span><i style="background:${sa}"></i>песок ${fmt(s.sand, 0)} %</span></div>
    <div class="soil-grid" style="margin-top:14px">
      <div class="kv"><span>pH (H₂O)</span><b>${fmt(ph, 1)}</b> <small class="chip-note">${phTxt}</small></div>
      <div class="kv"><span>Органический углерод</span><b>${fmt(s.soc, 0)}</b> <small class="chip-note">г/кг</small></div>
      <div class="kv"><span>Запас углерода 0–30 см</span><b>${fmt(s.ocs, 0)}</b> <small class="chip-note">т/га</small></div>
      <div class="kv"><span>Азот общий</span><b>${fmt(s.nitrogen, 1)}</b> <small class="chip-note">г/кг</small></div>
    </div>`;
}
