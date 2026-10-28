// Экран «Оптимизация структуры посевов»: текущий план → рекомендованный при ограничении переноса X % и уровне осторожности.
import { D, crop, regionName, regionsAll } from './data.js';
import { cropIcon } from './icons.js';
import { calcState, newCalc, presetPlan, scenarioMatrix, profitByScenario, optimize, stats, optRegion } from './econ.js';
import { planEditor } from './calc.js';
import { state, fmt, fmtMoney, fmtSignedMoney, fmtPct, chart, opt, css, info, alpha, esc } from './util.js';

export function renderOptimize(el) {
  const cfg = calcState();
  cfg.X ??= 0.1;
  cfg.lambda ??= 0.5;
  const O = D.optimization, oR = optRegion(cfg.region);
  const yrs = oR ? oR.scenario_years : D.scenarios.scenario_years;
  const scenInfo = info(oR ? (O.settings.scenario_source === 'hist' ? 'Сценарии — фактические сезоны прошлых лет (ЕМИСС).' : 'Сценарии — итоговая модель, прогнавшая погоду прошлых лет.') : 'Сценарии — заглушка.',
    `Цены — ЕМИСС 57693 (2026), затраты на гектар — допущения. ${oR ? O.meta.source : ''}`);
  const regionSel = `<div class="field" style="min-width:min(260px,100%)"><label for="oReg">Регион</label><select class="select" id="oReg">${regionsAll().map((r) => `<option value="${r}" ${r === cfg.region ? 'selected' : ''}>${esc(regionName(r))}</option>`).join('')}</select></div>`;
  const head = `
  <div class="page-head">
    <div>
      <div class="eyebrow">Что посеять</div>
      <h1>Измените план немного — получите заметный эффект</h1>
      <p class="lead">Проверяем ваш план на погоде ${yrs.length} прошлых сезонов (${yrs[0]}–${yrs.at(-1)}) и предлагаем небольшие перемены, которые повышают прибыль.</p>
      <span class="frame">Урожайность берётся по региону в целом, затраты — допущения: это подсказка для планирования, а не гарантия.</span>
    </div>
    ${regionSel}
  </div>`;
  if (!(cfg.area > 0)) {
    el.innerHTML = head + `<div class="card empty-hint"><h3 style="margin-bottom:6px">Сначала задайте план хозяйства</h3><p style="margin:0 0 14px">Укажите гектары по культурам в калькуляторе — или возьмите типовой план региона.</p><div class="preset-row" style="justify-content:center"><button class="btn" id="oPre" type="button">Типовой план региона</button><a class="btn ghost" href="#/calc">Открыть калькулятор</a></div></div>`;
    el.querySelector('#oPre').addEventListener('click', () => { presetPlan(cfg, 1000); renderOptimize(el); });
    el.querySelector('#oReg').addEventListener('change', (e) => { Object.assign(cfg, newCalc(e.target.value)); state.region = cfg.region; renderOptimize(el); });
    return;
  }
  el.innerHTML = head + `
  <div class="callout" id="oCall" style="margin-bottom:18px"></div>
  <div class="grid g-calc">
    <div class="card stack" style="gap:18px">
      <div class="slider-field">
        <div class="top"><span>Сколько площади можно переставить</span><output id="oXv"></output></div>
        <input type="range" id="oX" min="0" max="30" step="1" value="${Math.round(cfg.X * 100)}">
        <div class="ends"><span>0 % — ничего</span><span>30 %</span></div>
      </div>
      <div class="slider-field">
        <div class="top"><span>Осторожность</span><output id="oLv"></output></div>
        <input type="range" id="oL" min="0" max="100" step="5" value="${Math.round(cfg.lambda * 100)}">
        <div class="ends"><span>больше прибыли</span><span>надёжнее в плохой год</span></div>
      </div>
      <div>
        <div class="card-head" style="margin:0 0 8px"><span class="field-label">Ваш план, га</span><a class="chip-note" href="#/calc">изменить в калькуляторе</a></div>
        <div id="oPlan"></div>
      </div>
    </div>
    <div class="stack">
      <div class="kpis" id="oK" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr))"></div>
      <div class="card">
        <div class="card-head"><div><h3>Что изменить в плане</h3><div class="sub">Доля площади по культурам: серая полоса — сейчас, цветная — рекомендация</div></div>${scenInfo}</div>
        <div class="diff" id="oDiff"></div>
      </div>
    </div>
  </div>
  <details class="more" id="oMore">
    <summary><span>Подробнее<small>как растёт выигрыш, прибыль по годам, настройки</small></span></summary>
    <div class="more-body">
      <div class="grid g-2">
        <div class="card"><p class="verdict" id="oCurveT"></p><div class="chart" id="oCurve"></div></div>
        <div class="card"><p class="verdict">Прибыль при погоде прошлых лет: план стал устойчивее к плохим сезонам</p><div class="chart" id="oDist"></div></div>
      </div>
      <div>
        <div class="field-label" style="margin-bottom:8px">Какие культуры можно добавлять в план</div>
        <div class="crop-toggles" id="oEn"></div>
        <p class="chip-note" style="margin:12px 0 0">Ограничения севооборота — агрономические нормы возврата культуры на поле (подсолнечник ≤ 15 %, свёкла ≤ 20 % и не больше текущей площади), затраты на 1 га — допущения (src/optimize/config.toml). «Плохой год» — среднее по худшим 20 % сезонов (около 1 из 5). Осторожность задаёт, насколько мы жертвуем средней прибылью ради плохих лет.${oR ? ' Отдачу от перемен ограничивает допустимый перенос площади.' : ' Учтена убывающая отдача: каждый следующий процент перемен даёт меньше предыдущего.'}</p>
      </div>
    </div>
  </details>
  ${oR ? `<details class="more" id="oRegDet"><summary><span>Весь регион целиком<small>оптимальная структура посевов субъекта</small></span></summary><div class="more-body">${regionCardHtml(oR)}</div></details>` : ''}`;

  let curveC = null, distC = null;
  const moreEl = el.querySelector('#oMore');
  moreEl.addEventListener('toggle', () => {
    if (moreEl.open && !curveC) { curveC = chart(el.querySelector('#oCurve')); distC = chart(el.querySelector('#oDist')); update(true); }
  });
  const regDet = el.querySelector('#oRegDet');
  if (regDet) regDet.addEventListener('toggle', () => { if (regDet.open && !regDet.dataset.bound) { regDet.dataset.bound = '1'; bindRegionCard(el, oR); } });

  el.querySelector('#oReg').addEventListener('change', (e) => {
    const keep = { soil: cfg.soil, variety: cfg.variety, tech: cfg.tech, adj: cfg.adj, dateIdx: cfg.dateIdx, X: cfg.X, lambda: cfg.lambda };
    Object.assign(cfg, newCalc(e.target.value, cfg.area), keep);
    state.region = cfg.region;
    renderOptimize(el);
  });
  const xs = el.querySelector('#oX'), ls = el.querySelector('#oL');
  const paint = () => {
    xs.style.setProperty('--p', (xs.value / 30 * 100) + '%'); ls.style.setProperty('--p', ls.value + '%');
    el.querySelector('#oXv').textContent = 'до ' + xs.value + ' %';
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
    const changes = M.crops.map((c) => ({ c, d: best[c] - plan0[c] })).filter((x) => Math.abs(x.d) >= 0.01).sort((a, b) => a.d - b.d);
    const from = changes.filter((x) => x.d < 0).map((x) => crop(x.c).short.toLowerCase());
    const to = changes.filter((x) => x.d > 0).map((x) => crop(x.c).short.toLowerCase());
    el.querySelector('#oCall').innerHTML = moved < 0.004
      ? `<h3>Текущий план уже близок к лучшему при этих ограничениях.</h3><p>Увеличьте допустимый перенос или снизьте осторожность, чтобы увидеть варианты.</p>`
      : `<h3>Переведите <span class="big">${fmt(moved * 100, 1)} %</span> площади (${fmt(moved * cfg.area, 0)} га): ${from.join(', ')} → ${to.join(', ')}</h3>
         <p>Ожидаемая прибыль <b class="big">${gainTxt}</b> (${fmtSignedMoney(s1.mean - s0.mean)} в год), в плохой год <b class="big">${fmtSignedMoney(s1.bad - s0.bad)}</b>. Проверено на погоде ${M.years.length} прошлых сезонов.</p>`;

    el.querySelector('#oK').innerHTML = `
      <div class="kpi hero"><div class="label">Ожидаемая прибыль в год</div><div class="value num">${gainTxt}</div><div class="foot">${fmtMoney(s0.mean)} → ${fmtMoney(s1.mean)}</div></div>
      <div class="kpi"><div class="label">В плохой год</div><div class="value num" style="color:${s1.bad >= s0.bad ? 'var(--pos)' : 'var(--neg)'}">${badTxt}</div><div class="foot">${fmtMoney(s0.bad)} → ${fmtMoney(s1.bad)} · худшие ${Math.max(1, Math.round(M.years.length * 0.2))} из ${M.years.length} сезонов</div></div>
      <div class="kpi"><div class="label">Переставляем</div><div class="value num">${fmt(moved * 100, 1)}<small>%</small></div><div class="foot">${fmt(moved * cfg.area, 0)} га из ${fmt(cfg.area, 0)}</div></div>`;

    el.querySelector('#oDiff').innerHTML = M.crops.filter((c) => plan0[c] > 0 || best[c] >= 0.01).sort((a, b) => best[b] - best[a]).map((cc) => {
      const c = crop(cc), a = plan0[cc] * 100, b = best[cc] * 100, d = b - a;
      const cls = Math.abs(d) < 0.25 ? 'zero' : d > 0 ? 'up' : 'down';
      return `<div class="diff-row"><div class="lbl"><span class="ico" style="color:${c.color};background:${alpha(c.color, .14)}">${cropIcon(c)}</span><div>${c.short}<div class="vals">${fmt(a, 0)} → ${fmt(b, 1)} %</div></div></div>
        <div class="track"><div class="old" style="width:${a}%"></div><div class="new" style="width:${b}%;background:${c.color}"></div></div>
        <div class="d ${cls}">${cls === 'zero' ? '0' : (d > 0 ? '▲ +' : '▼ −') + fmt(Math.abs(d), 1)} п.п.</div></div>`;
    }).join('');

    if (!curveC) return;
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
    const maxG = curve.at(-1)[1], x80 = curve.find((c) => c[1] >= 0.8 * maxG)?.[0];
    el.querySelector('#oCurveT').textContent = maxG > 0 ? `Основной выигрыш дают первые ${x80} % перемен — дальше прибавка почти не растёт` : 'При этих условиях перемены не добавляют прибыли';
    const brand = css('--brand-2'), gold = css('--gold-2');
    curveC.setOption(opt({
      grid: { top: 48, left: 4, right: 12, bottom: 22 },
      legend: { data: ['Средняя прибыль', 'Плохой год'], left: 0, right: 'auto' },
      tooltip: { formatter: (ps) => `<b>Перенос до ${ps[0].data[0]} %</b>` + ps.map((p) => `<br>${p.marker}${p.seriesName}: ${fmtSignedMoney(p.data[1] * 1e6)}`).join('') },
      xAxis: { type: 'value', min: 0, max: 30, name: 'сколько площади переставляем', nameLocation: 'middle', nameGap: 26, nameTextStyle: { color: css('--text-3'), fontSize: 11 }, axisLabel: { formatter: '{value} %' } },
      yAxis: { type: 'value', name: 'млн ₽ в год', axisLabel: { formatter: (v) => fmt(v, Math.abs(v) < 10 ? 1 : 0) } },
      series: [
        { name: 'Средняя прибыль', type: 'line', data: curve.map((c) => [c[0], c[1]]), smooth: true, symbol: 'none', lineStyle: { width: 3, color: brand }, itemStyle: { color: brand }, areaStyle: { color: alpha(brand, .12) },
          markPoint: { symbol: 'circle', symbolSize: 12, itemStyle: { color: css('--gold'), borderColor: css('--surface'), borderWidth: 3 }, data: [{ coord: [xi, curve[xi][1]] }], label: { show: false } },
          markLine: { silent: true, symbol: 'none', lineStyle: { color: css('--text-3'), type: 'dashed' }, label: { formatter: 'у вас', color: css('--text-3'), fontSize: 11 }, data: [{ xAxis: xi }] } },
        { name: 'Плохой год', type: 'line', data: curve.map((c) => [c[0], c[2]]), smooth: true, symbol: 'none', lineStyle: { width: 2, color: gold, type: [6, 4] }, itemStyle: { color: gold } },
      ],
    }), true);

    // распределение по сценариям, отсортировано по прибыли текущего плана
    const order = M.years.map((y, k) => k).sort((a, b) => p0[a] - p0[b]);
    distC.setOption(opt({
      grid: { top: 34, left: 4, right: 8, bottom: 52 },
      legend: { data: ['Текущий план', 'Рекомендация'], left: 0, right: 'auto' },
      tooltip: { axisPointer: { type: 'shadow' }, formatter: (ps) => `<b>Погода ${ps[0].name} г.</b>` + ps.map((p) => `<br>${p.marker}${p.seriesName}: ${fmtMoney(p.value)}`).join('') },
      xAxis: { type: 'category', data: order.map((k) => String(M.years[k])), name: 'погода года (по возрастанию прибыли)', nameLocation: 'middle', nameGap: 38, nameTextStyle: { color: css('--text-3'), fontSize: 11 }, axisLabel: { interval: 0, fontSize: 10, rotate: 60 } },
      yAxis: { type: 'value', axisLabel: { formatter: (v) => fmt(v / 1e6, 0) + ' млн' } },
      series: [
        { name: 'Текущий план', type: 'bar', data: order.map((k) => p0[k]), itemStyle: { color: css('--border-strong'), borderRadius: [3, 3, 0, 0] }, barGap: '10%' },
        { name: 'Рекомендация', type: 'bar', data: order.map((k) => p1[k]), itemStyle: { color: brand, borderRadius: [3, 3, 0, 0] } },
      ],
    }), true);
  }
  update(true);
}

// ---------- Расчёт для структуры посевов субъекта в целом (src/optimize, CVaR-LP)
const DKEYS = () => [...D.optimization.settings.deltas.map(String), 'all'];
const dLabel = (k) => (k === 'all' ? 'как позволит севооборот' : `не более ±${k} п.п.`);

function regionCardHtml(o) {
  const s = D.optimization.settings;
  const bt = o.backtest;
  return `<div>
    <div class="card-head"><div><h3>Лучшая структура посевов для региона целиком</h3>
      <div class="sub">Расчёт для всех хозяйств региона: ${fmt(o.pool_kha, 0)} тыс. га под 7 культурами (посевы 2025 г.). Выберите, насколько можно менять долю каждой культуры.</div></div>
      ${info('Научный расчёт модуля оптимизации: сценарная оптимизация (линейное программирование) с учётом худших ' + fmt(s.alpha * 100, 0) + ' % сезонов; цель — (1 − λ) × средняя прибыль + λ × прибыль в худших сезонах, λ = ' + fmt(s.lambda, 1) + '.', D.optimization.meta.source)}</div>
    <div class="seg" id="rSeg" style="margin-bottom:14px;flex-wrap:wrap">${DKEYS().map((k, i) => `<button data-k="${k}" class="${i === 0 ? 'active' : ''}">${dLabel(k)}</button>`).join('')}</div>
    <div class="kpis" id="rK" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr));margin-bottom:14px"></div>
    <div class="grid g-2">
      <div><div class="diff" id="rDiff"></div>
        <p class="chip-note" style="margin:12px 0 0">${bt ? `Проверка на прошлых годах ${bt.years[0]}–${bt.years[1]} (сценарии и тренд — только по истории до года t, результат — по факту года t), при перемене до ±10 п.п.: в среднем <b>${bt.real_gain_rub_ha > 0 ? '+' : '−'}${fmt(Math.abs(bt.real_gain_rub_ha), 0)} ₽</b> на гектар, план лучше текущего в ${fmt(bt.win_share_pct, 0)} % лет. ` : ''}Затраты — допущения; выигрыш держится на разнице маржи культур и чувствителен к ценам (reports/optimization.md).</p></div>
      <div><div class="card-head" style="margin:0 0 4px"><div><h3 style="font-size:14px">Доход — риск</h3><div class="sub">Эффективная граница: каждая точка — оптимум при своём λ</div></div></div><div class="chart" id="rFront" style="height:300px"></div></div>
    </div>
  </div>`;
}

function bindRegionCard(el, o) {
  const frontC = chart(el.querySelector('#rFront'));
  const show = (k) => {
    const p = o.plans[k], c0 = o.current;
    // ₽/га — точно, без округления до тысяч
    const rh = (v) => fmt(v, 0) + ' ₽', srh = (v) => (v > 0 ? '+' : v < 0 ? '−' : '') + rh(Math.abs(v));
    el.querySelector('#rK').innerHTML = `
      <div class="kpi hero"><div class="label">Ожидаемая прибыль, ₽/га</div><div class="value num">${srh(p.mean - c0.mean)}</div><div class="foot">${rh(c0.mean)} → ${rh(p.mean)} · ${fmtSignedMoney(p.gain_mln * 1e6)} в год по субъекту</div></div>
      <div class="kpi"><div class="label">Худшие ${fmt(D.optimization.settings.alpha * 100, 0)} % сезонов, ₽/га</div><div class="value num" style="color:${p.cvar >= c0.cvar ? 'var(--pos)' : 'var(--neg)'}">${srh(p.cvar - c0.cvar)}</div><div class="foot">${rh(c0.cvar)} → ${rh(p.cvar)}</div></div>
      <div class="kpi"><div class="label">Самый плохой сезон, ₽/га</div><div class="value num" style="color:${p.worst >= c0.worst ? 'var(--pos)' : 'var(--neg)'}">${srh(p.worst - c0.worst)}</div><div class="foot">${rh(c0.worst)} → ${rh(p.worst)}</div></div>
      <div class="kpi"><div class="label">Перенос площади</div><div class="value num">${fmt(p.turnover_pct, 1)}<small>%</small></div><div class="foot">${fmt(p.turnover_pct / 100 * o.pool_kha, 0)} тыс. га</div></div>`;
    el.querySelector('#rDiff').innerHTML = o.crops.map((cc, i) => ({ cc, a: o.x0[i] * 100, b: p.x[i] * 100 }))
      .filter((r) => r.a >= 0.5 || r.b >= 0.5).sort((x, y) => y.b - x.b).map(({ cc, a, b }) => {
        const c = crop(cc), d = b - a, cls = Math.abs(d) < 0.25 ? 'zero' : d > 0 ? 'up' : 'down';
        return `<div class="diff-row"><div class="lbl"><span class="ico" style="color:${c.color};background:${alpha(c.color, .14)}">${cropIcon(c)}</span><div>${c.short}<div class="vals">${fmt(a, 1)} → ${fmt(b, 1)} %</div></div></div>
          <div class="track"><div class="old" style="width:${a}%"></div><div class="new" style="width:${b}%;background:${c.color}"></div></div>
          <div class="d ${cls}">${cls === 'zero' ? '0' : (d > 0 ? '▲ +' : '▼ −') + fmt(Math.abs(d), 1)} п.п.</div></div>`;
      }).join('');
    const brand = css('--brand-2');
    const line = (key, name, color, width) => ({ name, type: 'line', data: (o.frontier[key] || []).map((q) => [q[0], q[1], q[2]]),
      symbolSize: 7, lineStyle: { width, color }, itemStyle: { color } });
    frontC.setOption(opt({
      grid: { top: 30, left: 4, right: 14, bottom: 58 },
      legend: { data: ['как позволит севооборот', 'не более ±10 п.п.', 'текущий план', 'выбранный план'], left: 0, right: 'auto', top: 'auto', bottom: 0 },
      tooltip: { trigger: 'item', formatter: (q) => `<b>${q.seriesName}</b>${q.data[2] != null ? ` · λ = ${fmt(q.data[2], 1)}` : ''}<br>средняя: ${rh(q.data[1])}/га<br>худшие сезоны: ${rh(q.data[0])}/га` },
      xAxis: { type: 'value', scale: true, name: 'худшие сезоны, тыс. ₽/га', nameLocation: 'middle', nameGap: 20, nameTextStyle: { color: css('--text-3'), fontSize: 11 }, axisLabel: { formatter: (v) => fmt(v / 1e3, 1) } },
      yAxis: { type: 'value', scale: true, name: 'средняя, тыс. ₽/га', axisLabel: { formatter: (v) => fmt(v / 1e3, 1) } },
      series: [
        line('all', 'как позволит севооборот', css('--text-3'), 2),
        line('10', 'не более ±10 п.п.', brand, 3),
        { name: 'текущий план', type: 'scatter', data: [[o.current.cvar, o.current.mean, null]], symbolSize: 12, itemStyle: { color: css('--border-strong'), borderColor: css('--surface'), borderWidth: 2 } },
        { name: 'выбранный план', type: 'scatter', data: [[p.cvar, p.mean, null]], symbolSize: 13, itemStyle: { color: css('--gold'), borderColor: css('--surface'), borderWidth: 2 } },
      ],
    }), true);
  };
  el.querySelectorAll('#rSeg button').forEach((b) => b.addEventListener('click', () => {
    el.querySelectorAll('#rSeg button').forEach((x) => x.classList.toggle('active', x === b));
    show(b.dataset.k);
  }));
  show(DKEYS()[0]);
}
