"""Общие константы, загрузка parquet ЕМИСС и стиль графиков для скриптов анализа."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed" / "emiss"
PROC_ROOT = ROOT / "data" / "processed"
FIG = ROOT / "reports" / "figures"
TAB = ROOT / "reports" / "tables"
FIG.mkdir(parents=True, exist_ok=True)
TAB.mkdir(parents=True, exist_ok=True)

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
SEQ = LinearSegmentedColormap.from_list("seq", ["#f0efec", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
DIV = LinearSegmentedColormap.from_list("div", ["#2a78d6", "#f0efec", "#e34948"])
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 9,
    "axes.titlesize": 10, "axes.titleweight": "bold", "lines.linewidth": 2,
})

CAT_ALL, CAT_SHO = "1", "2"
MAIN = {
    "1010400": "Пшеница озимая", "1010500": "Пшеница яровая", "1010401": "Пшеница (оз.+яр.)",
    "1030100": "Ячмень яровой", "1080202": "Кукуруза на зерно", "3080000": "Подсолнечник", "3100000": "Соя",
    "3060100": "Сахарная свёкла", "4010000": "Картофель", "3130200": "Рапс яровой", "1060000": "Овёс",
    "1020200": "Рожь озимая", "2010000": "Горох", "1120000": "Гречиха",
}
MIN_AREA = 5.0  # тыс. га, средняя посевная 2017–2021


def load(ind: str) -> pd.DataFrame:
    return pd.read_parquet(PROC / f"{ind}.parquet")


def rf_series(df: pd.DataFrame) -> pd.DataFrame:
    """РФ: код 643 до 2022, «без новых субъектов» 643004.АГ с 2023."""
    a = df[(df.okato == "643") & (df.year <= 2022)]
    b = df[(df.okato == "643004.АГ") & (df.year >= 2023)]
    return pd.concat([a, b])


def area_reg() -> pd.Series:
    """Средняя посевная площадь 2017–2021, тыс. га, по (crop_code, okato), все категории."""
    a = load("31328")
    a = a[(a.region_level == "subject") & (a.farm_category_code == CAT_ALL) & a.value.notna()
          & a.year.between(2017, 2021)]
    return a.groupby(["crop_code", "okato"]).value.mean().rename("area_tha")


def savefig(fig, name):
    fig.savefig(FIG / name, dpi=150, bbox_inches="tight")
    plt.close(fig)
