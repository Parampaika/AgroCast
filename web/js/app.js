// Точка входа: загрузка данных, роутер по хешу, тема.
import { loadAll } from './data.js';
import { disposeCharts, state } from './util.js';
import { renderHome } from './home.js';
import { renderOverview } from './overview.js';
import { renderRegion } from './region.js';
import { renderCalc } from './calc.js';
import { renderOptimize } from './optimize.js';
import { renderMethod } from './method.js';

const ROUTES = { home: renderHome, overview: renderOverview, region: renderRegion, calc: renderCalc, optimize: renderOptimize, method: renderMethod };
const main = document.getElementById('main');

function route() {
  const [path, query = ''] = location.hash.split('?');
  const [, name = 'home', arg] = path.split('/');
  const r = ROUTES[name] ? name : 'home';
  if (r === 'region' && arg) state.region = arg;
  document.querySelectorAll('#nav a').forEach((a) => a.classList.toggle('active', a.dataset.route === (r === 'region' ? 'overview' : r)));
  disposeCharts();
  main.innerHTML = '';
  const page = document.createElement('div');
  page.className = 'page';
  main.appendChild(page);
  ROUTES[r](page);
  // #/optimize?open — раскрыть все «Подробнее» (для ссылок и скриншотов)
  if (query === 'open') page.querySelectorAll('details.more').forEach((d) => { d.open = true; });
  if (!route.first) window.scrollTo({ top: 0 });
  route.first = false;
}
route.first = true;
// Поповер «i» не выходит за края экрана: после открытия сдвигаем его внутрь окна
document.addEventListener('toggle', (e) => {
  const d = e.target;
  if (!(d instanceof HTMLDetailsElement) || !d.classList.contains('info') || !d.open) return;
  const pop = d.querySelector('.pop');
  pop.style.transform = '';
  const r = pop.getBoundingClientRect(), W = document.documentElement.clientWidth;
  let dx = 0;
  if (r.right > W - 12) dx = W - 12 - r.right;
  if (r.left + dx < 12) dx = 12 - r.left;
  if (dx) pop.style.transform = `translateX(${Math.round(dx)}px)`;
}, true);
// Поповеры «i» закрываются по клику вне их
document.addEventListener('click', (e) => document.querySelectorAll('details.info[open]').forEach((d) => { if (!d.contains(e.target)) d.open = false; }));

document.getElementById('themeToggle').addEventListener('click', () => {
  const root = document.documentElement;
  const cur = root.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  const next = cur === 'dark' ? 'light' : 'dark';
  root.dataset.theme = next;
  try { localStorage.setItem('theme', next); } catch (e) { /* приватный режим */ }
  route();
});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (!document.documentElement.dataset.theme) route(); });

loadAll().then(() => {
  window.addEventListener('hashchange', route);
  route();
}).catch((e) => {
  main.innerHTML = `<div class="card empty"><h2>Данные не загрузились</h2><p>${e.message}. Откройте сайт через локальный сервер:<br><code>uv run python -m http.server -d web 8000</code></p></div>`;
  console.error(e);
});
