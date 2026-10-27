// Экран «Обзор»: карта России, переключатель культуры, шкала дат прогноза, KPI по РФ.
import { D, crop, fc, regionName, rfSummary } from './data.js';
import { cropIcon } from './icons.js';
import { state, fmt, fmtVol, fmtPct, deltaHtml, chart, opt, css, demoBadge, seqStops, divStops, quantile, alpha } from './util.js';

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

export function renderOverview(el) {
  ensureMap();
  el.innerHTML = `
  <div class="page-head">
    <div>
      <div class="eyebrow">Сезон 2026 · прогноз по субъектам РФ</div>
      <h1>Где урожай будет выше тренда</h1>
      <p class="lead">Прогноз урожайности по 80+ регионам: точка, честный интервал и то, как он уточняется с 1 мая до конца сезона по мере того, как становится известна погода.</p>
    </div>
    <div class="seg" id="metricSeg">
      <button data-m="yield">Урожайность, т/га</button><button data-m="dev">К тренду, %</button>
    </div>
  </div>
  <div class="toolbar" style="margin-bottom:16px" id="cropBar"></div>
  <div class="grid g-overview">
    <div class="card map-card">
      <div class="card-head">
        <div><h2 id="mapTitle"></h2><div class="sub">Наведите на регион — подробности, клик — карточка региона</div></div>
        <div class="legend" id="legend"></div>
      </div>
      <div class="map-wrap"><div class="map" id="map"></div></div>
      <div class="timeline">
        <button class="play" id="play" aria-label="Проиграть уточнение прогноза"><svg viewBox="0 0 24 24"><path d="M7 4.5v15l13-7.5z"/></svg></button>
        <div class="steps" id="steps"></div>
      </div>
    </div>
    <div class="stack">
      <div class="kpis" id="kpis"></div>
      <div class="card">
        <div class="card-head"><div><h3>Как уточняется прогноз по РФ</h3><div class="sub">Светлая полоса — 80 % интервал, тёмная — разброс погоды</div></div>${demoBadge()}</div>
        <div class="chart sm" id="refine"></div>
      </div>
      <div class="card">
        <div class="card-head"><h3>Крупнейшие регионы по сбору</h3></div>
        <ul class="rank-list" id="rank"></ul>
      </div>
    </div>
  </div>
  <p class="foot-note">Площади посева — 2025 г. (ЕМИСС). Прогноз на сезон 2026 — заглушка на основе тренда и предварительной модели «тренд × погода»; интервал — 80 % (p10–p90).</p>`;

  const mapEl = el.querySelector('#map');
  const map = chart(mapEl);
  // Размер карты: по ширине контейнера (Россия примерно вдвое шире своей высоты)
  const mapSize = () => Math.round(Math.min(mapEl.clientWidth * 0.9, mapEl.clientHeight * 1.7));
  new ResizeObserver(() => { if (!map.isDisposed() && map.getOption()?.series?.length) map.setOption({ series: [{ layoutSize: mapSize() }] }); }).observe(mapEl);
  const refine = chart(el.querySelector('#refine'));

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

  const steps = el.querySelector('#steps');
  steps.innerHTML = `<div class="progress"></div>` + D.dates.map((d, i) => `<button class="step" data-i="${i}"><span class="dot"></span>${d.label}</button>`).join('');
  steps.querySelectorAll('.step').forEach((s) => s.addEventListener('click', () => { stopPlay(); state.dateIdx = +s.dataset.i; update(); }));

  let timer = null;
  const playBtn = el.querySelector('#play');
  const stopPlay = () => { clearInterval(timer); timer = null; playBtn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M7 4.5v15l13-7.5z"/></svg>'; };
  playBtn.addEventListener('click', () => {
    if (timer) return stopPlay();
    state.dateIdx = 0; update();
    playBtn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M6 4h4v16H6zM14 4h4v16h-4z"/></svg>';
    timer = setInterval(() => {
      if (!document.body.contains(playBtn)) return clearInterval(timer);
      if (state.dateIdx >= D.dates.length - 1) return stopPlay();
      state.dateIdx++; update();
    }, 1300);
  });

  map.on('click', (p) => { if (p.name && fc(p.name, state.crop)) location.hash = '#/region/' + p.name; });

  function update(full = false) {
    const cc = state.crop, i = state.dateIdx, c = crop(cc);
    // шкала дат
    steps.querySelectorAll('.step').forEach((s, k) => { s.classList.toggle('active', k === i); s.classList.toggle('passed', k < i); });
    steps.querySelector('.progress').style.width = (i / (D.dates.length - 1)) * 80 + '%';

    const devMode = state.metric === 'dev';
    el.querySelector('#mapTitle').textContent = `${c.name}: ${devMode ? 'отклонение от тренда' : 'прогноз урожайности'} на ${D.dates[i].label.toLowerCase()}`;
    const data = [];
    for (const f of D.regions.features) {
      const ok = f.properties.okato, x = fc(ok, cc);
      if (!x) { data.push({ name: ok, value: null }); continue; }
      const d = x.by_date[i];
      const v = devMode ? d.dev_trend_pct : d.p50;
      data.push({ name: ok, value: v });
    }
    // шкала: т/га — по квантилям всех дат (не прыгает при смене даты), % — симметрично
    const all = Object.values(D.forecast.regions).map((r) => r[cc]).filter(Boolean).flatMap((x) => x.by_date.map((q) => q.p50));
    const lo = devMode ? -20 : quantile(all, 0.05), hi = devMode ? 20 : quantile(all, 0.95);
    const stops = devMode ? divStops() : seqStops();
    const unit = devMode ? '%' : 'т/га';
    el.querySelector('#legend').innerHTML = `<span>${devMode ? '−20 %' : fmt(lo, 1)}</span><span class="ramp" style="background:linear-gradient(90deg,${stops.join(',')})"></span><span>${devMode ? '+20 %' : fmt(hi, 1) + ' т/га'}</span>${demoBadge()}`;

    const mapOpt = {
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
    };
    map.setOption(mapOpt, full);

    // KPI
    const s = rfSummary(cc, i);
    const rTotal = s.up + s.down;
    el.querySelector('#kpis').innerHTML = `
      <div class="kpi hero wide">
        <div class="label"><span>Прогноз сбора по РФ · ${c.short.toLowerCase()}</span>${demoBadge()}</div>
        <div class="value num">${fmtVol(s.vol)}</div>
        <div class="foot">80 % интервал: ${fmtVol(s.lo)} — ${fmtVol(s.hi)} · ${fmt(s.yieldAvg, c.crop_code === '3060100' ? 1 : 2)} т/га в среднем</div>
      </div>
      <div class="kpi"><div class="label">К ${s.prevYear ?? 'прошлому'} году</div><div class="value num">${deltaHtml(s.devPrev)}</div><div class="foot">${s.prevYear ? 'сбор ' + fmtVol(s.prevVol) : 'нет данных'}</div></div>
      <div class="kpi"><div class="label">К тренду</div><div class="value num">${deltaHtml(s.devTrend)}</div><div class="foot">тренд ${fmtVol(s.trendVol)}</div></div>
      <div class="kpi wide"><div class="label"><span>Регионы выше / ниже тренда</span><span>${rTotal} с данными</span></div>
        <div class="value num" style="display:flex;justify-content:space-between"><span style="color:var(--pos)">${s.up}</span><span style="color:var(--neg)">${s.down}</span></div>
        <div class="split-bar"><span style="width:${s.up / rTotal * 100}%;background:var(--div-5)"></span><span style="width:${s.down / rTotal * 100}%;background:var(--div-1)"></span></div></div>`;

    // ранжирование
    const top = s.regs.slice(0, 7), max = top[0]?.vol || 1;
    el.querySelector('#rank').innerHTML = top.map((r, k) => `<li data-ok="${r.ok}"><span class="n">${k + 1}</span>
      <div><div>${regionName(r.ok)}</div><div class="bar" style="width:${r.vol / max * 100}%;background:${c.color}"></div></div>
      <span class="v num">${fmtVol(r.vol)} <small style="color:${r.dev >= 0 ? 'var(--pos)' : 'var(--neg)'}">${fmtPct(r.dev, 0)}</small></span></li>`).join('');
    el.querySelectorAll('#rank li').forEach((li) => li.addEventListener('click', () => { location.hash = '#/region/' + li.dataset.ok; }));

    // уточнение прогноза по датам
    const ser = D.dates.map((_, k) => rfSummary(cc, k));
    const y = ser.map((q) => q.vol / q.area), ylo = ser.map((q) => q.lo / q.area), yhi = ser.map((q) => q.hi / q.area);
    const wlo = ser.map((q) => q.wlo / q.area), whi = ser.map((q) => q.whi / q.area);
    const tr = s.trendVol / s.area;
    const gold = css('--gold'), brand = css('--brand-2');
    refine.setOption(opt({
      grid: { top: 30, bottom: 4, left: 4, right: 10 },
      legend: false,
      tooltip: { formatter: (ps) => { const k = ps[0].dataIndex; return `<b>${D.dates[k].label}</b><br>p50: ${fmt(y[k], 2)} т/га<br>80 % интервал: ${fmt(ylo[k], 2)}–${fmt(yhi[k], 2)}<br>только погода: ${fmt(wlo[k], 2)}–${fmt(whi[k], 2)}`; } },
      xAxis: { type: 'category', data: D.dates.map((d) => d.label.replace('Конец сезона', 'Итог')), boundaryGap: false },
      yAxis: { type: 'value', scale: true, name: 'т/га', axisLabel: { formatter: (v) => fmt(v, 1) } },
      series: [
        { type: 'line', data: ylo, stack: 'b', symbol: 'none', lineStyle: { opacity: 0 }, silent: true },
        { type: 'line', data: yhi.map((v, k) => v - ylo[k]), stack: 'b', symbol: 'none', lineStyle: { opacity: 0 }, areaStyle: { color: alpha(gold, 0.2) }, silent: true },
        { type: 'line', data: wlo, stack: 'w', symbol: 'none', lineStyle: { opacity: 0 }, silent: true },
        { type: 'line', data: whi.map((v, k) => v - wlo[k]), stack: 'w', symbol: 'none', lineStyle: { opacity: 0 }, areaStyle: { color: alpha(gold, 0.45) }, silent: true },
        { type: 'line', data: y, smooth: true, symbolSize: (v, p) => (p.dataIndex === i ? 12 : 6), lineStyle: { width: 3, color: brand }, itemStyle: { color: brand, borderColor: css('--surface'), borderWidth: 2 },
          markLine: { silent: true, symbol: 'none', data: [{ yAxis: tr, label: { formatter: 'тренд', position: 'insideStartTop', color: css('--text-3'), fontSize: 11 } }], lineStyle: { type: 'dashed', color: css('--text-3') } } },
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
    ${row('Прогноз', fmt(d.p50, 2) + ' т/га')}
    ${row('Интервал 80 %', fmt(d.p10, 2) + '–' + fmt(d.p90, 2))}
    ${row('К тренду', fmtPct(d.dev_trend_pct))}
    ${row('Площадь 2025', fmt(x.area_kha, 1) + ' тыс. га')}
    ${row('Сбор', fmtVol(d.volume_kt))}`;
}
