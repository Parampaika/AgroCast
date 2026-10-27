"""Единый стиль графиков отчёта: палитра, шрифты, подписи признаков."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

# Категориальная палитра (порядок фиксирован, цвет закреплён за сущностью, а не за рангом)
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
CAT = [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED]
INK, INK2, MUTED, GRID, NEUTRAL, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df", "#b9b8b2", "#ffffff"
# Последовательная шкала (синяя) и ординальные ступени (не светлее 250)
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#1c5cab", "#104281", "#0d366b"]
ORD5 = ["#b9b8b2", "#86b6ef", "#5598e7", "#256abf", "#104281"]  # лесенка: серый «наивный» → тёмно-синий
CMAP_SEQ = LinearSegmentedColormap.from_list("seq", ["#f4f8fd"] + SEQ)
CMAP_DIV = LinearSegmentedColormap.from_list(
    "div", ["#a52e2e", "#e34948", "#f2a9a3", "#f0efec", "#9ec5f4", "#2a78d6", "#104281"])

CROP_ORDER = ["winter_wheat", "spring_wheat", "barley", "sunflower", "maize", "soy", "sugar_beet"]
CROP_NAME = {"winter_wheat": "Пшеница озимая", "spring_wheat": "Пшеница яровая", "barley": "Ячмень яровой",
             "sunflower": "Подсолнечник", "maize": "Кукуруза на зерно", "soy": "Соя",
             "sugar_beet": "Сахарная свёкла"}
CROP_SHORT = {"winter_wheat": "Пшеница оз.", "spring_wheat": "Пшеница яр.", "barley": "Ячмень",
              "sunflower": "Подсолнечник", "maize": "Кукуруза", "soy": "Соя", "sugar_beet": "Свёкла"}
NAME_KEY = {v: k for k, v in CROP_NAME.items()}
CROP_COLOR = dict(zip(CROP_ORDER, CAT))
DATE_ORDER = ["05-01", "06-01", "07-01", "08-01", "end"]
DATE_LABEL = {"05-01": "1 мая", "06-01": "1 июня", "07-01": "1 июля", "08-01": "1 авг.", "end": "конец сезона"}

MONTH = {"p09": "сен.¹", "p10": "окт.¹", "p11": "нояб.¹", "p12": "дек.¹", "01": "янв.", "02": "февр.",
         "03": "март", "04": "апр.", "05": "май", "06": "июнь", "07": "июль", "08": "авг.", "09": "сент.",
         "10": "окт."}
VAR = {"tmean": "T сред.", "tmax": "T макс.", "tmin": "T мин.", "prec": "осадки", "et0": "ET0",
       "cwb": "P − ET0", "rad": "радиация", "vpd": "дефицит влажности", "sm7_28": "влага 7–28 см",
       "sm28_100": "влага 28–100 см", "hot30": "дни > 30 °C", "hot35": "дни > 35 °C", "gdd5": "сумма T > 5",
       "gdd10": "сумма T > 10", "frost0": "заморозки", "snow_depth": "снег", "tsoil_min": "T почвы мин.",
       "dry_days": "сухие дни", "htc": "ГТК", "dry_spell": "засушливая серия", "ndvi": "NDVI",
       "lai": "LAI", "fpar": "FPAR", "lst_day": "LST днём", "lst_night": "LST ночью",
       "lst_diff": "LST день−ночь", "gpp": "GPP"}


def feature_label(col: str) -> str:
    """Человеческая подпись признака из `src/model/data.py`."""
    special = {"r1": "отклонение прошлого года", "r2": "отклонение 2 года назад", "cat:okato": "регион",
               "cat:fo": "федеральный округ", "e:wrb": "тип почвы WRB", "w:prec_p09_03": "осадки сен.–март",
               "w:tsoil_min_win": "T почвы мин., зима", "w:cold20_win": "дни < −20 °C, зима",
               "w:snow_win": "снег, зима", "w:thaw_win": "оттепели, зима", "n:ndvi_integral": "NDVI, интеграл",
               "n:ndvi_max": "NDVI, максимум"}
    if col in special:
        return special[col]
    blk, _, name = col.partition(":")
    if blk == "w" and name.startswith("win_"):
        return "окно культуры: " + VAR.get(name[4:], name[4:])
    base, _, tag = name.rpartition("_")
    if tag in MONTH and base:
        return f"{VAR.get(base, base)}, {MONTH[tag]}"
    if tag in ("pk", "cum"):
        return f"{VAR.get(base, base)}, {'пик' if tag == 'pk' else 'сумма'}"
    return VAR.get(name, name)


def setup() -> None:
    plt.rcParams.update({
        "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 9, "axes.titlesize": 10,
        "axes.titleweight": "semibold", "axes.titlelocation": "left", "axes.labelsize": 9,
        "axes.labelcolor": INK2, "axes.edgecolor": NEUTRAL, "axes.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "axes.axisbelow": True,
        "grid.color": GRID, "grid.linewidth": 0.6, "xtick.color": INK2, "ytick.color": INK2,
        "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8, "legend.frameon": False,
        "text.color": INK, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "savefig.dpi": 220, "savefig.bbox": "tight", "savefig.pad_inches": 0.08,
        "lines.linewidth": 2, "lines.markersize": 5, "axes.prop_cycle": matplotlib.cycler(color=CAT),
    })


def annotate_heat(ax, M, fmt="{:.0f}", thresh=None, fontsize=7.5) -> None:
    """Подписи значений в ячейках теплокарты: тёмный текст на светлом фоне и наоборот."""
    import numpy as np
    vals = np.asarray(M, dtype=float)
    hi = np.nanmax(np.abs(vals)) if thresh is None else thresh
    for i in range(vals.shape[0]):
        for j in range(vals.shape[1]):
            v = vals[i, j]
            if np.isfinite(v):
                ax.text(j, i, fmt.format(v), ha="center", va="center", fontsize=fontsize,
                        color="white" if abs(v) > 0.62 * hi else INK)
