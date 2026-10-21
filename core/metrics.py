"""7 个指标。纯函数：不碰文件、不碰网络、不看未来。

「不看未来」是硬约束：所有函数只吃一个按日期升序的序列，
输出第 i 项只依赖前 i 项，末尾多几天记录不会改变前面任何一项的结果。
函数签名里没有「未来日期」这种参数。

停牌日（Day.suspended）不参与收益率、振幅、波动率、连阳连阴的计算，
只参与「停牌天数 / 停牌率」的计数。跨停牌时，上一根有记录的收盘价就是基准。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date, timedelta

from .model import Day, Candle


@dataclass(frozen=True)
class Segment:
    """一段连续的阳线/阴线。

    start / end 都是「真正属于这一段的那根 K 线」的日期：start 是第一根，
    end 是最后一根，与 length 自洽（跨度 ≤ length，中间只有停牌日）。
    """

    start: Date
    end: Date
    length: int


@dataclass(frozen=True)
class Stats:
    daily_returns: list[float]
    amplitudes: list[float]
    volatility: float | None
    max_drawdown: float
    max_drawdown_date: Date | None
    max_drawdown_peak_date: Date | None
    longest_up: Segment | None
    longest_down: Segment | None
    recorded_days: int
    suspended_days: int
    total_days: int
    first_recorded: Date | None
    last_recorded: Date | None

    @property
    def suspension_rate(self) -> float:
        return self.suspended_days / self.total_days if self.total_days else 0.0


def daily_returns(days: list[Day]) -> list[float]:
    """(close_t - close_{t-1}) / close_{t-1}，与「上一个有记录日」比。"""
    recorded = [d for d in days if not d.suspended]
    out = []
    for prev, cur in zip(recorded, recorded[1:]):
        out.append((cur.close - prev.close) / prev.close)
    return out


def amplitudes(days: list[Day]) -> list[float]:
    """(high - low) / prev_close，prev_close 是上一个有记录日的收盘。"""
    recorded = [d for d in days if not d.suspended]
    out = []
    for prev, cur in zip(recorded, recorded[1:]):
        out.append((cur.high - cur.low) / prev.close)
    return out


def volatility(returns: list[float]) -> float | None:
    """日收益率的样本标准差（n-1 分母）。少于 2 个样本时无从谈起，返回 None。"""
    n = len(returns)
    if n < 2:
        return None
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    return var ** 0.5


def max_drawdown(days: list[Day]) -> tuple[float, Date | None, Date | None]:
    """max(1 - close_t / max(close_0..close_t))。

    返回 (回撤比例, 回撤最低点日期, 之前的最高点日期)。只看过去，不看未来。
    """
    recorded = [d for d in days if not d.suspended]
    if not recorded:
        return 0.0, None, None

    peak_close = recorded[0].close
    peak_date = recorded[0].date
    worst = 0.0
    worst_date: Date | None = None
    worst_peak: Date | None = None

    for day in recorded:
        if day.close > peak_close:
            peak_close = day.close
            peak_date = day.date
        dd = 1 - day.close / peak_close
        if dd > worst:
            worst = dd
            worst_date = day.date
            worst_peak = peak_date
    return worst, worst_date, worst_peak


def streaks(days: list[Day]) -> tuple[Segment | None, Segment | None]:
    """最长的连阳 / 连阴（按有记录日顺序，跨停牌继续）。

    连阳段中途遇到平盘（close == prev_close）就中断：既不算阳也不算阴。
    """
    recorded = [d for d in days if not d.suspended]
    best_up: Segment | None = None
    best_down: Segment | None = None

    run_dir = 0
    run_start: Date | None = None
    run_len = 0
    run_last: Date | None = None

    def close_run() -> None:
        nonlocal best_up, best_down
        if run_dir > 0 and (best_up is None or run_len > best_up.length):
            best_up = Segment(run_start, run_last, run_len)
        elif run_dir < 0 and (best_down is None or run_len > best_down.length):
            best_down = Segment(run_start, run_last, run_len)

    for prev, cur in zip(recorded, recorded[1:]):
        direction = 1 if cur.close > prev.close else (-1 if cur.close < prev.close else 0)
        if direction == 0:
            close_run()
            run_dir, run_start, run_len, run_last = 0, None, 0, None
            continue
        if direction != run_dir:
            close_run()
            run_dir = direction
            run_start = cur.date  # 第一根阳/阴线自己，不是它参照的前一日
            run_len = 1
        else:
            run_len += 1
        run_last = cur.date
    close_run()

    return best_up, best_down


def _span(days: list[Day]) -> int:
    if not days:
        return 0
    first, last = days[0].date, days[-1].date
    return (last - first).days + 1


def compute_stats(days: list[Day]) -> Stats:
    """一次算齐 7 个指标。days 必须按日期升序、且不含未来数据。"""
    ordered = sorted(days, key=lambda d: d.date)
    recorded = [d for d in ordered if not d.suspended]

    # 停牌天数只统计「有记录区间内」没填的日子，区间外的空白不替用户记账。
    total = _span(ordered)
    dd, dd_date, dd_peak = max_drawdown(ordered)
    up, down = streaks(ordered)

    return Stats(
        daily_returns=daily_returns(ordered),
        amplitudes=amplitudes(ordered),
        volatility=volatility(daily_returns(ordered)),
        max_drawdown=dd,
        max_drawdown_date=dd_date,
        max_drawdown_peak_date=dd_peak,
        longest_up=up,
        longest_down=down,
        recorded_days=len(recorded),
        suspended_days=total - len(recorded),
        total_days=total,
        first_recorded=recorded[0].date if recorded else None,
        last_recorded=recorded[-1].date if recorded else None,
    )


def suspension_gaps(days: list[Day]) -> list[Date]:
    """列出区间内没有记录的日子（停牌）。

    区间与 compute_stats 用同一个口径：文件里最早一行到最后一行。
    末尾的停牌日也算 —— 否则写了「当天停牌」却被报成「一天没停牌」。
    """
    if not days:
        return []
    recorded = {d.date for d in days if not d.suspended}
    ordered = sorted(d.date for d in days)
    first, last = ordered[0], ordered[-1]
    out = []
    cursor = first
    while cursor <= last:
        if cursor not in recorded:
            out.append(cursor)
        cursor += timedelta(days=1)
    return out


def slice_days(days: list[Day], start: Date | None = None, end: Date | None = None) -> list[Day]:
    return [d for d in days if (start is None or d.date >= start) and (end is None or d.date <= end)]


def candle_count(candles: list[Candle]) -> int:
    return len(candles)
