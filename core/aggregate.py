"""日 → 周/月/年 聚合。纯函数，不碰磁盘、不算指标。

三条硬规则（照抄真实 K 线，不自己发明）：
1. 开盘取该周期「第一个有记录日」的 open，不是周一的 open。
2. 收盘取「最后一个有记录日」的 close。
3. 整周期全停牌 → 不产生 K 线（绝不生成 0 值或空柱子）。

停牌日（Day.suspended 为真）不参与开高低收，也不参与成交量求和。
"""

from __future__ import annotations

from datetime import date as Date

from .model import Candle, Day

PERIODS = ("day", "week", "month", "year")


def _group_key(day: Date, period: str) -> tuple:
    if period == "day":
        return (day,)
    if period == "week":
        iso = day.isocalendar()
        return (iso[0], iso[1])
    if period == "month":
        return (day.year, day.month)
    if period == "year":
        return (day.year,)
    raise ValueError(f"未知周期：{period}（可选 {'/'.join(PERIODS)}）")


def _group_label(key: tuple, period: str) -> str:
    if period == "day":
        return key[0].isoformat()
    if period == "week":
        return f"{key[0]}-W{key[1]:02d}"
    if period == "month":
        return f"{key[0]}-{key[1]:02d}"
    return f"{key[0]}"


def group_days(days: list[Day], period: str) -> list[tuple[tuple, list[Day]]]:
    """按周期分组，保留输入中的停牌日与记录日。结果按时间升序。"""
    buckets: dict[tuple, list[Day]] = {}
    for day in days:
        buckets.setdefault(_group_key(day.date, period), []).append(day)
    for value in buckets.values():
        value.sort(key=lambda d: d.date)
    return sorted(buckets.items(), key=lambda kv: kv[0])


def aggregate(days: list[Day], period: str) -> list[Candle]:
    """把日记录聚合成 Candle 列表。全停牌的周期不产生 Candle。"""
    if period not in PERIODS:
        raise ValueError(f"未知周期：{period}（可选 {'/'.join(PERIODS)}）")

    candles: list[Candle] = []
    for key, group in group_days(days, period):
        recorded = [d for d in group if not d.suspended]
        if not recorded:
            continue  # 停牌周期：留白，不生成 K 线

        volumes = [d.volume for d in recorded if d.volume is not None]
        notes = [d.note for d in recorded if d.note]
        tags: list[str] = []
        for d in recorded:
            for t in d.tags:
                if t not in tags:
                    tags.append(t)

        candles.append(
            Candle(
                key=_group_label(key, period),
                start=group[0].date,
                end=group[-1].date,
                open=float(recorded[0].open),          # 第一个「有记录日」的开
                high=float(max(d.high for d in recorded)),
                low=float(min(d.low for d in recorded)),
                close=float(recorded[-1].close),        # 最后一个「有记录日」的收
                volume=sum(volumes) if volumes else None,
                recorded_days=len(recorded),
                note=notes[-1] if notes else "",
                tags=tuple(tags),
            )
        )
    return candles


def recorded_only(days: list[Day]) -> list[Day]:
    """去掉停牌日。收益率等指标只在有记录的日子上连起来算。"""
    return [d for d in days if not d.suspended]
