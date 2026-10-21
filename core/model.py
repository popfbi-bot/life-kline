"""Day / Candle 数据模型与 0–10 校验。

这里只做「数据长得对不对」的判断，不读文件、不算指标。
错误信息必须能定位到：第几行、哪天、哪个字段。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date as Date

ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

FIELDS = ("open", "high", "low", "close")
CSV_COLUMNS = ("date", "open", "high", "low", "close", "volume", "note", "tags")


class DataError(Exception):
    """带定位信息的校验错误：行号 + 日期 + 字段名。"""

    def __init__(self, line: int | None, date: str, field: str, reason: str):
        self.line = line
        self.date = date
        self.field = field
        self.reason = reason
        super().__init__(self.render())

    def render(self) -> str:
        where = f"第 {self.line} 行" if self.line is not None else "CSV"
        day = self.date or "（无日期）"
        return f"{where}：{day} 的字段 `{self.field}` {self.reason}"


@dataclass(frozen=True)
class Day:
    """一天的记录。四个价格全为 None 表示停牌（合法，不是错误）。"""

    date: Date
    open: int | None = None
    high: int | None = None
    low: int | None = None
    close: int | None = None
    volume: int | None = None
    note: str = ""
    tags: tuple[str, ...] = ()

    @property
    def suspended(self) -> bool:
        return self.open is None and self.high is None and self.low is None and self.close is None


@dataclass(frozen=True)
class Candle:
    """一根 K 线。period 为 day/week/month/year 时 key 分别是日期/周标识/年月/年。"""

    key: str
    start: Date
    end: Date
    open: float
    high: float
    low: float
    close: float
    volume: int | None = None
    recorded_days: int = 1
    note: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


def parse_iso_date(text: str, line: int | None, field_name: str = "date") -> Date:
    if not ISO_RE.match(text or ""):
        raise DataError(line, text or "", field_name, "必须是 ISO 格式 YYYY-MM-DD")
    try:
        return Date.fromisoformat(text)
    except ValueError:
        raise DataError(line, text, field_name, "不是真实存在的日期") from None


def parse_score(raw: str, name: str, line: int | None, day: str) -> int | None:
    """0–10 的整数；空字符串返回 None（由调用方判断是不是停牌）。"""
    text = (raw or "").strip()
    if text == "":
        return None
    try:
        value = int(text)
    except ValueError:
        raise DataError(line, day, name, f"必须是 0–10 的整数，实际是 `{text}`") from None
    if not 0 <= value <= 10:
        raise DataError(line, day, name, f"必须在 0–10 之间，实际是 {value}")
    return value


def parse_volume(raw: str, line: int | None, day: str) -> int | None:
    text = (raw or "").strip()
    if text == "":
        return None
    try:
        value = int(text)
    except ValueError:
        raise DataError(line, day, "volume", f"必须是非负整数，实际是 `{text}`") from None
    if value < 0:
        raise DataError(line, day, "volume", f"不能为负数，实际是 {value}")
    return value


def validate_ohlc(open_, high, low, close, line: int | None, day: str) -> None:
    """校验逻辑：低点不能高于开收盘，高点不能低于开收盘。"""
    if low is not None and open_ is not None and low > open_:
        raise DataError(line, day, "low", f"({low}) 不能大于 open ({open_})")
    if low is not None and close is not None and low > close:
        raise DataError(line, day, "low", f"({low}) 不能大于 close ({close})")
    if high is not None and open_ is not None and high < open_:
        raise DataError(line, day, "high", f"({high}) 不能小于 open ({open_})")
    if high is not None and close is not None and high < close:
        raise DataError(line, day, "high", f"({high}) 不能小于 close ({close})")


def build_day(
    raw_date: str,
    scores: dict[str, str],
    volume: str = "",
    note: str = "",
    tags: str = "",
    line: int | None = None,
) -> Day:
    """把一行原始文本变成 Day；任何不合规都抛带定位的 DataError。"""
    raw_date = (raw_date or "").strip()
    parsed = parse_iso_date(raw_date, line)
    day = raw_date

    values = {name: parse_score(scores.get(name, ""), name, line, day) for name in FIELDS}
    filled = [name for name, v in values.items() if v is not None]

    # 整行全空 = 停牌，合法。
    if not filled:
        if (volume or "").strip() not in ("",):
            raise DataError(line, day, "volume", "停牌日不应有成交量")
        return Day(date=parsed, note=note.strip(), tags=_split_tags(tags))

    # 只填了一部分：拒绝，不猜。
    missing = [name for name in FIELDS if values[name] is None]
    if missing:
        raise DataError(line, day, missing[0], "停牌日以外的记录必须四个分数都填（不猜缺失值）")

    validate_ohlc(values["open"], values["high"], values["low"], values["close"], line, day)

    return Day(
        date=parsed,
        open=values["open"],
        high=values["high"],
        low=values["low"],
        close=values["close"],
        volume=parse_volume(volume, line, day),
        note=note.strip(),
        tags=_split_tags(tags),
    )


def _split_tags(tags: str) -> tuple[str, ...]:
    return tuple(t.strip() for t in (tags or "").split(";") if t.strip())


def day_to_row(day: Day) -> list[str]:
    def num(v):
        return "" if v is None else str(v)

    return [
        day.date.isoformat(),
        num(day.open),
        num(day.high),
        num(day.low),
        num(day.close),
        num(day.volume),
        day.note,
        ";".join(day.tags),
    ]
