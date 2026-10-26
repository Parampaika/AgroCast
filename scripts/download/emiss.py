"""Выгрузка показателей ЕМИСС (fedstat.ru) со всеми значениями всех фильтров.

Механизм: страница /indicator/<id> содержит JS-объект `filters` (id фильтра -> значения),
`left_columns`, `top_columns`, `filterObjectIds`. Выгрузка — POST на
/indicator/data.do?format=<sdmx|excel> с полями id, lineObjectIds, columnObjectIds,
filterObjectIds и selectedFilterIds=<filterId>_<valueId> для каждого значения.

Запуск: uv run python -I scripts/download/emiss.py 31533 31328 ...
Сохраняет data/raw/emiss/<id>/{page.html, filters.json, data.xml(sdmx), data.xls}.
Уже скачанное не перекачивается (флаг --force).
"""
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "emiss"
BASE = "https://www.fedstat.ru"
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (research data download; rshb_yield_forecast)"


def unescape(s: str) -> str:
    return re.sub(r"\\u([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), s)


def parse_page(html: str) -> dict:
    title = re.search(r"title:\s*'([^']*)'", html)
    unit = re.search(r"unit:\s*'([^']*)'", html)
    start = html.index("filters: {")
    end = html.index("left_columns:", start)
    block = html[start:end]
    filters = {}
    # фильтр: "<fid>: {\n title: '...', ... values: { <vid>: { title: '...', order: N, checked: bool } ...}"
    for fm in re.finditer(r"\n\s*(\d+):\s*\{\s*title:\s*'([^']*)',\s*all:", block):
        fid = fm.group(1)
        nxt = re.search(r"indicator:\s*(true|false)", block[fm.end():])
        seg = block[fm.end(): fm.end() + nxt.end()] if nxt else block[fm.end():]
        vals = {}
        for vm in re.finditer(r"(\d+):\s*\{\s*title:\s*'([^']*)',\s*order:\s*(-?\d+),\s*checked:\s*(true|false)", seg):
            vals[vm.group(1)] = {"title": unescape(vm.group(2)), "order": int(vm.group(3)),
                                 "checked": vm.group(4) == "true"}
        filters[fid] = {"title": unescape(fm.group(2)), "values": vals}

    def ids(name):
        m = re.search(name + r":\s*\[([^\]]*)\]", html[end:])
        return [x.strip() for x in m.group(1).split(",") if x.strip()] if m else []

    return {"title": unescape(title.group(1)) if title else "", "unit": unescape(unit.group(1)) if unit else "",
            "filters": filters, "left_columns": ids("left_columns"), "top_columns": ids("top_columns"),
            "groups": ids("groups"), "filterObjectIds": ids("filterObjectIds")}


def payload(ind_id: str, meta: dict, only: dict | None = None) -> list:
    data = [("id", ind_id)]
    for x in meta["left_columns"]:
        data.append(("lineObjectIds", x))
    for x in meta["top_columns"]:
        data.append(("columnObjectIds", x))
    for x in meta["groups"]:
        data.append(("groupObjectIds", x))
    for x in meta["filterObjectIds"]:
        data.append(("filterObjectIds", x))
    for fid, f in meta["filters"].items():
        for vid in (only[fid] if only and fid in only else f["values"]):
            data.append(("selectedFilterIds", f"{fid}_{vid}"))
    return data


def fetch(ind_id: str, force=False, formats=("sdmx", "excel")):
    d = OUT / ind_id
    d.mkdir(parents=True, exist_ok=True)
    page = d / "page.html"
    if force or not page.exists():
        r = S.get(f"{BASE}/indicator/{ind_id}", timeout=120)
        r.raise_for_status()
        page.write_text(r.text, encoding="utf-8")
    meta = parse_page(page.read_text(encoding="utf-8"))
    (d / "filters.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    nvals = {f["title"]: len(f["values"]) for f in meta["filters"].values()}
    print(ind_id, meta["title"], "|", nvals, flush=True)
    for fmt in formats:
        fn = d / ("data.xml" if fmt == "sdmx" else "data.xls")
        if (fn.exists() and fn.stat().st_size > 2_000 and not force) or (d / f"by_year_{fmt}.done").exists():
            continue
        if download(ind_id, meta, fmt, fn):
            continue
        # полная выгрузка не прошла -> по годам (фильтр «Год» имеет id 3)
        if "3" in meta["filters"]:
            ok = True
            for y in meta["filters"]["3"]["values"]:
                yfn = d / f"data_{y}.{'xml' if fmt == 'sdmx' else 'xls'}"
                if yfn.exists() and yfn.stat().st_size > 2_000:
                    continue
                ok &= download(ind_id, meta, fmt, yfn, only={"3": [y]})
            if ok:
                (d / f"by_year_{fmt}.done").write_text("ok")


def download(ind_id, meta, fmt, fn, only=None) -> bool:
    d = fn.parent
    for attempt in range(3):
        try:
            # токен одноразовый: каждый раз берём свежую страницу в той же сессии (cookie)
            pg = S.get(f"{BASE}/indicator/{ind_id}", timeout=120)
            if pg.status_code in (403, 429, 503):  # сайт ограничивает частые выгрузки — ждём
                print(f"  {fn.name}: page {pg.status_code}, sleep 10 min", flush=True)
                time.sleep(600)
                continue
            html = pg.text
            tok = re.search(r'name="token" value="([^"]+)"', html).group(1)
            data = [("title", meta["title"]), ("struts.token.name", "token"), ("token", tok)]
            data += payload(ind_id, meta, only)
            r = S.post(f"{BASE}/indicator/downloadData.do?format={fmt}", data=data, timeout=1800)
            ctype = r.headers.get("content-type", "")
            if r.ok and "html" not in ctype:
                fn.write_bytes(r.content)
                print(f"  {fn.name}: {len(r.content)/1e6:.2f} MB", flush=True)
                time.sleep(10)
                return True
            print(f"  {fn.name}: bad response {r.status_code} {ctype} {len(r.content)}", flush=True)
            (d / f"bad_response_{fmt}.html").write_bytes(r.content)
        except (requests.RequestException, AttributeError) as e:
            print(f"  {fn.name}: {e!r}"[:300], flush=True)
        time.sleep(60 * (attempt + 1))
    return False


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    fmts = ("sdmx",) if "--sdmx-only" in sys.argv else ("sdmx", "excel")
    for i in args:
        try:
            fetch(i, force, fmts)
        except Exception as e:  # продолжаем со следующим показателем
            print(i, "FAILED", repr(e), flush=True)
