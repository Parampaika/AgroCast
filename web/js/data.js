// Загрузка web/data/*.json и удобные выборки. Формат — docs/06_ui_data_contract.md.
const FILES = ['regions.geojson', 'crops', 'history', 'forecast', 'drivers', 'weather_season', 'scenarios', 'economics', 'soils', 'metrics'];
const OPTIONAL = ['optimization'];

export const D = {};

export async function loadAll() {
  const res = await Promise.all(FILES.map((f) =>
    fetch('data/' + (f.includes('.') ? f : f + '.json'), { cache: 'no-cache' }).then((r) => {
      if (!r.ok) throw new Error('Не удалось загрузить ' + f);
      return r.json();
    })));
  FILES.forEach((f, i) => { D[f.replace('.geojson', '')] = res[i]; });
  // Необязательные файлы: без них сайт работает на заглушках
  await Promise.all(OPTIONAL.map((f) => fetch(`data/${f}.json`, { cache: 'no-cache' })
    .then((r) => (r.ok ? r.json() : null)).catch(() => null).then((j) => { D[f] = j; })));
  D.cropList = D.crops.crops;
  D.cropBy = Object.fromEntries(D.cropList.map((c) => [c.crop_code, c]));
  D.regionBy = Object.fromEntries(D.regions.features.map((f) => [f.properties.okato, f.properties]));
  D.dates = D.forecast.dates;
  D.yearIdx = (y) => D.history.years.indexOf(y);
  return D;
}

export const regionName = (ok) => D.regionBy[ok]?.name || ok;
export const crop = (cc) => D.cropBy[cc];
export const fc = (ok, cc) => D.forecast.regions[ok]?.[cc];
export const fcAt = (ok, cc, i) => fc(ok, cc)?.by_date[i];
export const hist = (ok, cc) => D.history.series[ok]?.[cc];

// Регионы, где есть прогноз по культуре, отсортированные по названию
export function regionsWithCrop(cc) {
  return Object.keys(D.forecast.regions).filter((ok) => D.forecast.regions[ok][cc])
    .sort((a, b) => regionName(a).localeCompare(regionName(b), 'ru'));
}
export function regionsAll() {
  return Object.keys(D.forecast.regions).sort((a, b) => regionName(a).localeCompare(regionName(b), 'ru'));
}

// Цена, руб./т: регион → РФ
export function price(ok, cc) {
  return D.economics.region_prices[ok]?.[cc] ?? D.economics.crops[cc]?.price_rf_rub_t;
}

// Сводка по РФ на дату: сумма объёмов по регионам с прогнозом
export function rfSummary(cc, i) {
  let vol = 0, lo = 0, hi = 0, wlo = 0, whi = 0, trendVol = 0, area = 0, up = 0, down = 0;
  const regs = [];
  for (const [ok, crops] of Object.entries(D.forecast.regions)) {
    const f = crops[cc];
    if (!f || !f.area_kha) continue;
    const d = f.by_date[i];
    vol += d.p50 * f.area_kha; lo += d.p10 * f.area_kha; hi += d.p90 * f.area_kha; wlo += d.w_lo * f.area_kha; whi += d.w_hi * f.area_kha;
    trendVol += f.trend * f.area_kha; area += f.area_kha;
    if (d.dev_trend_pct >= 0) up++; else down++;
    regs.push({ ok, vol: d.p50 * f.area_kha, y: d.p50, dev: d.dev_trend_pct });
  }
  // Прошлый год: валовой сбор РФ 2025 (ЕМИСС), иначе 2024
  const h = hist('643', cc);
  let prevVol = null, prevYear = null;
  for (const y of [2025, 2024]) {
    const v = h?.gross_kt[D.yearIdx(y)];
    if (v) { prevVol = v; prevYear = y; break; }
  }
  return { vol, lo, hi, wlo, whi, trendVol, area, up, down, yieldAvg: vol / area, regs: regs.sort((a, b) => b.vol - a.vol), prevVol, prevYear,
    devTrend: (vol / trendVol - 1) * 100, devPrev: prevVol ? (vol / prevVol - 1) * 100 : null };
}
