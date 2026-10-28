// Экономика хозяйства и оптимизация структуры посевов по погодным сценариям.
import { D, fc, price } from './data.js';
import { state, quantile, mean } from './util.js';

export const ADJ = () => D.economics.adjustments;
const pick = (list, id) => list.find((x) => x.id === id) || list[1] || list[0];

// Состояние калькулятора — общее для экранов «Калькулятор» и «Оптимизация»
export function calcState() {
  if (!state.calc || !D.forecast.regions[state.calc.region]) state.calc = newCalc(state.region);
  return state.calc;
}
// План хозяйства задаётся в гектарах по каждой культуре (cfg.ha), независимо; доли cfg.plan и общая площадь cfg.area — производные.
export function newCalc(ok, area = 1000) {
  if (!D.forecast.regions[ok]) ok = '03000000000';
  const cfg = { region: ok, ha: {}, area: 0, plan: {}, adj: 0, soil: 'avg', variety: 'standard', tech: 'base', dateIdx: state.dateIdx,
    enabled: Object.fromEntries(Object.keys(D.forecast.regions[ok]).map((c) => [c, true])) };
  presetPlan(cfg, area);
  return cfg;
}
// Типовой план региона на заданную площадь (га)
export function presetPlan(cfg, area = 1000) {
  const sh = defaultPlan(cfg.region);
  cfg.ha = Object.fromEntries(Object.keys(D.forecast.regions[cfg.region]).map((cc) => [cc, Math.round((sh[cc] || 0) * area)]));
  syncPlan(cfg);
}
export function clearPlan(cfg) {
  cfg.ha = Object.fromEntries(Object.keys(D.forecast.regions[cfg.region]).map((cc) => [cc, 0]));
  syncPlan(cfg);
}
// Общая площадь и доли — из гектаров
export function syncPlan(cfg) {
  const tot = Object.values(cfg.ha).reduce((s, v) => s + (v || 0), 0);
  cfg.area = tot;
  cfg.plan = Object.fromEntries(Object.entries(cfg.ha).map(([cc, v]) => [cc, tot > 0 ? (v || 0) / tot : 0]));
}

// Типичная структура посевов региона по площадям 2025 г., округлённая до 5 %
export function defaultPlan(ok) {
  const reg = D.forecast.regions[ok];
  const items = Object.entries(reg).map(([cc, f]) => [cc, f.area_kha || 0]).filter(([cc]) => D.cropBy[cc]);
  const tot = items.reduce((s, [, a]) => s + a, 0) || 1;
  let plan = Object.fromEntries(items.map(([cc, a]) => [cc, a / tot]));
  // ограничения севооборота и минимальная доля
  for (const cc of Object.keys(plan)) {
    plan[cc] = Math.min(plan[cc], D.cropBy[cc].max_share);
    if (plan[cc] < 0.04) plan[cc] = 0;
  }
  const s = Object.values(plan).reduce((a, b) => a + b, 0) || 1;
  for (const cc of Object.keys(plan)) plan[cc] = Math.round(plan[cc] / s * 20) / 20;
  const sum = Object.values(plan).reduce((a, b) => a + b, 0);
  const top = Object.keys(plan).sort((a, b) => plan[b] - plan[a])[0];
  plan[top] = Math.round((plan[top] + 1 - sum) * 100) / 100;
  return plan;
}

export function multipliers(cfg) {
  const a = ADJ();
  const so = pick(a.soil, cfg.soil), va = pick(a.variety, cfg.variety), te = pick(a.tech, cfg.tech);
  const user = 1 + (cfg.adj || 0) / 100;   // собственная поправка пользователя к урожайности своих полей
  return { y: so.yield_mult * va.yield_mult * te.yield_mult * user, c: so.cost_mult * va.cost_mult * te.cost_mult, risk: va.risk_mult ?? 1 };
}

// Экономика по культурам на дату прогноза
export function cropEcon(cfg) {
  const m = multipliers(cfg);
  const rows = [];
  for (const [cc, share] of Object.entries(cfg.plan)) {
    if (!share) continue;
    const f = fc(cfg.region, cc);
    if (!f) continue;
    const d = f.by_date[cfg.dateIdx];
    const ha = cfg.area * share;
    const pr = price(cfg.region, cc);
    const cost = D.economics.crops[cc].cost_rub_ha * m.c;
    const y = { p10: d.p50 - (d.p50 - d.p10) * m.risk, p50: d.p50, p90: d.p50 + (d.p90 - d.p50) * m.risk };
    for (const k in y) y[k] *= m.y;
    rows.push({ cc, share, ha, y, vol: y.p50 * ha, price: pr, revenue: y.p50 * ha * pr, cost: cost * ha,
      margin: y.p50 * ha * pr - cost * ha, marginLo: y.p10 * ha * pr - cost * ha, marginHi: y.p90 * ha * pr - cost * ha });
  }
  const tot = rows.reduce((s, r) => ({ revenue: s.revenue + r.revenue, cost: s.cost + r.cost, margin: s.margin + r.margin,
    lo: s.lo + r.marginLo, hi: s.hi + r.marginHi }), { revenue: 0, cost: 0, margin: 0, lo: 0, hi: 0 });
  return { rows, tot };
}

// Расчёт модуля оптимизации по субъекту (web/data/optimization.json), если он выгружен
export const optRegion = (ok) => D.optimization?.regions?.[ok];

// Матрица «культура × сценарий → прибыль на 1 га», руб.
// Есть optimization.json — урожайность по сценариям, цены и затраты субъекта берём оттуда (как в расчёте LP);
// культуры плана вне пула субъекта — из scenarios.json по тем же годам.
export function scenarioMatrix(cfg) {
  const m = multipliers(cfg);
  const sc = D.scenarios.regions[cfg.region] || {};
  const o = optRegion(cfg.region);
  const years = o ? o.scenario_years : D.scenarios.scenario_years;
  const crops = [...new Set([...(o ? o.crops : []), ...Object.keys(sc)])].filter((cc) => D.cropBy[cc] && fc(cfg.region, cc));
  const R = {}, rev = {};
  for (const cc of crops) {
    const i = o ? o.crops.indexOf(cc) : -1;
    const ys = i >= 0 ? o.yields[i] : years.map((y) => sc[cc]?.[D.scenarios.scenario_years.indexOf(y)]);
    if (ys.some((y) => y == null)) continue;
    const mu = mean(ys);
    const pr = i >= 0 ? o.price_rub_t[i] : price(cfg.region, cc);
    const cost = (i >= 0 ? o.cost_rub_ha[i] : D.economics.crops[cc].cost_rub_ha) * m.c;
    R[cc] = ys.map((y) => (mu + (y - mu) * m.risk) * m.y * pr - cost);
    rev[cc] = mu * m.y * pr;
  }
  return { crops: Object.keys(R), R, rev, years, plan0: { ...cfg.plan } };
}

// Максимальная доля культуры в хозяйстве: норма севооборота модуля оптимизации (src/optimize/config.toml),
// иначе — из crops.json; свёклу (no_expand) не расширяем сверх текущего плана.
export function maxShare(cc, plan0) {
  const c = D.optimization?.crops?.[cc];
  if (!c) return D.cropBy[cc].max_share;
  return c.no_expand ? (plan0[cc] || 0) : Math.max(c.max_share, plan0[cc] || 0);
}

// Убывающая отдача: каждый следующий гектар перемен даёт меньше — добавленная площадь культуры хуже
// (предшественники, худшие участки), сокращённая требует перестройки севооборота.
// Потеря выручки растёт квадратично с изменением доли: BETA × Δ² / 2.
// С расчётом модуля оптимизации (optimization.json) штраф выключен: там, как и в научной постановке
// (src/optimize, линейная задача с CVaR), убывающую отдачу заменяет ограничение переноса X.
export const BETA = 2;
const beta = () => (D.optimization ? 0 : BETA);
function expansionLoss(c, w, M) {
  const d = w - (M.plan0[c] || 0);
  return beta() * d * d / 2 * M.rev[c];
}

export function profitByScenario(plan, M, area) {
  const n = M.years.length, out = new Array(n).fill(0);
  for (const cc of M.crops) {
    const w = plan[cc] || 0;
    if (!w && !M.plan0[cc]) continue;
    const r = M.R[cc], loss = expansionLoss(cc, w, M);
    for (let s = 0; s < n; s++) out[s] += (w * r[s] - loss) * area;
  }
  return out;
}
// Среднее худших 20 % сценариев (CVaR)
export function cvar(arr, q = 0.2) {
  const a = [...arr].sort((x, y) => x - y), k = Math.max(1, Math.round(a.length * q));
  return mean(a.slice(0, k));
}
export function stats(arr) { return { mean: mean(arr), bad: cvar(arr), p10: quantile(arr, 0.1), p90: quantile(arr, 0.9) }; }

// Жадная оптимизация переносами площади небольшими шагами.
// Цель: (1 − λ)·среднее + λ·CVaR20; ограничения: сумма долей = 1, доля ≤ max_share, перенос ≤ X.
export function optimize(plan0, M, { X, lambda, enabled, step = 0.005 }) {
  const crops = M.crops;
  const w = Object.fromEntries(crops.map((c) => [c, plan0[c] || 0]));
  const obj = () => { const p = profitByScenario(w, M, 1); return (1 - lambda) * mean(p) + lambda * cvar(p); };
  const moved = () => crops.reduce((s, c) => s + Math.abs(w[c] - (plan0[c] || 0)), 0) / 2;
  let cur = obj();
  for (let iter = 0; iter < 400; iter++) {
    let best = null, bestVal = cur + 1e-6;
    for (const i of crops) {
      if (w[i] < step - 1e-9) continue;
      for (const j of crops) {
        if (i === j || !enabled[j] || w[j] + step > maxShare(j, plan0) + 1e-9) continue;
        w[i] -= step; w[j] += step;
        if (moved() <= X + 1e-9) {
          const v = obj();
          if (v > bestVal) { bestVal = v; best = [i, j]; }
        }
        w[i] += step; w[j] -= step;
      }
    }
    if (!best) break;
    w[best[0]] -= step; w[best[1]] += step;
    cur = bestVal;
  }
  for (const c of crops) w[c] = Math.round(w[c] * 1000) / 1000;
  return w;
}
