"""CSV 读写。全项目唯一碰磁盘的模块（render 只写用户指定的 --out）。

不做聚合、不算指标——这样聚合和指标才能被纯函数测试。
"""

from __future__ import annotations

import csv
import os
from datetime import date as Date
from pathlib import Path

from .model import CSV_COLUMNS, DataError, Day, build_day, day_to_row

TEMPLATE_ROWS = (
    "2026-10-18,6,8,4,7,12,下午把那个 bug 修了,work",
    "2026-10-19,7,7,5,5,8,,tired",
    "2026-10-20,,,,,,",
    "2026-10-21,5,9,3,8,15,早上很糟下午反转,breakthrough",
)

DEFAULT_PATH = Path("~/life-kline.csv")


def default_path() -> Path:
    return DEFAULT_PATH.expanduser()


def _split_row(row: list[str], line: int) -> Day:
    cells = list(row) + [""] * (len(CSV_COLUMNS) - len(row))
    raw_date, open_, high, low, close, volume, note, tags = cells[: len(CSV_COLUMNS)]
    return build_day(
        raw_date,
        {"open": open_, "high": high, "low": low, "close": close},
        volume=volume,
        note=note,
        tags=tags,
        line=line,
    )


def parse_csv_text(text: str) -> list[Day]:
    """解析 CSV 文本。空行跳过；表头可选。"""
    rows = list(csv.reader(text.splitlines()))
    days: list[Day] = []
    seen: dict[Date, int] = {}
    header_skipped = False

    for idx, row in enumerate(rows, start=1):
        if not row or all(not c.strip() for c in row):
            continue
        if not header_skipped and row[0].strip().lower() == "date":
            header_skipped = True
            continue

        day = _split_row(row, idx)
        if day.date in seen:
            first = seen[day.date]
            raise DataError(idx, day.date.isoformat(), "date", f"与第 {first} 行重复")
        seen[day.date] = idx
        days.append(day)

    days.sort(key=lambda d: d.date)
    return days


def load(path: str | os.PathLike[str]) -> list[Day]:
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"找不到数据文件：{p}（先跑 `life-kline init`）")
    return parse_csv_text(p.read_text(encoding="utf-8"))


def write_days(path: str | os.PathLike[str], days: list[Day]) -> None:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        for day in sorted(days, key=lambda d: d.date):
            writer.writerow(day_to_row(day))


def init_file(path: str | os.PathLike[str], rows: tuple[str, ...] = TEMPLATE_ROWS) -> tuple[Path, bool]:
    """初始化 CSV。已存在则不覆盖，返回 (路径, 是否新建)。"""
    p = Path(path).expanduser()
    if p.exists():
        return p, False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(",".join(CSV_COLUMNS) + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return p, True


def append_day(path: str | os.PathLike[str], day: Day) -> None:
    """追加/替换一天。同日期已存在则替换（由调用方决定是否允许）。"""
    p = Path(path).expanduser()
    existing = [] if not p.exists() else load(p)
    replaced = False
    for i, old in enumerate(existing):
        if old.date == day.date:
            existing[i] = day
            replaced = True
            break
    if not replaced:
        existing.append(day)
    write_days(p, existing)


def find_day(path: str | os.PathLike[str], target: Date) -> Day | None:
    for day in load(path):
        if day.date == target:
            return day
    return None


def write_text(path: str | os.PathLike[str], text: str) -> None:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
