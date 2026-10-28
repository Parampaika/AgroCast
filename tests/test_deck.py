"""Презентация: форматирование чисел и сценарий на синтетических данных (без данных проекта)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deck import facts, script  # noqa: E402


def test_fmt_russian_numbers():
    assert facts.fmt(1301.3) == "1 301"
    assert facts.fmt(11.256, 1) == "11,3"
    assert facts.fmt(-30.1) == "−30"
    assert facts.fmt(0.2, 0, sign=True) == "0"        # нулевой знак не пишем
    assert facts.fmt(12.4, 0, sign=True) == "+12"
    assert facts.fmt(float("nan")) == "—"


def test_plural():
    p = lambda n: facts.plural(n, "субъект", "субъекта", "субъектов")  # noqa: E731
    assert [p(n) for n in (1, 2, 5, 11, 21, 62, 112)] == ["субъект", "субъекта", "субъектов", "субъектов", "субъект", "субъекта", "субъектов"]


def _fake():
    L = {"mape": [20.0, 17.6, 15.0, 15.1, 14.1], "gain": [0, 12, 25.4, 25.1, 30.1], "gain_end": 30.1,
         "by_date": {"all": [19.5] * 5, "late": [19.0] * 5}}
    return {"ladder": L, "final": {"cov_min": 0.83, "cov_max": 0.93, "halfwidth_end": 24.4, "halfwidth_may": 27.6},
            "cfg": {"total": 4069, "optuna_trials": 10244}, "n_sources": 17, "raw_gb": 11.3, "rows_mln": 21.2,
            "model_cols": 683, "n_tests": 57, "built": "x", "stamps": {}, "missing": ["shap: нет файла"]}


def test_script_without_optional_blocks():
    sl = script.build(_fake(), {"author": "Фамилия И.О."})
    assert len(sl) == 12 and all(s["text"] for s in sl)
    assert "17 источников" in sl[2]["text"] and "4 069" in sl[2]["text"]
    assert "ждёт данных" in sl[7]["text"] and "ждёт данных" in sl[8]["text"]
    md = script.render(_fake(), {"author": "Фамилия И.О."}, sl)
    assert "Не хватает данных" in md and "Возможные вопросы жюри" in md
