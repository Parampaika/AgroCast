// Экран «Оптимизация структуры посевов»: текущий план → рекомендованный при ограничении переноса X % и уровне осторожности.
import { D, crop, regionName, regionsAll } from './data.js';
import { cropIcon } from './icons.js';
import { calcState, newCalc, scenarioMatrix, profitByScenario, optimize, stats } from './econ.js';
import { planEditor } from './calc.js';
import { state, fmt, fmtMoney, fmtSignedMoney, fmtPct, chart, opt, css, demoBadge, alpha, esc } from './util.js';

export function renderOptimize(el) {
  const cfg = calcState();
  cfg.X ??= 0.1;
  cfg.lambda ??= 0.5;
  el.innerHTML = `
  <div class="page-head">
    <div>
      <div class="eyebrow">Оптимизация структуры посевов</div>
      <h1>Измените план немного — получите заметный эффект</h1>
      <p class="lead">Перебираем погоду ${D.scenarios.scenario_years[0]}–${D.scenarios.scenario_years.at(-1)} годов как сценарии сезона и ищем план с лучшей прибылью при ограничении «менять не больше X % площади» и правилах севооборота.</p>
    </div>
    <div class="field" style="min-width:260px"><label for="oReg">Регион</label><select class="select" id="oReg">${regionsAll().map((r) => `<option value="${r}" ${r === cfg.region ? 'selected' : ''}>${esc(regionName(r))}</option>`).join('')}</select></div>
  </div>
  <div class="callout" id="oCall" style="margin-bottom:18px"></div>
  <div class="grid g-calc">
    <div class="card stack" style="gap:18px">
      <div class="slider-field">
        <div class="top"><span>Менять не больше</span><output id="oXv"></output></div>
        <input type="range" id="oX" min="0" max="30" step="1" value="${Math.round(cfg.X * 100)}">
        <div class="ends"><span>0 % — оставить как есть</span><span>30 %</span></div>
      </div>
      <div class="slider-field">
        <div class="top"><span>Осторожность</span><output id="oLv"></output></div>
        <input type="range" id="oL" min="0" max="100" step="5" value="${Math.round(cfg.lambda * 100)}">
        <div class="ends"><span>максимум прибыли</span><span>защита от плохого года</span></div>
      </div>
      <div>
        <div class="field-label" style="margin-bottom:8px">Какие культуры можно сеять</div>
        <div class="crop-toggles" id="oEn"></div>
      </div>
      <div>
        <div class="card-head" style="margin:0 0 8px"><span class="field-label">Текущий план, ${fmt(cfg.area, 0)} га</span><a class="chip-note" href="#/calc">изменить в калькуляторе</a></div>
        <div class="plan-rows" id="oPlan"></div>
      </div>
      <p class="chip-note" style="margin:0">Ограничения севооборота (макс. доля культуры) — допущения прототипа. Цель: (1 − осторожность) × средняя прибыль + осторожность × прибыль в худших 20 % сезонов. Учтена убывающая отдача: каждый следующий процент перемен даёт меньше предыдущего (предшественники, худшие участки, перестройка севооборота).</p>
    </div>
    <div class="stack">
      <div class="kpis" id="oK" style="grid-template-columns:repeat(auto-fit,minmax(180px,1fr))"></div>
      <div class="card">
        <div class="card-head"><div><h3>Было → стало</h3><div class="sub">Доля площади по культурам: серая полоса — текущий план, цветная — рекомендация</div></div>${demoBadge('сценарии — демо')}</div>
        <div class="diff" id="oDiff"></div>
      </div>
      <div class="grid g-2">
        <div class="card"><div class="card-head"><div><h3>Сколько меняем → сколько выигрываем</h3><div class="sub">Прирост прибыли за год при разном ограничении X</div></div></div><div class="chart" id="oCurve"></div></div>
        <div class="card"><div class="card-head"><div><h3>Прибыль по погодным сценариям</h3><div class="sub">Каждый столбец — погода одного прошлого сезона</div></div></div><div class="chart" id="oDist"></div></div>
      </div>
    </div>
  </div>`;

  const curveC = chart(el.querySelector('#oCurve')), distC = chart(el.querySelector('#oDist'));

  el.querySelector('#oReg').addEventListener('change', (e) => {
    const keep = { area: cfg.area, soil: cfg.soil, variety: cfg.variety, tech: cfg.tech, dateIdx: cfg.dateIdx, X: cfg.X, lambda: cfg.lambda };
    Object.assign(cfg, newCalc(e.target.value), keep);
    state.region = cfg.region;
    renderOptimize(el);
  });
  const xs = el.querySelector('#oX'), ls = el.querySelector('#oL');
  const paint = () => {
    xs.style.setProperty('--p', (xs.value / 30 * 100) + '%'); ls.style.setProperty('--p', ls.value + '%');
    el.querySelector('#oXv').textContent = xs.value + ' % площади';
    el.querySelector('#oLv').textContent = ls.value < 25 ? 'низкая' : ls.value < 65 ? 'средняя' : 'высокая';
  };
  xs.addEventListener('input', () => { cfg.X = xs.value / 100; paint(); update(false); });
  ls.addEventListener('input', () => { cfg.lambda = ls.value / 100; paint(); update(true); });
  paint();

  const M0 = scenarioMatrix(cfg);
  el.querySelector('#oEn').innerHTML = M0.crops.map((cc) => { const c = crop(cc); return `<label><input type="checkbox" data-cc="${cc}" ${cfg.enabled[cc] !== false ? 'checked' : ''}><span class="ico" style="color:${c.color}">${cropIcon(c)}</span>${c.short}</label>`; }).join('');
  el.querySelectorAll('#oEn input').forEach((i) => i.addEventListener('change', () => { cfg.enabled[i.dataset.cc] = i.checked; update(true); }));

  const ed = planEditor(cfg, () => update(true));
  el.querySelector('#oPlan').innerHTML = ed.html;
  ed.bind(el.querySelector('#oPlan'));

  let curve = null;
  function update(recalcCurve = true) {
    const M = scenarioMatrix(cfg);
    const plan0 = Object.fromEntries(M.crops.map((c) => [c, cfg.plan[c] || 0]));
    const params = { lambda: cfg.lambda, enabled: cfg.enabled };
    const best = optimize(plan0, M, { ...params, X: cfg.X });
    const p0 = profitByScenario(plan0, M, cfg.area), p1 = profitByScenario(best, M, cfg.area);
    const s0 = stats(p0), s1 = stats(p1);
    // Процент показываем, только если база положительная и заметная; иначе — рубли
    const rel = (a, b) => (b > 0 && Math.abs(a - b) / b < 5 ? fmtPct((a / b - 1) * 100) : fmtMoney(a - b));
    const gainTxt = rel(s1.mean, s0.mean), badTxt = rel(s1.bad, s0.bad);
    const moved = M.crops.reduce((s, c) => s + Math.abs(best[c] - plan0[c]), 0) / 2;

    // главная фраза
    const changes = M.crops.map((c) => ({ c, d: best[c] - plan0[c] })).filter((x) => Math.abs(x.d) >= 0.005).sort((a, b) => a.d - b.d);
    const from = changes.filter((x) => x.d < 0).map((x) => crop(x.c).short.toLowerCase());
    const to = changes.filter((x) => x.d > 0).map((x) => crop(x.c).short.toLowerCase());
    el.querySelector('#oCall').innerHTML = moved < 0.004
      ? `<h3>Текущий план уже близок к лучшему при этих ограничениях.</h3><p>Увеличьте допустимый перенос или снизьте осторожность, чтобы увидеть варианты.</p>`
      : `<h3>Переведите <span class="big">${fmt(moved * 100, 1)} %</span> площади (${fmt(moved * cfg.area, 0)} га): ${from.join(', ')} → ${to.join(', ')}</h3>
         <p>Ожидаемая прибыль <b class="big">${gainTxt}</b> (${fmtSignedMoney(s1.mean - s0.mean)} в год), в плохой год <b class="big">${fmtSignedMoney(s1.bad - s0.bad)}</b>. Расчёт по ${M.years.length} погодным сценариям.</p>`;

    el.querySelector('#oK').innerHTML = `
      <div class="kpi hero"><div class="label">Ожидаемая прибыль</div><div class="value num">${gainTxt}</div><div class="foot">${fmtMoney(s0.mean)} → ${fmtMoney(s1.mean)}</div></div>
      <div class="kpi"><div class="label">Плохой год (худшие 20 %)</div><div class="value num" style="color:${s1.bad >= s0.bad ? 'var(--pos)' : 'var(--neg)'}">${badTxt}</div><div class="foot">${fmtMoney(s0.bad)} → ${fmtMoney(s1.bad)}</div></div>
      <div class="kpi"><div class="label">Сколько меняем</div><div class="value num">${fmt(moved * 100, 1)}<small>%</small></div><div class="foot">${fmt(moved * cfg.area, 0)} га из ${fmt(cfg.area, 0)}</div></div>`;

    el.querySelector('#oDiff').innerHTML = M.crops.filter((c) => plan0[c] > 0 || best[c] > 0).sort((a, b) => best[b] - best[a]).map((cc) => {
      const c = crop(cc), a = plan0[cc] * 100, b = best[cc] * 100, d = b - a;
      const cls = Math.abs(d) < 0.25 ? 'zero' : d > 0 ? 'up' : 'down';
      return `<div class="diff-row"><div class="lbl"><span class="ico" style="color:${c.color};background:${alpha(c.color, .14)}">${cropIcon(c)}</span><div>${c.short}<div class="vals">${fmt(a, 0)} → ${fmt(b, 1)} %</div></div></div>
        <div class="track"><div class="old" style="width:${a}%"></div><div class="new" style="width:${b}%;background:${c.color}"></div></div>
        <div class="d ${cls}">${cls === 'zero' ? '0' : (d > 0 ? '▲ +' : '▼ −') + fmt(Math.abs(d), 1)} п.п.</div></div>`;
    }).join('');

    // кривая «X → выигрыш»
    if (recalcCurve || !curve) {
      curve = [];
      for (let x = 0; x <= 30; x += 1) {
        const w = optimize(plan0, M, { ...params, X: x / 100, step: 0.01 });
        const p = profitByScenario(w, M, cfg.area), s = stats(p);
        curve.push([x, (s.mean - s0.mean) / 1e6, (s.bad - s0.bad) / 1e6]);
      }
    }
    const xi = Math.round(cfg.X * 100);
    const brand = css('--brand-2'), gold = css('--gold-2');
    curveC.setOption(opt({
      grid: { top: 34, left: 4, right: 12, bottom: 22 },
      legend: { data: ['Средняя прибыль', 'Плохой год'], left: 0, right: 'auto' },
      tooltip: { formatter: (ps) => `<b>Перенос до ${ps[0].data[0]} %</b>` + ps.map((p) => `<br>${p.marker}${p.seriesName}: ${fmtSignedMoney(p.data[1] * 1e6)}`).join('') },
      xAxis: { type: 'value', min: 0, max: 30, name: 'X, % площади', nameLocation: 'middle', nameGap: 26, nameTextStyle: { color: css('--text-3'), fontSize: 11 }, axisLabel: { formatter: '{value} %' } },
      yAxis: { type: 'value', name: 'млн ₽ в год', axisLabel: { formatter: (v) => fmt(v, Math.abs(v) < 10 ? 1 : 0) } },
      series: [
        { name: 'Средняя прибыль', type: 'line', data: curve.map((c) => [c[0], c[1]]), smooth: true, symbol: 'none', lineStyle: { width: 3, color: brand }, itemStyle: { color: brand }, areaStyle: { color: alpha(brand, .12) },
          markPoint: { symbol: 'circle', symbolSize: 12, itemStyle: { color: css('--gold'), borderColor: css('--surface'), borderWidth: 3 }, data: [{ coord: [xi, curve[xi][1]] }], label: { show: false } },
          markLine: { silent: true, symbol: 'none', lineStyle: { color: css('--text-3'), type: 'dashed' }, label: { formatter: 'ваш X', color: css('--text-3'), fontSize: 11 }, data: [{ xAxis: xi }] } },
        { name: 'Плохой год', type: 'line', data: curve.map((c) => [c[0], c[2]]), smooth: true, symbol: 'none', lineStyle: { width: 2, color: gold, type: [6, 4] }, itemStyle: { color: gold } },
      ],
    }), true);

    // распределение по сценариям, отсортировано по прибыли текущего плана
    const order = M.years.map((y, k) => k).sort((a, b) => p0[a] - p0[b]);
    distC.setOption(opt({
      grid: { top: 34, left: 4, right: 8, bottom: 4 },
      legend: { data: ['Текущий план', 'Рекомендация'], left: 0, right: 'auto' },
      tooltip: { axisPointer: { type: 'shadow' }, formatter: (ps) => `<b>Погода ${ps[0].name} г.</b>` + ps.map((p) => `<br>${p.marker}${p.seriesName}: ${fmtMoney(p.value)}`).join('') },
      xAxis: { type: 'category', data: order.map((k) => String(M.years[k])), axisLabel: { interval: 'auto', fontSize: 10.5, rotate: 0, formatter: (v) => "'" + v.slice(2) } },
      yAxis: { type: 'value', axisLabel: { formatter: (v) => fmt(v / 1e6, 0) + ' млн' } },
      series: [
        { name: 'Текущий план', type: 'bar', data: order.map((k) => p0[k]), itemStyle: { color: css('--border-strong'), borderRadius: [3, 3, 0, 0] }, barGap: '10%' },
        { name: 'Рекомендация', type: 'bar', data: order.map((k) => p1[k]), itemStyle: { color: brand, borderRadius: [3, 3, 0, 0] } },
      ],
    }), true);
  }
  update(true);
}
