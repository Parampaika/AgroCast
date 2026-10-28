// Экран «Калькулятор хозяйства»: план посевов в гектарах + поправки → урожайность, сбор, выручка, затраты, маржа.
import { D, crop, regionName, regionsAll } from './data.js';
import { cropIcon } from './icons.js';
import { calcState, newCalc, presetPlan, clearPlan, syncPlan, cropEcon, ADJ, multipliers } from './econ.js';
import { state, fmt, fmtMoney, chart, opt, css, info, alpha, esc, dateNote, isFinalDate } from './util.js';

const STEP = 50;

// Редактор плана в гектарах: у каждой культуры независимое поле; доли — только подпись
export function haEditor(cfg, onChange) {
  const crops = Object.keys(D.forecast.regions[cfg.region]);
  const rowsHtml = crops.map((cc) => {
    const c = crop(cc), v = Math.round(cfg.ha[cc] || 0);
    return `<div class="ha-row ${v ? '' : 'off'}" data-cc="${cc}">
      <span class="ico" style="color:${c.color};background:${alpha(c.color, .14)}">${cropIcon(c)}</span>
      <div class="nm">${c.short}<small class="sh"></small></div>
      <div class="stepper"><button type="button" data-d="-1" aria-label="Меньше">−</button><input type="number" inputmode="numeric" min="0" max="1000000" step="${STEP}" value="${v}" aria-label="${c.short}, га"><button type="button" data-d="1" aria-label="Больше">+</button></div>
    </div>`;
  }).join('');
  const html = `<div class="ha-rows" id="haRows">${rowsHtml}</div>
    <div class="ha-total"><span>Всего в плане</span><b class="num" id="haTotal"></b></div>`;
  const paint = (root) => {
    root.querySelectorAll('.ha-row').forEach((row) => {
      const cc = row.dataset.cc, v = Math.round(cfg.ha[cc] || 0);
      const inp = row.querySelector('input');
      if (document.activeElement !== inp) inp.value = v;
      row.classList.toggle('off', !v);
      row.querySelector('.sh').textContent = cfg.area > 0 && v ? `${fmt((v / cfg.area) * 100, 0)} % плана` : 'не сеем';
    });
    const t = root.querySelector('#haTotal');
    if (t) t.textContent = fmt(cfg.area, 0) + ' га';
  };
  const bind = (root) => {
    const set = (cc, v) => { cfg.ha[cc] = Math.max(0, Math.min(1e6, Math.round(+v || 0))); syncPlan(cfg); paint(root); onChange(); };
    root.querySelectorAll('.ha-row').forEach((row) => {
      const cc = row.dataset.cc, inp = row.querySelector('input');
      inp.addEventListener('input', () => set(cc, inp.value));
      row.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => set(cc, (cfg.ha[cc] || 0) + (+b.dataset.d) * STEP)));
    });
    paint(root);
  };
  return { html, bind, paint };
}
export const planEditor = haEditor;

const selectHtml = (id, list, val, label) => `<div class="field"><label for="${id}">${label}</label>
  <select class="select" id="${id}">${list.map((x) => `<option value="${x.id}" ${x.id === val ? 'selected' : ''}>${esc(x.label)}</option>`).join('')}</select></div>`;

export function renderCalc(el) {
  const cfg = calcState();
  const a = ADJ();
  el.innerHTML = `
  <div class="page-head">
    <div>
      <div class="eyebrow">Калькулятор хозяйства</div>
      <h1>Сколько соберёте и сколько заработаете</h1>
      <p class="lead">Задайте, сколько гектаров под какой культурой, — получите урожайность, сбор, выручку и маржу.</p>
      <span class="frame"><b>Как считаем:</b> берём прогноз по вашему региону в целом — так, как будто ваши поля урожайны, как в среднем по региону. Отличия ваших полей учтите поправками ниже.</span>
    </div>
    <a class="btn" href="#/optimize"><svg viewBox="0 0 24 24"><path d="M5 15l4-4 3 3 7-7"/><path d="M15 7h4v4"/></svg>Что посеять</a>
  </div>
  <div class="grid g-calc">
    <div class="card stack" style="gap:16px">
      <div class="card-head" style="margin:0"><h3>Ваше хозяйство</h3></div>
      <div class="field"><label for="cReg">Регион</label><select class="select" id="cReg">${regionsAll().map((r) => `<option value="${r}" ${r === cfg.region ? 'selected' : ''}>${esc(regionName(r))}</option>`).join('')}</select></div>
      <div class="field"><label for="cDate">На какую дату считать</label><select class="select" id="cDate">${D.dates.map((d, i) => `<option value="${i}" ${i === cfg.dateIdx ? 'selected' : ''}>${isFinalDate(i) ? 'Итог сезона (по фактической погоде)' : 'Прогноз на ' + d.label}</option>`).join('')}</select><span class="hint" id="cDateNote"></span></div>
      <div>
        <div class="card-head" style="margin:4px 0 8px"><span class="field-label">План посевов, га</span>
          <div class="preset-row"><button class="btn ghost" id="cPreset" type="button">Типовой план региона</button><button class="btn ghost" id="cClear" type="button">Очистить</button></div></div>
        <div id="plan"></div>
      </div>
      <div class="card-head" style="margin:6px 0 0"><h3>Поправки на ваши поля</h3>${info('Открытых данных о сорте, почве и агротехнике по отдельным полям нет, поэтому это ваши собственные поправки: они умножают прогноз региона.', 'Их можно оставить по умолчанию — тогда расчёт равен региональному.')}</div>
      ${selectHtml('cSoil', a.soil, cfg.soil, 'Почва относительно региона')}
      ${selectHtml('cVar', a.variety, cfg.variety, 'Сорт / гибрид')}
      ${selectHtml('cTech', a.tech, cfg.tech, 'Агротехника')}
      <div class="field"><label for="cAdj">Ваша поправка к урожайности, %</label><input class="input num" id="cAdj" type="number" min="-50" max="50" step="1" value="${cfg.adj || 0}"><span class="hint">Если по опыту ваши поля урожайнее (+) или слабее (−) средних по региону</span></div>
      <div class="chip-note" id="multNote"></div>
    </div>
    <div class="stack" id="out"></div>
  </div>`;

  const out = el.querySelector('#out');
  let marginChart = null;
  const ed = haEditor(cfg, () => update());
  el.querySelector('#plan').innerHTML = ed.html;
  ed.bind(el.querySelector('#plan'));

  const redraw = () => { ed.paint(el.querySelector('#plan')); update(); };
  el.querySelector('#cReg').addEventListener('change', (e) => {
    const keep = { soil: cfg.soil, variety: cfg.variety, tech: cfg.tech, adj: cfg.adj, dateIdx: cfg.dateIdx };
    Object.assign(cfg, newCalc(e.target.value, cfg.area > 0 ? cfg.area : 1000), keep);
    state.region = cfg.region;
    renderCalc(el.closest('.page') || el);   // перерисовать список культур региона
  });
  el.querySelector('#cPreset').addEventListener('click', () => { presetPlan(cfg, cfg.area > 0 ? cfg.area : 1000); redraw(); });
  el.querySelector('#cClear').addEventListener('click', () => { clearPlan(cfg); redraw(); });
  el.querySelector('#cDate').addEventListener('change', (e) => { cfg.dateIdx = +e.target.value; update(); });
  el.querySelector('#cAdj').addEventListener('input', (e) => { cfg.adj = Math.max(-50, Math.min(50, +e.target.value || 0)); update(); });
  for (const [id, key] of [['cSoil', 'soil'], ['cVar', 'variety'], ['cTech', 'tech']]) {
    el.querySelector('#' + id).addEventListener('change', (e) => { cfg[key] = e.target.value; update(); });
  }

  function update() {
    const m = multipliers(cfg);
    el.querySelector('#cDateNote').textContent = dateNote(cfg.dateIdx);
    el.querySelector('#multNote').textContent = `Итого к региональному прогнозу: урожайность ×${fmt(m.y, 2)}, затраты ×${fmt(m.c, 2)}.`;
    if (cfg.area <= 0) {
      out.innerHTML = `<div class="card empty-hint"><h3 style="margin-bottom:6px">Задайте план посевов</h3><p style="margin:0 0 14px">Введите гектары хотя бы по одной культуре — или возьмите типовой план региона.</p><button class="btn" id="cPreset2" type="button">Типовой план региона</button></div>`;
      out.querySelector('#cPreset2').addEventListener('click', () => { presetPlan(cfg, 1000); redraw(); });
      marginChart = null;
      return;
    }
    const { rows, tot } = cropEcon(cfg);
    const volT = rows.reduce((s, r) => s + r.vol, 0);
    if (!out.querySelector('#cK')) {
      out.innerHTML = `
      <div class="kpis" id="cK" style="grid-template-columns:repeat(auto-fit,minmax(170px,1fr))"></div>
      <div class="card">
        <div class="card-head"><div><h3>Что получится по культурам</h3><div class="sub" id="cSub"></div></div>${info('Урожайность — региональный прогноз итоговой модели с вашими поправками. Цены — средние цены производителей 2026 г. (ЕМИСС).', 'Затраты на гектар — допущения по открытым обзорам отрасли, не норматив.')}</div>
        <div class="table-wrap" id="cTbl"></div>
      </div>
      <div class="card"><div class="card-head"><h3 id="cScenTitle">Плохой, обычный и хороший год</h3></div><div class="scen" id="cScen"></div>
        <p class="chip-note" style="margin:12px 0 0">«Плохой» и «хороший» год — границы 80 % интервала: такой результат или хуже (лучше) бывает примерно раз в 10 лет.</p></div>
      <details class="more"><summary><span>Подробнее<small>маржа по культурам</small></span></summary><div class="more-body"><div class="chart" id="cMargin"></div></div></details>`;
      marginChart = null;
      out.querySelector('.more').addEventListener('toggle', (e) => { if (e.target.open) { marginChart = chart(out.querySelector('#cMargin')); update(); } });
    }
    out.querySelector('#cK').innerHTML = `
      <div class="kpi"><div class="label">Сбор</div><div class="value num">${fmt(volT, 0)}<small>т</small></div><div class="foot">${fmt(cfg.area, 0)} га · ${rows.length} культур${rows.length === 1 ? 'а' : rows.length < 5 ? 'ы' : ''}</div></div>
      <div class="kpi"><div class="label">Выручка</div><div class="value num">${fmtMoney(tot.revenue)}</div><div class="foot">затраты ${fmtMoney(tot.cost)} (допущение)</div></div>
      <div class="kpi hero"><div class="label">Маржа</div><div class="value num">${fmtMoney(tot.margin)}</div><div class="foot">${fmt(tot.margin / cfg.area / 1000, 1)} тыс. ₽ с гектара</div></div>`;
    out.querySelector('#cSub').textContent = `${regionName(cfg.region)} · ${fmt(cfg.area, 0)} га · ${isFinalDate(cfg.dateIdx) ? 'оценка по фактической погоде сезона' : 'прогноз на ' + D.dates[cfg.dateIdx].label}`;

    out.querySelector('#cTbl').innerHTML = `<table class="table"><thead><tr><th>Культура</th><th>Площадь, га</th><th>Урожайность, т/га</th><th>Сбор, т</th><th>Выручка</th><th>Маржа</th></tr></thead><tbody>
      ${rows.map((r) => { const c = crop(r.cc), dg = r.cc === '3060100' ? 1 : 2; return `<tr>
        <td><div class="crop-cell"><span class="ico" style="color:${c.color};background:${alpha(c.color, .14)}">${cropIcon(c)}</span>${c.short}</div></td>
        <td class="num">${fmt(r.ha, 0)}</td><td class="num"><b>${fmt(r.y.p50, dg)}</b><span class="sub-line">${fmt(r.y.p10, dg)}–${fmt(r.y.p90, dg)}</span></td>
        <td class="num"><b>${fmt(r.vol, 0)}</b></td><td class="num">${fmtMoney(r.revenue)}<span class="sub-line">${fmt(r.price, 0)} ₽/т</span></td>
        <td class="num" style="color:${r.margin >= 0 ? 'var(--pos)' : 'var(--neg)'}"><b>${fmtMoney(r.margin)}</b><span class="sub-line">затраты ${fmtMoney(r.cost)}</span></td></tr>`; }).join('')}
      </tbody><tfoot><tr><td>Итого</td><td class="num">${fmt(cfg.area, 0)}</td><td></td><td class="num">${fmt(volT, 0)}</td><td class="num">${fmtMoney(tot.revenue)}</td><td class="num">${fmtMoney(tot.margin)}<span class="sub-line">затраты ${fmtMoney(tot.cost)}</span></td></tr></tfoot></table>`;

    out.querySelector('#cScen').innerHTML = `
      <div class="bad"><div class="t">Плохой год</div><div class="v num">${fmtMoney(tot.lo)}</div><div class="f">маржа, раз в ~10 лет хуже</div></div>
      <div><div class="t">Обычный год</div><div class="v num">${fmtMoney(tot.margin)}</div><div class="f">ожидаемая маржа</div></div>
      <div class="good"><div class="t">Хороший год</div><div class="v num">${fmtMoney(tot.hi)}</div><div class="f">маржа, раз в ~10 лет лучше</div></div>`;

    if (marginChart) {
      marginChart.setOption(opt({
        grid: { left: 4, right: 10, top: 10, bottom: 4 }, legend: false,
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (ps) => { const r = rows[ps[0].dataIndex]; return `<b>${crop(r.cc).name}</b><br>Маржа: ${fmtMoney(r.margin)}<br>плохой – хороший год: ${fmtMoney(r.marginLo)} … ${fmtMoney(r.marginHi)}`; } },
        xAxis: { type: 'category', data: rows.map((r) => crop(r.cc).short), axisLabel: { interval: 0, fontSize: 11 } },
        yAxis: { type: 'value', axisLabel: { formatter: (v) => fmt(v / 1e6, 1) + ' млн' } },
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
  }
  update();
}
