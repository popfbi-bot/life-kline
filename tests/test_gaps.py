"""验收判据 2 与 3：停牌不是插值，周开盘取「第一个有记录日」。

这些都是本项目三条红线里最关键的两条（不预测、不插值）的直接断言。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.aggregate import aggregate  # noqa: E402
from core.metrics import daily_returns, suspension_gaps  # noqa: E402
from core.store import parse_csv_text  # noqa: E402

HEADER = "date,open,high,low,close,volume,note,tags\n"


def days_of(rows: str):
    return parse_csv_text(HEADER + rows)


class TestMissingDayIsGapNotInterpolated(unittest.TestCase):
    def test_missing_day_produces_no_candle(self):
        """中间某天停牌：该日不产生 Candle。"""
        days = days_of(
            "2026-10-19,4,6,3,5,1,\n"
            "2026-10-20,,,,,,,\n"
            "2026-10-21,6,8,5,7,1,\n"
        )
        candles = aggregate(days, "day")
        self.assertEqual([c.key for c in candles], ["2026-10-19", "2026-10-21"])
        self.assertNotIn("2026-10-20", [c.key for c in candles])

    def test_returns_skip_over_the_gap(self):
        """有停牌日时，收益率是跨过停牌日跟「上一个有记录日」比的。

        close：10-19=5，10-20 停牌（不能填成 5 或 0），10-21=7
        正确：(7-5)/5 = 0.4
        若错误地对 0 算：除以 0 → 崩；若错误地拿 10-20 的插值 5 算 → 同样是 0.4，
        所以这里再加一条：加一个真正的洞，看收益率个数。
        """
        days = days_of(
            "2026-10-19,4,6,3,5,1,\n"
            "2026-10-20,,,,,,,\n"
            "2026-10-21,6,8,5,7,1,\n"
        )
        returns = daily_returns(days)
        self.assertEqual(len(returns), 1)  # 3 天里只有 2 天有记录 -> 1 个收益率
        self.assertAlmostEqual(returns[0], 0.4, places=12)

    def test_interpolation_would_have_changed_the_answer(self):
        """反证：如果真插值（把 10-20 填成 5），收益率会有 2 个，且图上多一根 K 线。"""
        with_gap = days_of(
            "2026-10-19,4,6,3,5,1,\n"
            "2026-10-20,,,,,,,\n"
            "2026-10-21,6,8,5,7,1,\n"
        )
        interpolated = days_of(
            "2026-10-19,4,6,3,5,1,\n"
            "2026-10-20,5,5,5,5,0,\n"
            "2026-10-21,6,8,5,7,1,\n"
        )
        self.assertEqual(len(daily_returns(with_gap)), 1)
        self.assertEqual(len(daily_returns(interpolated)), 2)
        self.assertEqual(len(aggregate(with_gap, "day")), 2)
        self.assertEqual(len(aggregate(interpolated, "day")), 3)

    def test_long_gap_keeps_single_return(self):
        days = days_of(
            "2026-10-19,4,6,3,5,1,\n"
            "2026-11-30,5,7,4,6,1,\n"
        )
        gap = suspension_gaps(days)
        self.assertEqual(len(gap), 41)  # 10-20 .. 11-29
        self.assertEqual(len(daily_returns(days)), 1)
        self.assertAlmostEqual(daily_returns(days)[0], (6 - 5) / 5, places=12)


class TestWeekOpenUsesFirstRecordedDay(unittest.TestCase):
    def test_monday_suspended_uses_tuesday_open(self):
        """周一停牌、周二有记录 → 周开盘必须等于周二的 open，不是周一（周一没有 open）。"""
        days = days_of(
            # 2026-10-19 是周一
            "2026-10-19,,,,,,,\n"
            "2026-10-20,3,7,2,6,4,\n"
            "2026-10-21,6,8,5,7,2,\n"
        )
        weeks = aggregate(days, "week")
        self.assertEqual(len(weeks), 1)
        self.assertEqual(weeks[0].open, 3)   # 周二的 open=3
        self.assertEqual(weeks[0].close, 7)  # 周三的 close=7（最后一个有记录日）
        self.assertEqual(weeks[0].high, 8)
        self.assertEqual(weeks[0].low, 2)
        self.assertEqual(weeks[0].volume, 6)

    def test_monday_suspended_is_not_zero_filled(self):
        """周一停牌时，绝不能拿 0 当周开盘。"""
        days = days_of(
            "2026-10-19,,,,,,,\n"
            "2026-10-22,9,10,8,9,1,\n"
        )
        self.assertNotEqual(aggregate(days, "week")[0].open, 0)
        self.assertEqual(aggregate(days, "week")[0].open, 9)

    def test_fully_suspended_week_has_no_candle(self):
        """整周全停牌 → 那周没有 Candle，不留 0 值柱子。"""
        days = days_of(
            # 2026-10-19 那一周（10-19..10-25）有记录
            "2026-10-20,4,6,3,5,1,\n"
            # 2026-10-26 那一周（10-26..11-01）整周空白
            # 2026-11-02 那一周（11-02..11-08）有记录
            "2026-11-03,5,7,4,6,1,\n"
        )
        weeks = aggregate(days, "week")
        keys = [c.key for c in weeks]
        self.assertEqual(len(weeks), 2)
        self.assertEqual(keys, ["2026-W43", "2026-W45"])
        self.assertNotIn("2026-W44", keys)

    def test_month_open_uses_first_recorded_day(self):
        """月初停牌同理：月开盘取该月第一个有记录日的开。"""
        days = days_of(
            "2026-11-05,2,4,1,3,1,\n"
            "2026-11-28,3,5,2,4,1,\n"
        )
        months = aggregate(days, "month")
        self.assertEqual(len(months), 1)
        self.assertEqual(months[0].open, 2)
        self.assertEqual(months[0].close, 4)

    def test_year_open_uses_first_recorded_day(self):
        days = days_of(
            "2026-03-03,7,8,6,8,1,\n"
            "2026-12-30,8,9,7,9,1,\n"
        )
        years = aggregate(days, "year")
        self.assertEqual(len(years), 1)
        self.assertEqual(years[0].open, 7)
        self.assertEqual(years[0].close, 9)


if __name__ == "__main__":
    unittest.main()
