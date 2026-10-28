// Экран «Калькулятор фермера»: участок, структура посевов, поправки → т/га, объём, выручка, затраты, маржа.
import { D, crop, regionName, regionsAll } from './data.js';
import { cropIcon } from './icons.js';
import { calcState, newCalc, cropEcon, ADJ, multipliers } from './econ.js';
import { state, fmt, fmtMoney, chart, opt, css, demoBadge, realBadge, alpha, esc } from './util.js';

export function planEditor(cfg, onChange) {
  const crops = Object.keys(D.forecast.regions[cfg.region]);
  const html = crops.map((cc) => {
    const c = crop(cc), v = Math.round((cfg.plan[cc] || 0) * 100);
    return `<div class="plan-row ${v ? '' : 'off'}" data-cc="${cc}">
      <span class="ico" style="color:${c.color};background:${alpha(c.color, .14)}">${cropIcon(c)}</span>
      <div><div class="name">${c.short}<small>макс. ${Math.round(c.max_share * 100)} %</small></div>
      <input type="range" min="0" max="100" step="1" value="${v}" style="--p:${v}%" aria-label="Доля ${c.short}"></div>
      <span class="pct num">${v} %</span></div>`;
  }).join('');
  const bind = (root) => {
    root.querySelectorAll('.plan-row input').forEach((inp) => inp.addEventListener('input', () => {
      const cc = inp.closest('.plan-row').dataset.cc;
      setShare(cfg, cc, +inp.value / 100);
      sync(root, cfg);
      onChange();
    }));
  };
  return { html, bind };
}
function sync(root, cfg) {
  root.querySelectorAll('.plan-row').forEach((row) => {
    const v = Math.round((cfg.plan[row.dataset.cc] || 0) * 100);
    const inp = row.querySelector('input');
    if (document.activeElement !== inp) inp.value = v;
    inp.style.setProperty('--p', inp.value + '%');
    row.querySelector('.pct').textContent = v + ' %';
    row.classList.toggle('off', !v);
  });
}
// Меняем долю одной культуры, остальные пропорционально, сумма = 100 %
export function setShare(cfg, cc, v) {
  const others = Object.keys(cfg.plan).filter((k) => k !== cc);
  const rest = others.reduce((s, k) => s + (cfg.plan[k] || 0), 0);
  if (rest <= 1e-9) {
    v = Math.min(v, 1);
    const free = Object.keys(D.forecast.regions[cfg.region]).filter((k) => k !== cc);
    cfg.plan[cc] = v;
    if (v < 1 && free.length) cfg.plan[free[0]] = 1 - v;
    return;
  }
  cfg.plan[cc] = v;
  for (const k of others) cfg.plan[k] = (cfg.plan[k] || 0) * (1 - v) / rest;
}

const selectHtml = (id, list, val, label, hint) => `<div class="field"><label for="${id}">${label}</label>
  <select class="select" id="${id}">${list.map((x) => `<option value="${x.id}" ${x.id === val ? 'selected' : ''}>${esc(x.label)}</option>`).join('')}</select>${hint ? `<span class="hint">${hint}</span>` : ''}</div>`;

export function renderCalc(el) {
  const cfg = calcState();
  const a = ADJ();
  el.innerHTML = `
  <div class="page-head">
    <div>
      <div class="eyebrow">Калькулятор фермера</div>
      <h1>Сколько соберёте и сколько заработаете</h1>
      <p class="lead">Введите участок и план посевов — получите прогноз урожайности в т/га, общий объём по каждой культуре, выручку, затраты и маржу с диапазоном «плохой — обычный — хороший год».</p>
    </div>
    <a class="btn" href="#/optimize"><svg viewBox="0 0 24 24"><path d="M5 15l4-4 3 3 7-7"/><path d="M15 7h4v4"/></svg>Оптимизировать план</a>
  </div>
  <div class="grid g-calc">
    <div class="card stack" style="gap:16px">
      <div class="card-head" style="margin:0"><h3>Участок</h3></div>
      <div class="field"><label for="cReg">Регион</label><select class="select" id="cReg">${regionsAll().map((r) => `<option value="${r}" ${r === cfg.region ? 'selected' : ''}>${esc(regionName(r))}</option>`).join('')}</select></div>
      <div class="grid" style="grid-template-columns:1fr 1fr;gap:12px">
        <div class="field"><label for="cArea">Площадь пашни, га</label><input class="input num" id="cArea" type="number" min="1" max="1000000" step="10" value="${cfg.area}"></div>
        <div class="field"><label for="cDate">Дата прогноза</label><select class="select" id="cDate">${D.dates.map((d, i) => `<option value="${i}" ${i === cfg.dateIdx ? 'selected' : ''}>${d.label}</option>`).join('')}</select></div>
      </div>
      <div>
        <div class="card-head" style="margin:4px 0 8px"><span class="field-label">Структура посевов</span><button class="btn ghost" id="cReset" style="padding:5px 10px;font-size:12.5px">Как в регионе</button></div>
        <div class="plan-rows" id="plan"></div>
      </div>
      <div class="card-head" style="margin:6px 0 0"><h3>Поправки участка</h3><span class="badge-demo" title="Открытых данных о сорте и агротехнике по полям нет: это пользовательские поправки, они масштабируют прогноз модели">поправки пользователя</span></div>
      ${selectHtml('cSoil', a.soil, cfg.soil, 'Почва участка относительно региона')}
      ${selectHtml('cVar', a.variety, cfg.variety, 'Сорт / гибрид')}
      ${selectHtml('cTech', a.tech, cfg.tech, 'Агротехника')}
      <div class="chip-note" id="multNote"></div>
    </div>
    <div class="stack">
      <div class="kpis" id="cK" style="grid-template-columns:repeat(auto-fit,minmax(180px,1fr))"></div>
      <div class="card">
        <div class="card-head"><div><h3>Прогноз по культурам</h3><div class="sub" id="cSub"></div></div>${realBadge('цены — ЕМИСС, затраты — допущения', 'Прогноз урожайности — итоговая модель; цены — ЕМИСС 57693; затраты на гектар — допущения по открытым обзорам отрасли, не норматив')}</div>
        <div class="table-wrap" id="cTbl"></div>
      </div>
      <div class="grid g-2">
        <div class="card"><div class="card-head"><h3>Маржа по культурам</h3><span class="chip-note">диапазон p10–p90</span></div><div class="chart" id="cMargin"></div></div>
        <div class="card"><div class="card-head"><h3>Плохой, обычный и хороший год</h3></div><div class="scen" id="cScen"></div>
          <p class="chip-note" style="margin:12px 0 0">Плохой год — урожайность всех культур на нижней границе 80 % интервала (p10), хороший — на верхней (p90). Цены — средние производителей за январь–сентябрь 2026 (ЕМИСС), затраты на гектар — допущение.</p></div>
      </div>
    </div>
  </div>`;

  const marginChart = chart(el.querySelector('#cMargin'));
  const editor = () => {
    const ed = planEditor(cfg, update);
    el.querySelector('#plan').innerHTML = ed.html + `<div class="sum-line"><span>Итого</span><b>100 %</b></div>`;
    ed.bind(el.querySelector('#plan'));
  };
  editor();

  el.querySelector('#cReg').addEventListener('change', (e) => {
    const area = cfg.area;
    Object.assign(cfg, newCalc(e.target.value), { area, soil: cfg.soil, variety: cfg.variety, tech: cfg.tech, dateIdx: cfg.dateIdx });
    state.region = cfg.region;
    editor(); update();
  });
  el.querySelector('#cReset').addEventListener('click', () => {
    Object.assign(cfg, { plan: newCalc(cfg.region).plan }); editor(); update();
  });
  el.querySelector('#cArea').addEventListener('input', (e) => { const v = +e.target.value; if (v > 0) { cfg.area = Math.min(v, 1e6); update(); } });
  el.querySelector('#cDate').addEventListener('change', (e) => { cfg.dateIdx = +e.target.value; update(); });
  for (const [id, key] of [['cSoil', 'soil'], ['cVar', 'variety'], ['cTech', 'tech']]) {
    el.querySelector('#' + id).addEventListener('change', (e) => { cfg[key] = e.target.value; update(); });
  }

  function update() {
    const { rows, tot } = cropEcon(cfg);
    const m = multipliers(cfg);
    el.querySelector('#multNote').innerHTML = `Итоговые множители: урожайность ×${fmt(m.y, 2)}, затраты ×${fmt(m.c, 2)}${m.risk !== 1 ? `, разброс ×${fmt(m.risk, 2)}` : ''}.`;
    el.querySelector('#cSub').textContent = `${regionName(cfg.region)} · ${fmt(cfg.area, 0)} га · прогноз на ${D.dates[cfg.dateIdx].label.toLowerCase()}`;
    const volT = rows.reduce((s, r) => s + r.vol, 0);
    const marginHa = tot.margin / cfg.area;
    el.querySelector('#cK').innerHTML = `
      <div class="kpi hero"><div class="label">Ожидаемая маржа</div><div class="value num">${fmtMoney(tot.margin)}</div><div class="foot">${fmt(marginHa / 1000, 1)} тыс. ₽ с гектара</div></div>
      <div class="kpi"><div class="label">Выручка</div><div class="value num">${fmtMoney(tot.revenue)}</div><div class="foot">рентабельность ${fmt(tot.margin / tot.cost * 100, 0)} %</div></div>
      <div class="kpi"><div class="label">Затраты <span class="badge-demo" title="Допущение: полные затраты на 1 га по культуре">допущение</span></div><div class="value num">${fmtMoney(tot.cost)}</div><div class="foot">${fmt(tot.cost / cfg.area / 1000, 1)} тыс. ₽/га</div></div>
      <div class="kpi"><div class="label">Общий сбор</div><div class="value num">${fmt(volT, 0)}<small>т</small></div><div class="foot">${rows.length} культур${rows.length === 1 ? 'а' : rows.length < 5 ? 'ы' : ''}</div></div>`;

    el.querySelector('#cTbl').innerHTML = `<table class="table"><thead><tr><th>Культура</th><th>Площадь, га</th><th>т/га</th><th>p10–p90</th><th>Объём, т</th><th>Цена, ₽/т</th><th>Выручка</th><th>Затраты</th><th>Маржа</th></tr></thead><tbody>
      ${rows.map((r) => { const c = crop(r.cc), dg = r.cc === '3060100' ? 1 : 2; return `<tr>
        <td><div class="crop-cell"><span class="ico" style="color:${c.color};background:${alpha(c.color, .14)}">${cropIcon(c)}</span>${c.short}</div></td>
        <td class="num">${fmt(r.ha, 0)}</td><td class="num"><b>${fmt(r.y.p50, dg)}</b></td><td class="num muted">${fmt(r.y.p10, dg)}–${fmt(r.y.p90, dg)}</td>
        <td class="num"><b>${fmt(r.vol, 0)}</b></td><td class="num">${fmt(r.price, 0)}</td><td class="num">${fmtMoney(r.revenue)}</td><td class="num">${fmtMoney(r.cost)}</td>
        <td class="num" style="color:${r.margin >= 0 ? 'var(--pos)' : 'var(--neg)'}"><b>${fmtMoney(r.margin)}</b></td></tr>`; }).join('')}
      </tbody><tfoot><tr><td>Итого</td><td class="num">${fmt(cfg.area, 0)}</td><td></td><td></td><td class="num">${fmt(volT, 0)}</td><td></td><td class="num">${fmtMoney(tot.revenue)}</td><td class="num">${fmtMoney(tot.cost)}</td><td class="num">${fmtMoney(tot.margin)}</td></tr></tfoot></table>`;

    el.querySelector('#cScen').innerHTML = `
      <div class="bad"><div class="t">🌵 Плохой год</div><div class="v num">${fmtMoney(tot.lo)}</div><div class="f">маржа при p10</div></div>
      <div><div class="t">🌤 Обычный год</div><div class="v num">${fmtMoney(tot.margin)}</div><div class="f">маржа при p50</div></div>
      <div class="good"><div class="t">🌧 Хороший год</div><div class="v num">${fmtMoney(tot.hi)}</div><div class="f">маржа при p90</div></div>`;

    const names = rows.map((r) => crop(r.cc).short);
    marginChart.setOption(opt({
      grid: { left: 4, right: 10, top: 10, bottom: 4 }, legend: false,
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (ps) => { const r = rows[ps[0].dataIndex]; return `<b>${crop(r.cc).name}</b><br>Маржа: ${fmtMoney(r.margin)}<br>p10–p90: ${fmtMoney(r.marginLo)} … ${fmtMoney(r.marginHi)}`; } },
      xAxis: { type: 'category', data: names, axisLabel: { interval: 0, fontSize: 11 } },
      yAxis: { type: 'value', axisLabel: { formatter: (v) => fmt(v / 1e6, 0) + ' млн' } },
      series: [
        { type: 'bar', barWidth: '46%', data: rows.map((r) => ({ value: r.margin, itemStyle: { color: crop(r.cc).color, borderRadius: r.margin >= 0 ? [6, 6, 0, 0] : [0, 0, 6, 6] } })) },
        { type: 'custom', renderItem: (p, api) => {
          const lo = api.coord([api.value(0), api.value(1)]), hi = api.coord([api.value(0), api.value(2)]);
          const st = { stroke: css('--text'), lineWidth: 1.5 };
          return { type: 'group', children: [
            { type: 'line', shape: { x1: lo[0], y1: lo[1], x2: hi[0], y2: hi[1] }, style: st },
            { type: 'line', shape: { x1: lo[0] - 6, y1: lo[1], x2: lo[0] + 6, y2: lo[1] }, style: st },
            { type: 'line', shape: { x1: hi[0] - 6, y1: hi[1], x2: hi[0] + 6, y2: hi[1] }, style: st }] };
        }, data: rows.map((r, k) => [k, r.marginLo, r.marginHi]), z: 10 },
      ],
    }), true);
  }
  update();
}
