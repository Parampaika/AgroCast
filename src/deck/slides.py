"""Двенадцать слайдов презентации. Все цифры берутся из словаря F (src/deck/facts.py)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE
from pptx.enum.dml import MSO_LINE
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_AUTO_SIZE, MSO_ANCHOR, PP_ALIGN
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.util import Inches, Pt

from . import kit as K
from .facts import CROP_ORDER, CROP_SHORT, DATE_LABEL, DATES, NBSP, fmt, plural, unit
from .kit import (BG, BORDER, BRAND, BRAND2, BRAND_DK, BRAND_SOFT, GOLD, GOLD2, GOLD_SOFT, INK, INK2, INK3, MX, NEG, POS,
                  RAMP5, SH, SURFACE, SW, card, circle, line, picture, pill, rect, shape_text, text)

ROOT = Path(__file__).resolve().parents[2]
SHOTS = ROOT / "deck" / "assets" / "shots"
BUILD = ROOT / "deck" / "build"
CW = SW - 2 * MX  # ширина рабочей области
TOP = 1.95        # верх рабочей области под заголовком
PENDING = "ждёт данных"
SIDEBAR = 354     # ширина боковой панели сайта на скриншоте, px (236 css-px × 1,5)


# ================================================================ каркас слайда

def base(prs, kicker: str, title: str, subtitle: str | None = None, dark: bool = False):
    s = prs.slides.add_slide(prs.slide_layouts[5])  # «Только заголовок»
    bg = s.background.fill
    bg.solid()
    bg.fore_color.rgb = K.rgb(BRAND_DK if dark else BG)
    t = s.shapes.title
    t.left, t.top, t.width, t.height = Inches(MX), Inches(0.68), Inches(CW), Inches(0.62)
    tf = t.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.vertical_anchor = MSO_ANCHOR.TOP
    for side in ("left", "right", "top", "bottom"):
        setattr(tf, f"margin_{side}", 0)
    K._fill_paragraphs(tf, title, 32, "FFFFFF" if dark else INK, True, "l", K.FONT, None, None)
    text(s, MX, 0.36, CW, 0.28, kicker.upper(), size=12, color=GOLD if dark else GOLD2, bold=True, name="Рубрика")
    if subtitle:
        text(s, MX, 1.34, CW, 0.4, subtitle, size=16, color="D5E3DA" if dark else INK2, name="Подзаголовок")
    foot = "Агрокаст · кейс «Своё Фермерство», задача 5 · решение участника конкурса, не продукт банка"
    text(s, MX, 7.08, 9.5, 0.25, foot, size=10, color="9DB8A8" if dark else INK3, name="Колонтитул")
    K.slide_number(s, SW - MX - 0.6, 7.08, color="9DB8A8" if dark else INK3)
    return s


def pending_box(slide, x, y, w, h, what: str):
    r = rect(slide, x, y, w, h, fill=GOLD_SOFT, line=GOLD, radius=0.12, dash=MSO_LINE.DASH)
    shape_text(r, f"{what}: {PENDING}", size=14, color=GOLD2, bold=True)


def kpi_card(slide, x, y, w, h, big, label, dark=False, big_size=40, sub=None, big_color=None, label_size=14):
    fill = BRAND if dark else SURFACE
    card(slide, x, y, w, h, fill=fill)
    bc = big_color or (GOLD if dark else BRAND)
    text(slide, x + 0.25, y + 0.15, w - 0.5, h * 0.5, big, size=big_size, bold=True, color=bc, anchor="m")
    text(slide, x + 0.25, y + 0.15 + h * 0.5, w - 0.5, h * 0.5 - 0.25, [label] if not sub else [label, (sub, {"size": 12, "color": "C9DACE" if dark else INK3})],
         size=label_size, color="FFFFFF" if dark else INK, anchor="t", space_after=2)


# ================================================================ 1. Титул

def poly(slide, pts, fill=None, alpha=None, line_color=None, line_w=0, close=True):
    fb = slide.shapes.build_freeform(Inches(pts[0][0]), Inches(pts[0][1]), scale=1.0)
    fb.add_line_segments([(Inches(x), Inches(y)) for x, y in pts[1:]], close=close)
    s = fb.convert_to_shape()
    if fill:
        s.fill.solid()
        s.fill.fore_color.rgb = K.rgb(fill)
        if alpha is not None:
            K.set_alpha(s, alpha)
    else:
        s.fill.background()
    if line_color:
        s.line.color.rgb = K.rgb(line_color)
        s.line.width = Pt(line_w)
    else:
        s.line.fill.background()
    K._clear_effects(s)
    return s


def s01_title(prs, F, cfg):
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = K.rgb(BRAND_DK)
    t = s.shapes.title
    t.left, t.top, t.width, t.height = Inches(MX), Inches(1.15), Inches(7.0), Inches(1.4)
    tf = t.text_frame
    tf.word_wrap, tf.auto_size, tf.vertical_anchor = True, MSO_AUTO_SIZE.NONE, MSO_ANCHOR.TOP
    for side in ("left", "right", "top", "bottom"):
        setattr(tf, f"margin_{side}", 0)
    K._fill_paragraphs(tf, "Агрокаст", 80, "FFFFFF", True, "l", K.FONT, None, None)
    text(s, MX, 0.62, 7.4, 0.3, "СТИПЕНДИЯ РОССЕЛЬХОЗБАНКА 2026–2027 · «СВОЁ ФЕРМЕРСТВО» · ЗАДАЧА 5", size=12, color=GOLD,
         bold=True, name="Рубрика")
    text(s, MX, 2.5, 6.9, 1.3, "Калькулятор урожайности участка: регион, площадь, почва, сорт, агротехника → т/га, сбор, выручка, маржа",
         size=26, color="FFFFFF", line_spacing=1.0, name="Суть")
    text(s, MX, 3.95, 7.0, 0.5, "Под капотом — региональная модель на 5 дат сезона и оптимизация посевов", size=14, color="D5E3DA")
    # крупные цифры
    chips = [(f"−{fmt(F['ladder']['gain_end'])}{NBSP}%", "ошибки к прогнозу «как в прошлом году»"),
             (fmt(F["cfg"]["total"]), "конфигураций моделей на единой проверке")]
    if "opt" in F:
        chips.append((f"+{fmt(F['opt']['d5']['gain_ha'])}{NBSP}₽/га", "от малых изменений плана посевов"))
    x = MX
    for big, lab in chips:
        text(s, x, 4.55, 2.3, 0.65, big, size=34, bold=True, color=GOLD, anchor="m")
        text(s, x, 5.2, 2.15, 0.75, lab, size=13, color="D5E3DA")
        x += 2.4
    text(s, MX, 6.3, 7.0, 0.3, [[(cfg["author"], {"bold": True, "color": "FFFFFF"}), (f" · {cfg['role']}", {})]], size=15,
         color="D5E3DA", name="Автор")
    text(s, MX, 6.65, 7.0, 0.3, f"{cfg['date_label']} · решение участника конкурса, не продукт банка", size=12, color="9DB8A8")
    # справа: схема «прогноз уточняется» (пропорции — медианы реальных интервалов итоговых моделей)
    px, py, pw, ph = 8.0, 0.9, 4.73, 5.9
    pn = rect(s, px, py, pw, ph, fill=BRAND, radius=0.2)
    text(s, px + 0.35, py + 0.3, pw - 0.7, 0.3, "ПРОГНОЗ УТОЧНЯЕТСЯ ПО МЕРЕ СЕЗОНА", size=11, bold=True, color=GOLD)
    cols = [px + 0.65 + i * ((pw - 1.3) / 4) for i in range(5)]
    outer, inner = F["final"]["fan_outer"], F["final"]["fan_inner"]
    k = 0.05   # дюймов на 1 % полуширины
    cy = [3.75, 3.65, 3.5, 3.35, 3.2]
    top = [(c, y - o * k) for c, y, o in zip(cols, cy, outer)]
    bot = [(c, y + o * k) for c, y, o in zip(cols, cy, outer)]
    poly(s, top + bot[::-1], fill=GOLD, alpha=28)
    itop = [(c, y - o * k) for c, y, o in zip(cols, cy, inner)]
    ibot = [(c, y + o * k) for c, y, o in zip(cols, cy, inner)]
    poly(s, itop + ibot[::-1], fill=GOLD, alpha=62)
    for c in cols:
        line(s, c, py + 1.0, c, py + ph - 1.25, color="3E6E58", width=0.75, dash=MSO_LINE.DASH)
    poly(s, list(zip(cols, cy)), line_color=GOLD, line_w=3.5, close=False)
    for c, y, d in zip(cols, cy, DATES):
        circle(s, c - 0.09, y - 0.09, 0.18, fill="FFFFFF")
        text(s, c - 0.45, py + ph - 1.15, 0.9, 0.3, DATE_LABEL[d].replace("Конец сезона", "конец"), size=12, color="FFFFFF",
             align="c", bold=True)
    text(s, px + 0.35, py + ph - 0.75, pw - 0.7, 0.55,
         "Схема. Широкая полоса — 80 % интервал по ошибкам прошлых лет, яркая — разброс погоды, которая ещё не наступила",
         size=11, color="C9DACE")
    return s


# ================================================================ 2. Задача

def s02_task(prs, F, cfg):
    s = base(prs, "Задача кейса", "Калькулятор участка: что сеять и сколько вложить",
             "Кейс: оценить урожайность по участку, показать т/га и общий объём по культурам, объяснить пользу для затрат и доходов")
    w, gap = 3.85, 0.29
    cards = [
        ("₽", "Фермеру", ["Что сеять: прогноз по культурам с 1 мая, а не после уборки",
                          "Сколько вложить: семена, удобрения, кредит под ожидаемый урожай",
                          "Что продавать вперёд: объём и диапазон «плохой — обычный — хороший год»"], SURFACE),
        ("%", "Банку", ["Риск кредитов по регионам и культурам виден до уборки",
                        "График платежей под реальный, а не средний урожай",
                        "Ранний сигнал: проблемный сезон заметен уже летом"], SURFACE),
        ("→", "Наш ответ", ["Калькулятор: регион, площадь, почва, сорт, агротехника → т/га, сбор, выручка, маржа",
                            "Основа — региональный прогноз на 5 дат сезона с честным интервалом",
                            "Оптимизация: что изменить в плане при том же риске"], BRAND),
    ]
    for i, (glyph, head, items, fill) in enumerate(cards):
        x = MX + i * (w + gap)
        dark = fill == BRAND
        card(s, x, 2.0, w, 3.75, fill=fill)
        circle(s, x + 0.3, 2.3, 0.62, fill=GOLD if dark else BRAND_SOFT, label=glyph, color=BRAND_DK if dark else BRAND, size=24)
        text(s, x + 1.1, 2.3, w - 1.3, 0.62, head, size=24, bold=True, color="FFFFFF" if dark else INK, anchor="m")
        text(s, x + 0.3, 3.2, w - 0.6, 2.45, items, size=15, color="E8F0EA" if dark else INK2, space_after=9)
    r = rect(s, MX, 6.0, CW, 0.85, fill=GOLD_SOFT, radius=0.14)
    text(s, MX + 0.35, 6.0, CW - 0.7, 0.85,
         [[("Главная идея: ", {"bold": True, "color": GOLD2}),
           ("не «модель предсказала N т/га», а рекомендация — изменить план немного и получить заметный эффект.", {})]],
         size=18, color=INK, anchor="m")
    return s


# ================================================================ 3. Масштаб

def s03_scale(prs, F, cfg):
    s = base(prs, "Масштаб работы", "Исследование на большом массиве данных, а не формула")
    L = F["layers"]
    tiles = [
        (str(F["n_sources"]), "источников открытых данных",
         f"ЕМИСС ({F['n_emiss']} {plural(F['n_emiss'], 'показатель', 'показателя', 'показателей')}), ERA5, NASA POWER, SoilGrids, MODIS, GGCMI, FAOSTAT, USDA…", False),
        (unit(F["raw_gb"], 1, "ГБ"), "сырых данных",
         f"{fmt(F['raw_files'] / 1e3, 1)}{NBSP}тыс. файлов, {fmt(F['rows_mln'])}{NBSP}млн строк наблюдений; со всеми слоями — {fmt(F['all_gb'], 1)}{NBSP}ГБ", False),
        (fmt(F["model_cols"]), f"{plural(F['model_cols'], 'столбец', 'столбца', 'столбцов')} в таблице признаков",
         f"{fmt(F['model_rows'] / 1e3)}{NBSP}тыс. строк «субъект × культура × год»: погода, окна культур, почвы, спутник", False),
        (fmt(F["cfg"]["total"]), "конфигураций моделей",
         f"на одной проверке 2012–2025; {fmt(F['cfg']['optuna_trials'] / 1e3, 1)}{NBSP}тыс. попыток Optuna", True),
        (f"{F['n_regions']} × {F['n_crops']}", "субъектов РФ × культур",
         f"{F['years']}, {F['n_points']} точек пашни для погоды и почв", False),
        (str(F["n_tests"]), "автоматических тестов",
         "чистота данных, защита от утечек, проверка оптимизатора", False),
    ]
    w, h, gx, gy = 3.85, 2.3, 0.29, 0.3
    for i, (big, lab, sub, dark) in enumerate(tiles):
        x = MX + (i % 3) * (w + gx)
        y = 1.65 + (i // 3) * (h + gy)
        card(s, x, y, w, h, fill=BRAND if dark else SURFACE)
        text(s, x + 0.3, y + 0.15, w - 0.6, 0.95, big, size=50, bold=True, color=GOLD if dark else BRAND, anchor="m")
        text(s, x + 0.3, y + 1.1, w - 0.6, 0.35, lab, size=17, bold=True, color="FFFFFF" if dark else INK)
        text(s, x + 0.3, y + 1.48, w - 0.6, 0.75, sub, size=12, color="C9DACE" if dark else INK2)
    return s


# ================================================================ 4. Пайплайн

def s04_pipeline(prs, F, cfg):
    s = base(prs, "Конвейер данных", "Четыре слоя данных от сырья до сайта")
    L = F["layers"]
    order = [("emiss", "ЕМИСС"), ("era5_om", "ERA5"), ("nasa_power", "NASA POWER"), ("soilgrids", "SoilGrids"),
             ("modis_", "MODIS"), ("crop_calendar_ggcmi", "GGCMI"), ("faostat", "FAOSTAT"), ("usda_psd", "USDA PSD"),
             ("gossortrf", "Госреестр сортов"), ("rosstat", "Росстат")]
    chips = [lab for key, lab in order if any(d.startswith(key) for d in F["sources"])]
    other = sum(1 for d in F["sources"] if not any(d.startswith(key) for key, _ in order))
    if other:
        chips.append(f"и ещё {other}")
    widths = [0.36 + 0.082 * len(c) for c in chips]
    gap_c = (CW - sum(widths)) / max(1, len(chips) - 1)
    x = MX
    for c, w in zip(chips, widths):
        pill(s, x, 1.65, w, 0.36, c, fill=BRAND_SOFT, color=BRAND, size=12)
        x += w + gap_c
    stages = [
        ("raw", str(F["n_sources"]), "источников", f"{fmt(L['raw']['files'] / 1e3, 1)} тыс. файлов · {fmt(L['raw']['gb'], 1)} ГБ", "как скачано, с докачкой и логами"),
        ("interim", str(L["interim"]["files"]), "файлов", f"{fmt(L['interim']['rows_mln'], 1)} млн строк", "сырой разбор без чистки: SDMX → таблицы"),
        ("processed", str(L["processed"]["files"]), "таблиц", f"{fmt(L['processed']['rows_mln'], 1)} млн строк", "суточная погода, признаки, первые модели"),
        ("clean", str(F["clean_tables"]), "таблиц", f"{F['n_tests']} {plural(F['n_tests'], 'тест', 'теста', 'тестов')}", "правила чистки; строки не удаляются, а помечаются флагами"),
        ("модель", fmt(F["model_cols"]), "признаков", f"{fmt(F['cfg']['total'])} конфигураций", "5 дат × 7 культур, проверка по времени"),
        ("сайт", "4", "экрана", "калькулятор · регионы · карточка · оптимизация", "статический, работает без сервера"),
    ]
    n = len(stages)
    gap = 0.12
    w = (CW - gap * (n - 1)) / n
    ramp = ["A9C6B3", "7FAA93", "4F8A6C", BRAND2, BRAND, GOLD]
    for i, (name, big, unit_, mid, desc) in enumerate(stages):
        x = MX + i * (w + gap)
        ch = rect(s, x, 2.35, w + (0.0 if i == n - 1 else 0.18), 0.8, fill=ramp[i],
                  shape=MSO_SHAPE.PENTAGON if i == 0 else (MSO_SHAPE.PENTAGON if i == n - 1 else MSO_SHAPE.CHEVRON))
        shape_text(ch, name, size=18, bold=True, color=BRAND_DK if i in (0, 5) else "FFFFFF", margin=0.05)
        card(s, x, 3.4, w, 3.1)
        text(s, x + 0.18, 3.5, w - 0.3, 0.7, big, size=38, bold=True, color=BRAND, anchor="m")
        text(s, x + 0.18, 4.18, w - 0.3, 0.3, unit_, size=15, bold=True, color=INK)
        text(s, x + 0.18, 4.65, w - 0.3, 0.85, mid, size=13, bold=True, color=BRAND2)
        text(s, x + 0.18, 5.5, w - 0.3, 0.95, desc, size=12, color=INK2)
    return s


# ================================================================ 5. Методика

def s05_method(prs, F, cfg):
    s = base(prs, "Методика", "Честная проверка: модель видит только прошлое")
    # --- A: формула
    ax, aw = MX, 6.9
    card(s, ax, 1.65, aw, 1.45)
    text(s, ax + 0.3, 1.78, aw - 0.6, 0.3, "1 · МОДЕЛЬ «ТРЕНД × ПОГОДА»", size=12, bold=True, color=GOLD2)
    b1 = rect(s, ax + 0.3, 2.2, 2.35, 0.7, fill=BRAND, radius=0.12)
    shape_text(b1, "тренд по годам < t", size=15, bold=True, color="FFFFFF")
    text(s, ax + 2.7, 2.2, 0.4, 0.7, "×", size=30, bold=True, color=INK2, align="c", anchor="m")
    b2 = rect(s, ax + 3.15, 2.2, 3.45, 0.7, fill=GOLD_SOFT, radius=0.12)
    shape_text(b2, [[("1 + ", {"bold": True}), ("эффект погоды, спутника, почвы", {})]], size=15, color=INK)
    # --- B: сетка «что известно на дату»
    by = 3.3
    card(s, ax, by, aw, 3.1)
    text(s, ax + 0.3, by + 0.13, aw - 0.6, 0.3, "2 · ПЯТЬ ДАТ ПРОГНОЗА: БУДУЩЕЕ ЗАМАСКИРОВАНО", size=12, bold=True, color=GOLD2)
    months = ["сен", "окт", "ноя", "дек", "янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт"]
    known = [8, 9, 10, 11, 14]
    c0, cw, ch = ax + 1.5, 0.355, 0.32
    for j, m in enumerate(months):
        text(s, c0 + j * cw, by + 0.52, 0.31, 0.22, m, size=10, color=INK3, align="c")
    for i, d in enumerate(DATES):
        yy = by + 0.8 + i * (ch + 0.05)
        text(s, ax + 0.3, yy, 1.15, ch, DATE_LABEL[d].replace("Конец сезона", "Конец сезона"), size=13, bold=True, color=INK, anchor="m")
        for j in range(14):
            ok = j < known[i]
            r = rect(s, c0 + j * cw, yy, 0.31, ch, fill=BRAND2 if ok else "ECE8DC", radius=0.05)
    text(s, ax + 0.3, by + 2.72, aw - 0.6, 0.3,
         [[("■ ", {"color": BRAND2}), ("известно на дату   ", {}), ("■ ", {"color": "D8D2C2"}), ("скрыто: в прогноз не попадает", {})]],
         size=12, color=INK2)
    # --- C: скользящая проверка
    cx, cwid = 7.8, SW - MX - 7.8
    card(s, cx, 1.65, cwid, 4.75)
    text(s, cx + 0.3, 1.78, cwid - 0.6, 0.3, "3 · СКОЛЬЗЯЩАЯ ПРОВЕРКА 2012–2025", size=12, bold=True, color=GOLD2)
    years = list(range(2012, 2026))
    x0, x1 = cx + 0.95, cx + cwid - 0.35
    sx = lambda yr: x0 + (yr - 2000) / 26 * (x1 - x0)  # noqa: E731
    ry0, rh = 2.3, 0.265
    for i, yr in enumerate(years):
        yy = ry0 + i * rh
        text(s, cx + 0.3, yy - 0.02, 0.6, rh, str(yr), size=10, color=INK2, anchor="m", align="r")
        rect(s, sx(2000), yy + 0.04, max(0.05, sx(yr) - sx(2000) - 0.03), rh - 0.1, fill="A9C6B3", radius=0.04)
        rect(s, sx(yr), yy + 0.02, sx(yr + 1) - sx(yr), rh - 0.06, fill=GOLD, radius=0.04)
    text(s, cx + 0.3, ry0 + 14 * rh + 0.1, cwid - 0.6, 0.55,
         [[("■ ", {"color": "A9C6B3"}), ("обучение: только годы до T   ", {}), ("■ ", {"color": GOLD}), ("прогноз года T", {})]], size=12, color=INK2)
    # --- подпись внизу
    text(s, MX, 6.47, CW, 0.5,
         ["Тренды и нормы — только по годам < t · гиперпараметры подобраны по 2012–2018, годы 2019–2025 отложены · случайного разбиения нет",
          [("Модель обучена на данных региона; ", {"bold": True}),
           ("почва, сорт, агротехника — множители-допущения. «Конец сезона» — оценка по фактической погоде", {})]],
         size=12, color=INK2, space_after=1)
    return s


# ================================================================ 6. Лесенка

def s06_ladder(prs, F, cfg):
    L = F["ladder"]
    s = base(prs, "Главный результат", f"Лесенка моделей: ошибка снижена на {fmt(L['gain_end'])} %",
             "Пять ступеней на одной проверке 2012–2025: средняя ошибка прогноза урожайности, % от факта (MAPE)")
    names = ["Прошлый год", "Тренд\nбез погоды", "Тренд +\nпогода (Ridge)", "Бустинг по\nумолчанию + спутник", "Optuna +\nансамбль"]
    cd = CategoryChartData()
    cd.categories = names
    cd.add_series("MAPE, %", [round(v, 1) for v in L["mape"]])
    ch = K.add_chart(s, XL_CHART_TYPE.COLUMN_CLUSTERED, cd, MX, 1.95, 8.1, 4.95, name="Лесенка моделей")
    ch.has_legend = False
    K.style_axes(ch, cat_size=13, show_val_axis=False, grid=False, vmin=0, vmax=24)
    plot = ch.plots[0]
    plot.gap_width = 35
    plot.vary_by_categories = False
    K.labels(plot, '0.0" %"', size=18, color=INK, bold=True, pos=XL_LABEL_POSITION.OUTSIDE_END)
    K.color_points(plot.series[0], RAMP5)
    # справа: главная цифра и два пояснения
    x = MX + 8.4
    w = SW - MX - x
    card(s, x, 1.95, w, 2.2, fill=BRAND)
    text(s, x + 0.3, 2.05, w - 0.6, 1.0, f"−{fmt(L['gain_end'])}{NBSP}%", size=60, bold=True, color=GOLD, anchor="m")
    text(s, x + 0.3, 3.1, w - 0.6, 1.0, f"ошибки (MAE и MAPE) к прогнозу «как в прошлом году», среднее по {F['n_crops']} культурам", size=14, color="E8F0EA")
    card(s, x, 4.35, w, 2.55)
    text(s, x + 0.3, 4.48, w - 0.6, 2.4,
         [[("Погода даёт основное: ", {"bold": True, "color": BRAND}), (f"−{fmt(L['gain'][2])} % уже у линейной модели.", {})],
          [("Бустинг «из коробки» со спутником ", {"bold": True, "color": BRAND}), (f"не лучше (−{fmt(L['gain'][3])} %): выигрыш — от перебора и ансамбля.", {})],
          [("Отложенные 2019–2025: ", {"bold": True, "color": BRAND}), (f"−{fmt(L['by_date']['late'][-1])} %, подгонки нет.", {})]],
         size=14, color=INK2, space_after=7)
    return s


# ================================================================ 7. По датам и культурам

def s07_dates(prs, F, cfg):
    L, Fin = F["ladder"], F["final"]
    s = base(prs, "Качество по датам и культурам", f"Ошибка падает уже с 1 мая: −{fmt(L['by_date']['all'][0])} %, к концу сезона −{fmt(L['gain_end'])} %")
    # слева: линия по датам
    text(s, MX, 1.62, 6.3, 0.3, "Снижение ошибки к «прошлому году», %", size=15, bold=True, color=INK)
    cd = CategoryChartData()
    cd.categories = [DATE_LABEL[d] for d in DATES]
    cd.add_series("Все годы 2012–2025", list(L["by_date"]["all"]))
    cd.add_series("Отложенные 2019–2025", list(L["by_date"]["late"]))
    ch = K.add_chart(s, XL_CHART_TYPE.COLUMN_CLUSTERED, cd, MX - 0.1, 1.95, 6.5, 3.45, name="Качество по датам")
    K.style_axes(ch, cat_size=12, show_val_axis=False, grid=False, vmin=0, vmax=36)
    K.legend(ch, XL_LEGEND_POSITION.BOTTOM, 12)
    plot = ch.plots[0]
    plot.gap_width = 55
    plot.overlap = -8
    for ser, colr in zip(plot.series, (BRAND, GOLD)):
        ser.format.fill.solid()
        ser.format.fill.fore_color.rgb = K.rgb(colr)
        K.labels(ser, "0", size=13, color=INK, bold=True, pos=XL_LABEL_POSITION.OUTSIDE_END)
    # справа: столбцы по культурам
    rx = 7.2
    text(s, rx, 1.62, SW - MX - rx, 0.3, "По культурам, конец сезона, %", size=15, bold=True, color=INK)
    items = sorted(L["by_crop"].items(), key=lambda kv: -kv[1])
    cd2 = CategoryChartData()
    cd2.categories = [CROP_SHORT[k] for k, _ in items]
    cd2.add_series("Снижение ошибки", [v for _, v in items])
    ch2 = K.add_chart(s, XL_CHART_TYPE.BAR_CLUSTERED, cd2, rx - 0.1, 1.95, SW - MX - rx + 0.1, 3.45, name="Качество по культурам")
    ch2.has_legend = False
    K.style_axes(ch2, cat_size=12, show_val_axis=False, grid=False, vmin=0, vmax=48)
    ch2.category_axis.reverse_order = True
    p2 = ch2.plots[0]
    p2.gap_width = 40
    p2.vary_by_categories = False
    p2.series[0].format.fill.solid()
    p2.series[0].format.fill.fore_color.rgb = K.rgb(BRAND2)
    K.labels(p2, '0" %"', size=13, color=INK, bold=True, pos=XL_LABEL_POSITION.OUTSIDE_END)
    # плитки про интервалы и озимую
    tw, gap = (CW - 2 * 0.29) / 3, 0.29
    tiles = [
        (f"{fmt(100 * Fin['cov_min'])}–{fmt(100 * Fin['cov_max'])}{NBSP}%", "покрытие 80{0}%-го интервала".format(NBSP), f"доля фактов внутри интервала у всех {Fin['n_models']} итоговых моделей"),
        (f"±{fmt(Fin['halfwidth_end'])}{NBSP}%", "полуширина интервала", f"к концу сезона; 1 мая — ±{fmt(Fin['halfwidth_may'])} %: честный диапазон, не «точка»"),
        (f"−{fmt(Fin['gain_may']['winter_wheat'])}{NBSP}%", f"озимая пшеница с 1{NBSP}мая", "к лучшему простому прогнозу; остальные культуры — с июля"),
    ]
    for i, (big, lab, sub) in enumerate(tiles):
        x = MX + i * (tw + gap)
        card(s, x, 5.55, tw, 1.35)
        text(s, x + 0.25, 5.6, 1.7, 0.7, big, size=28, bold=True, color=BRAND, anchor="m")
        text(s, x + 1.95, 5.62, tw - 2.1, 0.66, lab, size=13, bold=True, color=INK, anchor="m")
        text(s, x + 0.25, 6.35, tw - 0.5, 0.45, sub, size=11, color=INK2)
    return s


# ================================================================ 8. Драйверы

def s08_drivers(prs, F, cfg):
    if "shap" not in F:
        s = base(prs, "Что двигает урожайность", "Что двигает урожайность: погода и спутник")
        pending_box(s, MX, 2.0, CW, 3, "Вклад признаков (SHAP)")
        return s
    Sh = F["shap"]
    w_lo, w_hi = Sh["weather_rng"]
    s_lo, s_hi = Sh["sat_rng"]
    s = base(prs, "Что двигает урожайность", f"Погода даёт {fmt(w_lo)}–{fmt(w_hi)} % прогноза, спутник — {fmt(s_lo)}–{fmt(s_hi)} %",
             "Доля блоков признаков в суммарном вкладе SHAP по культурам (LightGBM, TreeSHAP)")
    cd = CategoryChartData()
    cd.categories = [CROP_SHORT[k] for k in CROP_ORDER]
    for g in Sh["groups"]:
        cd.add_series(g, [round(v, 1) for v in Sh["share"][g]])
    ch = K.add_chart(s, XL_CHART_TYPE.BAR_STACKED_100, cd, MX - 0.1, 1.95, 7.6, 4.95, name="Вклад блоков признаков")
    K.style_axes(ch, cat_size=13, show_val_axis=False, grid=False)
    ch.category_axis.reverse_order = True
    K.legend(ch, XL_LEGEND_POSITION.BOTTOM, 11)
    plot = ch.plots[0]
    plot.gap_width = 40
    plot.overlap = 100
    cols = [BRAND, GOLD, "F2DFA8", "A9C6B3", "C9C4B5"]
    lab_col = ["FFFFFF", INK, INK, INK, INK]
    for ser, c, lc in zip(plot.series, cols, lab_col):
        ser.format.fill.solid()
        ser.format.fill.fore_color.rgb = K.rgb(c)
        ser.format.line.color.rgb = K.rgb("FFFFFF")
        ser.format.line.width = Pt(1.5)
        K.labels(ser, '[>=7]0;""', size=12, color=lc, bold=True, pos=XL_LABEL_POSITION.CENTER)
    rx = 8.4
    card(s, rx, 1.95, SW - MX - rx, 4.95)
    text(s, rx + 0.3, 2.1, SW - MX - rx - 0.6, 0.3, "ЧТО ГОВОРЯТ ГЛАВНЫЕ ПРИЗНАКИ", size=12, bold=True, color=GOLD2)
    items = [("Озимая пшеница", "снег и минимальная температура в марте — выход из зимы; перегрев поверхности в мае–июне (LST)"),
             ("Кукуруза", "дефицит влажности воздуха в июле — засуха в цветение; влага почвы в августе"),
             ("Сахарная свёкла", "водный баланс окна вегетации и ГТК — самая влаголюбивая культура"),
             ("Ячмень", "жаркий июнь и тёплые июльские ночи вредят")]
    paras = []
    for k, v in items:
        paras.append([(k + ": ", {"bold": True, "color": BRAND}), (v, {})])
    text(s, rx + 0.3, 2.5, SW - MX - rx - 0.6, 3.3, paras, size=14, color=INK2, space_after=10)
    text(s, rx + 0.3, 5.75, SW - MX - rx - 0.6, 1.05,
         [[("Спутник сильнее всего у ", {}), (" и ".join(Sh["sat_top"]), {"bold": True, "color": BRAND}),
           (": у них погода региона объясняет меньше, а состояние посевов видно из космоса.", {})]],
         size=13, color=INK2)
    return s


# ================================================================ 9. Оптимизация

def s09_opt(prs, F, cfg):
    s = base(prs, "Оптимизация структуры посевов", "Изменить план немного — получить заметный эффект",
             "Сценарная стохастическая оптимизация структуры посевов с CVaR и ограничением на отклонение от плана")
    if "opt" not in F:
        pending_box(s, MX, 2.1, CW, 3, "Результаты оптимизации")
        return s
    o = F["opt"]
    # левый график: δ → эффект (XY)
    cx, cw = MX, 7.0
    text(s, cx, 1.85, cw, 0.3, "Выигрыш по всем субъектам, млрд ₽ в год, при сдвиге структуры не более δ п.п.", size=14, bold=True, color=INK)
    cd = XyChartData()
    a_ = cd.add_series("Средняя прибыль")
    b_ = cd.add_series("Худшие 20 % сезонов")
    for x_, m_, c_ in zip(o["curve"]["delta_pp"], o["curve"]["mean_bln"], o["curve"]["cvar_bln"]):
        a_.add_data_point(x_, m_)
        b_.add_data_point(x_, c_)
    p_ = cd.add_series("Точки")
    pts = [(5, o["d5"]["gain_bln"]), (10, o["d10"]["gain_bln"])]
    for x_, y_ in pts:
        p_.add_data_point(x_, y_)
    ch = K.add_chart(s, XL_CHART_TYPE.XY_SCATTER_LINES_NO_MARKERS, cd, cx - 0.1, 2.25, cw + 0.1, 3.5, name="Кривая δ → эффект")
    ch.has_legend = False
    K.style_axes(ch, cat_size=11, val_size=11, vmin=0, vmax=250, major=50)
    ca = ch.category_axis
    ca.minimum_scale, ca.maximum_scale, ca.major_unit = 0, 30, 5
    ca.has_major_gridlines = False
    ca.tick_labels.number_format = '0" п.п."'
    ca.tick_labels.number_format_is_linked = False
    ca.format.line.color.rgb = K.rgb(BORDER)
    sers = ch.plots[0].series
    for ser, colr, dash in ((sers[0], BRAND, None), (sers[1], GOLD2, MSO_LINE.DASH)):
        ser.smooth = False
        ser.format.line.color.rgb = K.rgb(colr)
        ser.format.line.width = Pt(3.25)
        if dash:
            ser.format.line.dash_style = dash
    pr = sers[2]
    pr.format.line.fill.background()
    pr.marker.style = XL_MARKER_STYLE.CIRCLE
    pr.marker.size = 13
    pr.marker.format.fill.solid()
    pr.marker.format.fill.fore_color.rgb = K.rgb(GOLD)
    pr.marker.format.line.color.rgb = K.rgb(BRAND_DK)
    # подписи точек — в пустом углу графика
    text(s, cx + 0.95, 2.45, 4.6, 0.8,
         [[("● ", {"color": GOLD2}), (f"5 п.п.: +{fmt(pts[0][1])} млрд ₽ в год", {})],
          [("● ", {"color": GOLD2}), (f"10 п.п.: +{fmt(pts[1][1])} млрд ₽ в год", {})]],
         size=15, bold=True, color=BRAND_DK, space_after=3)
    # подписи линий
    text(s, cx + 0.2, 5.82, 3.2, 0.3, [[("━ ", {"color": BRAND}), ("средняя прибыль", {})]], size=12, color=INK2)
    text(s, cx + 2.3, 5.82, 4.5, 0.3, [[("╌ ", {"color": GOLD2}), ("прибыль в худших 20 % сезонов", {})]], size=12, color=INK2)
    text(s, cx + 0.2, 6.15, cw - 0.2, 0.4,
         f"Первые 10 п.п. дают {fmt(o['share_d10_of_d30'])} % эффекта, достижимого при 30 п.п.: дальше кривая выходит на плато",
         size=12, color=INK2)
    # справа: числа
    x = 8.0
    w = SW - MX - x
    d5 = o["d5"]
    pct = f" (+{fmt(d5['gain_pct'])}{NBSP}%)" if d5["gain_pct"] is not None else ""
    sub1 = None
    if "median_ha" in d5:
        sub1 = f"медиана по субъектам +{fmt(d5['median_ha'])}{NBSP}₽/га, выигрыш у {fmt(d5['share_up'])}{NBSP}%"
    kpi_card(s, x, 1.85, w, 1.6, f"+{fmt(d5['gain_ha'])}{NBSP}₽/га", f"ожидаемой прибыли при сдвиге ≤ 5{NBSP}п.п.{pct}", dark=True,
             big_size=36, label_size=13, sub=sub1)
    kpi_card(s, x, 3.6, w, 1.45, f"+{fmt(d5['cvar_gain_ha'])}{NBSP}₽/га", "в худших 20 % сезонов (CVaR)",
             big_size=32, label_size=13,
             sub=f"худший сезон лучше в {d5['worst_better']} из {d5['n']} {plural(d5['n'], 'субъекта', 'субъектов', 'субъектов')}")
    bt = o["bt"]["d5"]
    card(s, x, 5.2, w, 1.4, fill=GOLD_SOFT)
    text(s, x + 0.25, 5.26, w - 0.5, 1.3,
         [[("Проверка на 2012–2025 ", {"bold": True, "color": GOLD2}), (f"({fmt(o['bt']['n'])} пар «субъект × год», только данные до года t, исторические сценарии): ", {})],
          [(f"факт +{fmt(bt['real'])} ₽/га", {"bold": True}), (f" — {fmt(bt['realization'])} % обещанного; лучше текущего плана в {fmt(bt['win'])} % случаев", {})]],
         size=13, color=INK, space_after=4)
    text(s, MX, 6.72, CW, 0.28,
         f"{o['n_regions']} {plural(o['n_regions'], 'субъект', 'субъекта', 'субъектов')}, {fmt(o['pool_mha'], 1)} млн га, {o['n_scen']} погодных {plural(o['n_scen'], 'сценарий', 'сценария', 'сценариев')}. "
         "Затраты на гектар — допущения: эффект читать как верхнюю оценку", size=11, color=INK3)
    return s


# ================================================================ 10. Сайт

def _crop(src: Path, dst: Path, box):
    im = Image.open(src)
    im.crop(box).save(dst)
    return dst


def s10_site(prs, F, cfg):
    s = base(prs, "Прототип", "Агрокаст: калькулятор участка — главный экран сайта")
    BUILD.mkdir(parents=True, exist_ok=True)
    top, lw, lh = 1.85, 5.2, 4.15
    calc, ov, opt = SHOTS / "calc.png", SHOTS / "overview.png", SHOTS / "optimize.png"
    if not calc.exists():
        pending_box(s, MX, 2.0, CW, 3, "Скриншоты сайта (src/deck/shots.py)")
        return s
    imc = Image.open(calc)
    W = imc.size[0] - SIDEBAR
    p1 = _crop(calc, BUILD / "shot_calc.png", (SIDEBAR, 375, imc.size[0], 375 + int(W * lh / lw)))
    picture(s, p1, MX, top, lw, lh, descr="Скриншот сайта: калькулятор участка — ввод региона, площади, почвы, сорта и агротехники, результат в т/га, сборе, выручке и марже")
    pill(s, MX, top - 0.42, 3.4, 0.3, "Калькулятор участка · ввод и результат", fill=BRAND, color="FFFFFF", size=11)
    rx = MX + lw + 0.33
    rw = SW - MX - rx
    rh = (lh - 0.45) / 2
    if ov.exists():
        imo = Image.open(ov)
        w2 = 1146
        p2 = _crop(ov, BUILD / "shot_overview.png", (SIDEBAR + 60, 780, SIDEBAR + 60 + w2, 780 + int(w2 * rh / rw)))
        picture(s, p2, rx, top, rw, rh, descr="Скриншот сайта: карта регионов — региональная модель, основа калькулятора")
        pill(s, rx, top - 0.42, 3.5, 0.3, "Карта регионов · основа калькулятора", fill=BRAND, color="FFFFFF", size=11)
    if opt.exists():
        imp = Image.open(opt)
        W3 = imp.size[0] - SIDEBAR
        p3 = _crop(opt, BUILD / "shot_optimize.png", (SIDEBAR, 470, imp.size[0], 470 + int(W3 * rh / rw)))
        picture(s, p3, rx, top + rh + 0.42, rw, rh, descr="Скриншот сайта: оптимизация плана посевов, что изменить и эффект")
        pill(s, rx, top + rh + 0.07, 2.3, 0.3, "Оптимизация плана", fill=BRAND, color="FFFFFF", size=11)
    link = cfg.get("site_url") or cfg.get("repo_url")
    link_txt = link if link else "[заполнить: ссылка на репозиторий]"
    card(s, MX, 6.15, CW, 0.82, fill=SURFACE)
    text(s, MX + 0.3, 6.17, CW - 0.6, 0.78,
         [[("Считает модель: ", {"bold": True, "color": BRAND}), ("региональный прогноз по погоде и данным региона. ", {}),
           ("Допущения: ", {"bold": True, "color": GOLD2}), ("почва, сорт, агротехника, затраты. «Итог сезона» — оценка по фактической погоде, не прогноз.", {})],
          [("Код и сайт: ", {"bold": True, "color": BRAND}), (link_txt, {"color": INK if link else NEG, "bold": not link})]],
         size=13, color=INK2, anchor="m", space_after=2)
    return s


# ================================================================ 11. Ограничения и развитие

def s11_next(prs, F, cfg):
    Fin = F["final"]
    s = base(prs, "Честно и дальше", "Ограничения и план развития")
    lw = 5.4
    card(s, MX, 1.65, lw, 5.2)
    text(s, MX + 0.3, 1.8, lw - 0.6, 0.3, "ОГРАНИЧЕНИЯ", size=12, bold=True, color=GOLD2)
    lim = [
        ("Модель — региональная, не полевая.", " Почва, сорт и агротехника — множители-допущения: открытых данных по хозяйствам нет."),
        ("Короткие ряды:", " 14 лет проверки, различия в 1–2 п. п. между конфигурациями — в пределах шума."),
        ("Интервалы широкие:", f" ±{fmt(Fin['halfwidth_end'])} % в конце сезона — это честная неопределённость."),
        ("2025 год:", " итогов Росстата ещё нет, урожайность восстановлена по сбору и посевной."),
        ("Затраты — допущения.", " Эффект оптимизации читать как верхнюю оценку."),
    ]
    text(s, MX + 0.3, 2.2, lw - 0.6, 4.55, [[(a, {"bold": True, "color": INK}), (b, {})] for a, b in lim], size=16, color=INK2, space_after=12)
    # дорожная карта
    rx = MX + lw + 0.35
    rw = SW - MX - rx
    text(s, rx, 1.72, rw, 0.3, "ПЛАН РАЗВИТИЯ", size=12, bold=True, color=GOLD2)
    road = [
        ("Калибровка множителей", "опытные станции, данные хозяйств и банка вместо допущений; уровень района"),
        ("Спутник в реальном времени", "ежедневные NDVI/LAI с маской культур в течение сезона"),
        ("Цены и затраты", "сценарии «цена × урожай», реальные нормативы затрат"),
        ("Удобрения и агротехника", "кривые «доза → прибавка» и рекомендации по срокам"),
        ("Интеграция с данными банка", "кредитные портфели, страхование, график платежей"),
    ]
    rh = 0.93
    for i, (a, b) in enumerate(road):
        y = 2.1 + i * rh
        circle(s, rx, y + 0.1, 0.55, fill=BRAND if i < 4 else GOLD, label=str(i + 1), color="FFFFFF" if i < 4 else BRAND_DK, size=18)
        if i < len(road) - 1:
            line(s, rx + 0.275, y + 0.65, rx + 0.275, y + rh + 0.1, color=BORDER, width=2)
        text(s, rx + 0.8, y + 0.02, rw - 0.8, 0.4, a, size=18, bold=True, color=INK)
        text(s, rx + 0.8, y + 0.42, rw - 0.8, 0.45, b, size=14, color=INK2)
    return s


# ================================================================ 12. Итоги

def s12_end(prs, F, cfg):
    s = base(prs, "Итоги", "Больше, чем модель: полноценное исследование", dark=True)
    L = F["ladder"]
    items = [
        (f"−{fmt(L['gain_end'])}{NBSP}%", "ошибки к прогнозу «как в прошлом году» — на честной проверке по времени 2012–2025"),
        (str(F["n_sources"]) + " → " + fmt(F["model_cols"]), "источников данных → признаков: слои, тесты, воспроизводимая сборка"),
    ]
    if "opt" in F:
        items.append((f"+{fmt(F['opt']['d5']['gain_ha'])}{NBSP}₽/га", "от малых изменений плана посевов: оптимизация с CVaR, проверена на прошлом"))
    else:
        items.append(("5 дат", "прогноза за сезон и рекомендация по структуре посевов"))
    w, gap = 3.85, 0.29
    for i, (big, lab) in enumerate(items):
        x = MX + i * (w + gap)
        card(s, x, 1.75, w, 2.65, fill=BRAND, shade=False)
        text(s, x + 0.3, 1.9, w - 0.6, 1.1, big, size=44, bold=True, color=GOLD, anchor="m")
        text(s, x + 0.3, 3.05, w - 0.6, 1.3, lab, size=15, color="E8F0EA")
    text(s, MX, 4.7, CW, 0.4, "Сайт, код, научный отчёт и тесты — в репозитории; всё пересобирается одной командой", size=16, color="D5E3DA")
    # контакты
    card(s, MX, 5.4, CW, 1.45, fill=BRAND, shade=False)
    def val(k, ph):
        return cfg.get(k) or ph
    text(s, MX + 0.35, 5.5, 6.0, 1.25,
         [[(cfg["author"], {"size": 26, "bold": True, "color": "FFFFFF"})], [(cfg["role"], {"size": 15, "color": "D5E3DA"})]],
         anchor="m", space_after=4)
    text(s, MX + 6.6, 5.5, CW - 6.9, 1.25,
         [[("e-mail: ", {"color": "9DB8A8"}), (val("email", "[заполнить]"), {"bold": True})],
          [("Telegram: ", {"color": "9DB8A8"}), (val("telegram", "[заполнить]"), {"bold": True})],
          [("Репозиторий: ", {"color": "9DB8A8"}), (val("repo_url", "[заполнить]"), {"bold": True})]],
         size=14, color="FFFFFF", anchor="m", space_after=3)
    return s


SLIDES = [s01_title, s02_task, s03_scale, s04_pipeline, s05_method, s06_ladder, s07_dates, s08_drivers, s09_opt,
          s10_site, s11_next, s12_end]
