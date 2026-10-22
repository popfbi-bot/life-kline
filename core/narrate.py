"""一句自动生成的回顾。

必须全部来自实算。指标不适用时换说法，绝不输出「最长连阳 0 天」这种废话。
语气克制：描述过去发生了什么，不评价、不鼓励、不建议。
"""

from __future__ import annotations

from datetime import date as Date

from .metrics import Stats, compute_stats
from .model import Day

CN_NUM = "零一二三四五六七八九十"


def _cn_day(d: Date) -> str:
    return f"{d.month} 月 {d.day} 日"


def _cn_month(d: Date) -> str:
    return f"{d.month} 月"


def _pct(value: float) -> str:
    return f"{round(value * 100)}%"


def build(data: list[Day], period: str = "year") -> str:
    """生成一句回顾。period 只影响「今年/本月」这类措辞。"""
    stats = compute_stats(data)
    return render_narrative(stats, period=period)


def render_narrative(stats: Stats, period: str = "year") -> str:
    if stats.recorded_days == 0:
        return "这段时间没有记录，图上什么都没有。停牌也是一种状态。"

    parts: list[str] = []
    scope = {"year": "这一年", "month": "这个月", "week": "这一周", "day": "这一天"}.get(period, "这段时间")
    span = stats.total_days
    parts.append(f"{scope}你记录了 {stats.recorded_days} 天（共 {span} 天）")

    # 连阳：只有真的连续 2 天以上才值得说。区间起点用 first_day，不是 start。
    if stats.longest_up and stats.longest_up.length >= 2:
        seg = stats.longest_up
        parts.append(f"最长连阳 {seg.length} 天（{_cn_day(seg.first_day)}–{_cn_day(seg.end)}）")
    elif stats.longest_down and stats.longest_down.length >= 2:
        seg = stats.longest_down
        parts.append(f"没有连阳，最长连阴 {seg.length} 天（{_cn_day(seg.first_day)}–{_cn_day(seg.end)}）")

    # 回撤：太小的回撤不值得当成「最大」，说成「几乎没回撤」。
    if stats.max_drawdown >= 0.01:
        dd_month = _cn_month(stats.max_drawdown_date) if stats.max_drawdown_date else ""
        parts.append(f"最大回撤 {_pct(stats.max_drawdown)}（{dd_month}那波）")
    else:
        parts.append("最大回撤不到 1%，收盘价基本没跌破过前高")

    # 停牌率：0 天就别说「停牌 0 天」。
    if stats.suspended_days == 0:
        parts.append("一天没停牌")
    elif stats.suspension_rate >= 0.5:
        parts.append(f"停牌 {stats.suspended_days} 天，比记录的日子还多")
    else:
        parts.append(f"停牌 {stats.suspended_days} 天")

    return "，".join(parts) + "。"


def describe_streak(seg, kind: str) -> str:
    if seg is None or seg.length < 2:
        return f"没有连续两天的{'连阳' if kind == 'up' else '连阴'}"
    return f"最长连{'阳' if kind == 'up' else '阴'} {seg.length} 天（{_cn_day(seg.first_day)}–{_cn_day(seg.end)}）"
