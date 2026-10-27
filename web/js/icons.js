// Иконки культур: собственные SVG проекта (лицензия — как у репозитория, свободное использование).
// Цвет берётся из currentColor, акцент — из второго цвета.
const wheat = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M12 22V6"/>
<path d="M12 10c-2.6 0-4-1.6-4-4 2.6 0 4 1.6 4 4Zm0 0c2.6 0 4-1.6 4-4-2.6 0-4 1.6-4 4Z" fill="currentColor" fill-opacity=".25"/>
<path d="M12 14.5c-2.6 0-4-1.6-4-4 2.6 0 4 1.6 4 4Zm0 0c2.6 0 4-1.6 4-4-2.6 0-4 1.6-4 4Z" fill="currentColor" fill-opacity=".25"/>
<path d="M12 19c-2.6 0-4-1.6-4-4 2.6 0 4 1.6 4 4Zm0 0c2.6 0 4-1.6 4-4-2.6 0-4 1.6-4 4Z" fill="currentColor" fill-opacity=".25"/>
<path d="M12 6c0-1.6.6-3 1.6-4"/></svg>`;

const barley = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M12 22c0-6 .5-10 0-15"/>
<ellipse cx="9.6" cy="8.6" rx="1.6" ry="2.6" transform="rotate(-30 9.6 8.6)" fill="currentColor" fill-opacity=".25"/>
<ellipse cx="14.4" cy="8.6" rx="1.6" ry="2.6" transform="rotate(30 14.4 8.6)" fill="currentColor" fill-opacity=".25"/>
<ellipse cx="9.6" cy="13" rx="1.6" ry="2.6" transform="rotate(-30 9.6 13)" fill="currentColor" fill-opacity=".25"/>
<ellipse cx="14.4" cy="13" rx="1.6" ry="2.6" transform="rotate(30 14.4 13)" fill="currentColor" fill-opacity=".25"/>
<path d="M9 7 6 2.5M15 7l3-4.5M12 6V1.5M8.2 11.5 5 8M15.8 11.5 19 8"/></svg>`;

const maize = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M12 3c2.6 0 4 3.4 4 8s-1.6 8-4 8-4-3.4-4-8 1.4-8 4-8Z" fill="currentColor" fill-opacity=".25"/>
<path d="M9 8h6M8.4 11h7.2M8.6 14h6.8M12 3.5V18"/>
<path d="M8 13c-3 1-4.5 3.5-4.5 7 3-1 5.5-2.6 7-5M16 13c3 1 4.5 3.5 4.5 7-3-1-5.5-2.6-7-5"/>
<path d="M12 19v3"/></svg>`;

const sunflower = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<g fill="currentColor" fill-opacity=".25">
<ellipse cx="12" cy="3.6" rx="1.7" ry="2.4"/><ellipse cx="12" cy="14.4" rx="1.7" ry="2.4"/>
<ellipse cx="6.6" cy="9" rx="2.4" ry="1.7"/><ellipse cx="17.4" cy="9" rx="2.4" ry="1.7"/>
<ellipse cx="8.2" cy="5.2" rx="1.7" ry="2.4" transform="rotate(-45 8.2 5.2)"/><ellipse cx="15.8" cy="5.2" rx="1.7" ry="2.4" transform="rotate(45 15.8 5.2)"/>
<ellipse cx="8.2" cy="12.8" rx="1.7" ry="2.4" transform="rotate(45 8.2 12.8)"/><ellipse cx="15.8" cy="12.8" rx="1.7" ry="2.4" transform="rotate(-45 15.8 12.8)"/>
</g>
<circle cx="12" cy="9" r="2.8" fill="currentColor"/>
<path d="M12 17v5M12 20c-1.5-1.6-3.2-2-5-1.6 1 1.5 2.6 2 5 1.6Z"/></svg>`;

const soy = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M6 19.5C4 17 4.6 13 7.5 11.2c1.8-1.1 2.5-2.6 3-4.5.8-3 4.6-4.1 6.8-2 2.4 2.4 1.5 6-1 7.3-1.7.9-2.6 2.1-3.1 4-1 3.6-4.8 6.3-7.2 3.5Z" fill="currentColor" fill-opacity=".25"/>
<circle cx="8.6" cy="15.8" r="1.6" fill="currentColor"/><circle cx="12" cy="11.3" r="1.6" fill="currentColor"/><circle cx="15.2" cy="7.2" r="1.6" fill="currentColor"/>
<path d="M17.3 4.6 19.5 2.5"/></svg>`;

const beet = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M12 9c3.6 0 5.5 2.3 5.5 5 0 3.4-3.2 6-5.5 8-2.3-2-5.5-4.6-5.5-8 0-2.7 1.9-5 5.5-5Z" fill="currentColor" fill-opacity=".25"/>
<path d="M12 9c-.6-3-2.4-5.2-5-6 0 3 1.6 5 5 6Zm0 0c.6-3 2.4-5.2 5-6 0 3-1.6 5-5 6Zm0 0V2.5"/>
<path d="M10 14.5h1.6M12.6 17h1.4"/></svg>`;

export const ICONS = { wheat, barley, maize, sunflower, soy, beet };
export const cropIcon = (crop) => ICONS[crop.icon] || wheat;

// Иконки источников данных для экрана «Методика»
export const SRC_ICONS = {
  stats: `<svg viewBox="0 0 24 24"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>`,
  weather: `<svg viewBox="0 0 24 24"><path d="M7 18a4 4 0 0 1-.6-8A6 6 0 0 1 18 9a4.5 4.5 0 0 1 0 9H7Z"/><path d="M9 21l1-2M13 21l1-2"/></svg>`,
  soil: `<svg viewBox="0 0 24 24"><path d="M3 10h18M3 15h18M3 20h18"/><path d="M12 10V3M12 6c-2 0-3-1-3-3 2 0 3 1 3 3Zm0 0c2 0 3-1 3-3-2 0-3 1-3 3Z"/></svg>`,
  sat: `<svg viewBox="0 0 24 24"><path d="m6 10 4-4 4 4-4 4z"/><path d="m13 3 3 3M3 13l3 3M14 14l4 4M17 21a4 4 0 0 0 4-4"/></svg>`,
  price: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M10 7h3a2.5 2.5 0 0 1 0 5h-3V7Zm0 5v5M8 14.5h5"/></svg>`,
  cal: `<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="3"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>`,
};
