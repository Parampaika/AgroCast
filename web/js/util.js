// Общие функции: форматирование, цвета из CSS, базовые опции графиков, состояние приложения.

export const state = {
  crop: '1010400',      // выбранная культура
  dateIdx: 4,           // индекс даты прогноза (0 — 1 мая … 4 — конец сезона)
  metric: 'yield',      // 'yield' — т/га, 'dev' — к тренду, %
  region: '03000000000',
  calc: null,           // состояние калькулятора (общий план для оптимизации)
};

const nf = (d) => new Intl.NumberFormat('ru-RU', { minimumFractionDigits: d, maximumFractionDigits: d });
const cache = {};
export const fmt = (v, d = 1) => (v == null || !isFinite(v)) ? '—' : (cache[d] ||= nf(d)).format(v);
export const fmtSigned = (v, d = 1) => (v == null || !isFinite(v)) ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '') + fmt(Math.abs(v), d);
export const fmtPct = (v, d = 1) => fmtSigned(v, d) + ' %';
export const fmtMoney = (rub) => {      // рубли → млн ₽ / тыс. ₽
  if (rub == null || !isFinite(rub)) return '—';
  const a = Math.abs(rub);
  if (a >= 1e9) return fmt(rub / 1e9, 2) + ' млрд ₽';
  if (a >= 1e6) return fmt(rub / 1e6, a >= 1e8 ? 0 : 1) + ' млн ₽';
  return fmt(rub / 1e3, 0) + ' тыс. ₽';
};
export const fmtSignedMoney = (rub) => (rub > 0 ? '+' : rub < 0 ? '−' : '') + fmtMoney(Math.abs(rub));
export const fmtVol = (kt) => {          // тыс. т → млн т / тыс. т / т
  if (kt == null || !isFinite(kt)) return '—';
  if (Math.abs(kt) >= 1000) return fmt(kt / 1000, 1) + ' млн т';
  if (Math.abs(kt) >= 1) return fmt(kt, kt >= 100 ? 0 : 1) + ' тыс. т';
  return fmt(kt * 1000, 0) + ' т';
};
export const deltaHtml = (pct, d = 1) => {
  if (pct == null || !isFinite(pct)) return '<span class="delta">—</span>';
  const cls = pct >= 0 ? 'up' : 'down';
  return `<span class="delta ${cls}">${pct >= 0 ? '▲' : '▼'} ${fmt(Math.abs(pct), d)} %</span>`;
};
export const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

export const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
export const isDark = () => {
  const t = document.documentElement.dataset.theme;
  return t ? t === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
};

export const demoBadge = (text = 'демо-данные', title = 'Заглушка до выгрузки финальной модели: формат стабильный, значения условные') =>
  `<span class="badge-demo" title="${esc(title)}">${text}</span>`;
export const realBadge = (text = 'реальные данные', title = '') =>
  `<span class="badge-demo badge-real" title="${esc(title)}">${text}</span>`;

// Квантиль по массиву
export function quantile(arr, q) {
  const a = arr.filter((x) => x != null && isFinite(x)).sort((x, y) => x - y);
  if (!a.length) return NaN;
  const pos = (a.length - 1) * q, lo = Math.floor(pos), hi = Math.ceil(pos);
  return a[lo] + (a[hi] - a[lo]) * (pos - lo);
}
export const mean = (a) => a.reduce((s, x) => s + x, 0) / a.length;

// Регистр графиков ECharts: переинициализация при смене темы и ресайзе
const charts = new Set();
export function chart(el) {
  const old = echarts.getInstanceByDom(el);
  if (old) { charts.delete(old); old.dispose(); }
  const c = echarts.init(el, null, { renderer: 'canvas' });
  charts.add(c);
  return c;
}
export function disposeCharts() { charts.forEach((c) => c.dispose()); charts.clear(); }
let rt;
window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => charts.forEach((c) => !c.isDisposed() && c.resize()), 120); });

export function baseOption() {
  const text2 = css('--text-2'), text3 = css('--text-3'), border = css('--border');
  return {
    animationDuration: 700, animationEasing: 'cubicOut', animationDurationUpdate: 500,
    textStyle: { fontFamily: css('--font'), color: text2 },
    grid: { left: 8, right: 12, top: 28, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis', confine: true, className: 'ec-tip',
      backgroundColor: css('--surface'), borderColor: border, borderWidth: 1,
      textStyle: { color: css('--text'), fontSize: 12.5 }, extraCssText: 'border-radius:12px;box-shadow:' + css('--shadow') + ';padding:10px 12px;',
      axisPointer: { type: 'line', lineStyle: { color: css('--border-strong') } },
    },
    xAxis: { axisLine: { lineStyle: { color: border } }, axisTick: { show: false }, axisLabel: { color: text3, fontSize: 11.5 }, splitLine: { show: false } },
    yAxis: { axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: text3, fontSize: 11.5 }, splitLine: { lineStyle: { color: border, type: [3, 4] } }, nameTextStyle: { color: text3, fontSize: 11.5, align: 'left' } },
    legend: { textStyle: { color: text2, fontSize: 12 }, icon: 'roundRect', itemWidth: 12, itemHeight: 8, top: 0, right: 0 },
  };
}
// Мелкое слияние опций: оси/тултип объединяются с базой
export function opt(o) {
  const b = baseOption();
  const merge = (x, y) => (Array.isArray(y) ? y.map((yy) => ({ ...x, ...yy })) : { ...x, ...y });
  return {
    ...b, ...o,
    grid: { ...b.grid, ...(o.grid || {}) },
    tooltip: { ...b.tooltip, ...(o.tooltip || {}) },
    legend: o.legend === false ? { show: false } : { ...b.legend, ...(o.legend || {}) },
    xAxis: o.xAxis ? merge(b.xAxis, o.xAxis) : b.xAxis,
    yAxis: o.yAxis ? merge(b.yAxis, o.yAxis) : b.yAxis,
  };
}

// Интерполяция цвета по шкале
export function rampColor(stops, t) {
  t = Math.max(0, Math.min(1, t));
  const n = stops.length - 1, i = Math.min(n - 1, Math.floor(t * n)), f = t * n - i;
  const a = hex(stops[i]), b = hex(stops[i + 1]);
  return `rgb(${a.map((v, k) => Math.round(v + (b[k] - v) * f)).join(',')})`;
}
function hex(h) { h = h.replace('#', ''); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)); }
export const seqStops = () => [0, 1, 2, 3, 4, 5, 6].map((i) => css('--seq-' + i));
export const divStops = () => [0, 1, 2, 3, 4, 5, 6].map((i) => css('--div-' + i));
export const alpha = (hexc, a) => { const [r, g, b] = hex(hexc); return `rgba(${r},${g},${b},${a})`; };

// Плашка «демо-данные» только если файл помечен meta.mock = true
import { D } from './data.js';
export const mockBadge = (file, text, title) => (D[file]?.meta?.mock ? demoBadge(text, title) : '');
