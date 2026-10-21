"""验收判据 1：fixtures/full.csv + 手算期望值，断言精确相等。

===========================================================================
fixtures/full.csv 全文（14 行，2 天停牌）

    date,open,high,low,close,volume,note,tags
    2026-10-18,6,8,4,7,12,下午把那个 bug 修了,work
    2026-10-19,7,7,5,5,8,,tired
    2026-10-20,,,,,,,                       <- 停牌
    2026-10-21,5,9,3,8,15,早上很糟下午反转,breakthrough
    2026-10-22,8,8,6,6,5,,tired
    2026-10-23,6,7,5,7,7,,
    2026-10-29,7,9,6,9,10,好的一天,work
    2026-10-30,,,,,,,                       <- 停牌
    2026-10-31,9,10,8,10,20,收尾,work
    2026-11-01,4,6,2,3,4,低开低走,tired
    2026-11-02,3,9,3,8,11,反转日,breakthrough
    2026-12-31,8,8,7,8,9,跨年前一天,work
    2027-01-01,8,9,7,9,6,新年,work
    2027-01-02,9,10,8,10,12,还在好状态,work

区间：2026-10-18 → 2027-01-02，共 (2027-01-02 - 2026-10-18).days + 1 = 77 天
有记录 12 天，停牌 77 - 12 = 65 天。
===========================================================================
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.aggregate import aggregate  # noqa: E402
from core.metrics import (  # noqa: E402
    amplitudes,
    compute_stats,
    daily_returns,
    max_drawdown,
    streaks,
    suspension_gaps,
    volatility,
)
from core.store import load  # noqa: E402

CSV = ROOT / "fixtures" / "full.csv"


def approx(values, places=10):
    return [round(v, places) for v in values]


class TestHandCalculatedMetrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.days = load(CSV)
        cls.recorded = [d for d in cls.days if not d.suspended]
        cls.stats = compute_stats(cls.days)

    # -- 基础计数 ---------------------------------------------------------
    def test_recorded_and_suspended_counts(self):
        # 14 行里 2 行全空 -> 有记录 12 天
        self.assertEqual(self.stats.recorded_days, 12)
        # 2026-10-18 到 2027-01-02 共 77 天 -> 停牌 65 天
        self.assertEqual(self.stats.total_days, 77)
        self.assertEqual(self.stats.suspended_days, 65)
        # 65 / 77 = 0.844155844...
        self.assertAlmostEqual(self.stats.suspension_rate, 65 / 77, places=12)

    # -- 日收益率 ---------------------------------------------------------
    def test_daily_returns_hand_checked(self):
        """
        有记录日收盘序列：7, 5, 8, 6, 7, 9, 10, 3, 8, 8, 9, 10
        注意 2026-10-21 的基准是 10-19 的 5（中间 10-20 停牌，直接跨过），
             2026-10-29 的基准是 10-23 的 7（跨过 10-24..10-28 的空白）。
        手算：
          (5-7)/7      = -0.2857142857142857
          (8-5)/5      = +0.6
          (6-8)/8      = -0.25
          (7-6)/6      = +0.16666666666666666
          (9-7)/7      = +0.2857142857142857
          (10-9)/9     = +0.1111111111111111
          (3-10)/10    = -0.7
          (8-3)/3      = +1.6666666666666667
          (8-8)/8      = 0.0
          (9-8)/8      = +0.125
          (10-9)/9     = +0.1111111111111111
        """
        expected = [
            -4 / 14,
            3 / 5,
            -1 / 4,
            1 / 6,
            2 / 7,
            1 / 9,
            -7 / 10,
            5 / 3,
            0.0,
            1 / 8,
            1 / 9,
        ]
        self.assertEqual(approx(daily_returns(self.days)), approx(expected))

    # -- 振幅 -------------------------------------------------------------
    def test_amplitudes_hand_checked(self):
        """
        (high - low) / prev_close，prev_close 是上一个有记录日的收盘：
          (7-5)/7   = 0.2857142857142857   (10-19)
          (9-3)/5   = 1.2                  (10-21)
          (8-6)/8   = 0.25                 (10-22)
          (7-5)/6   = 0.3333333333333333   (10-23)
          (9-6)/7   = 0.4285714285714286   (10-29)
          (10-8)/9  = 0.2222222222222222   (10-31)
          (6-2)/10  = 0.4                  (11-01)
          (9-3)/3   = 2.0                  (11-02)
          (8-7)/8   = 0.125                (12-31)
          (9-7)/8   = 0.25                 (2027-01-01)
          (10-8)/9  = 0.2222222222222222   (2027-01-02)
        """
        expected = [
            2 / 7,
            6 / 5,
            2 / 8,
            2 / 6,
            3 / 7,
            2 / 9,
            4 / 10,
            6 / 3,
            1 / 8,
            2 / 8,
            2 / 9,
        ]
        self.assertEqual(approx(amplitudes(self.days)), approx(expected))

    # -- 波动率 -----------------------------------------------------------
    def test_volatility_is_sample_stddev(self):
        """
        样本标准差（n-1 分母，n = 11）：
          mean = (-0.2857142857142857 + 0.6 - 0.25 + 0.16666666666666666 + 0.2857142857142857
                  + 0.1111111111111111 - 0.7 + 1.6666666666666667 + 0 + 0.125 + 0.1111111111111111) / 11
               = 1.8295655... / 11 = 0.1663241...
          sum of squared deviations = 3.9731176...
          var = 3.9731176... / 10 = 0.39731176...
          std = sqrt(0.39731176...) = 0.630326...
        这里用精确分数断言，避免抄写误差。
        """
        from fractions import Fraction

        returns = [
            Fraction(-2, 7),
            Fraction(3, 5),
            Fraction(-1, 4),
            Fraction(1, 6),
            Fraction(2, 7),
            Fraction(1, 9),
            Fraction(-7, 10),
            Fraction(5, 3),
            Fraction(0),
            Fraction(1, 8),
            Fraction(1, 9),
        ]
        n = len(returns)
        mean = sum(returns) / n
        var = sum((r - mean) ** 2 for r in returns) / (n - 1)
        expected = float(var) ** 0.5
        self.assertAlmostEqual(volatility([float(r) for r in returns]), expected, places=12)
        self.assertAlmostEqual(self.stats.volatility, expected, places=12)

    def test_volatility_needs_two_samples(self):
        # 只有 1 个收益率（2 天记录）时，样本标准差无从谈起
        self.assertIsNone(volatility([]))
        self.assertIsNone(volatility([0.1]))

    # -- 最大回撤 ---------------------------------------------------------
    def test_max_drawdown_hand_checked(self):
        """
        close 序列：7, 5, 8, 6, 7, 9, 10, 3, 8, 8, 9, 10
        逐日 running max 与回撤：
          t1 7  max=7  dd=0
          t2 5  max=7  dd=1-5/7  = 0.2857142857142857
          t3 8  max=8  dd=0
          t4 6  max=8  dd=1-6/8  = 0.25
          t5 7  max=8  dd=1-7/8  = 0.125
          t6 9  max=9  dd=0
          t7 10 max=10 dd=0
          t8 3  max=10 dd=1-3/10 = 0.7   <- 最大
          t9 8  max=10 dd=0.2
          t10 8 max=10 dd=0.2
          t11 9 max=10 dd=0.1
          t12 10 max=10 dd=0
        最大回撤 = 0.7，发生在 2026-11-01，之前的高点是 2026-10-31（close=10）
        """
        dd, dd_date, peak_date = max_drawdown(self.days)
        self.assertEqual(round(dd, 12), 0.7)
        self.assertEqual(dd_date, date(2026, 11, 1))
        self.assertEqual(peak_date, date(2026, 10, 31))
        self.assertEqual(self.stats.max_drawdown, dd)

    # -- 连阳 / 连阴 -------------------------------------------------------
    def test_streaks_hand_checked(self):
        """
        close：7 → 5(阴) → 8(阳) → 6(阴) → 7(阳) → 9(阳) → 10(阳)
              → 3(阴) → 8(阳) → 8(平) → 9(阳) → 10(阳)
        连阳段：8 单独 1 天；6→7→9 共 3 天（10-22 → 10-29，中间 10-30 停牌但不断）；
                9→10 共 2 天。最长 = 3。
        段的 start 记的是「第一根阳线的前一日」，因为涨幅是相对它算的：
        6→7 的那根阳线在 10-23，但它参照的基准日是 10-22。
        连阴段：全是 1 天。最长 = 1。
        """
        up, down = streaks(self.days)
        self.assertEqual(up.length, 3)
        self.assertEqual(up.start, date(2026, 10, 22))
        self.assertEqual(up.end, date(2026, 10, 31))
        self.assertEqual(down.length, 1)
        self.assertEqual(self.stats.longest_up, up)
        self.assertEqual(self.stats.longest_down, down)

    # -- 停牌日清单 --------------------------------------------------------
    def test_gap_dates_listed(self):
        gaps = suspension_gaps(self.days)
        self.assertEqual(len(gaps), 65)
        self.assertIn(date(2026, 10, 20), gaps)
        self.assertIn(date(2026, 10, 30), gaps)
        self.assertIn(date(2026, 11, 3), gaps)
        self.assertIn(date(2026, 12, 30), gaps)
        self.assertNotIn(date(2026, 10, 18), gaps)


class TestAggregationRules(unittest.TestCase):
    """验收判据 2 的聚合面：周/月/年的开高低收必须照抄真实 K 线规则。"""

    @classmethod
    def setUpClass(cls):
        cls.days = load(CSV)

    def test_week_candles_hand_checked(self):
        """
        按 ISO 周分组（只看有记录日）：
          2026-W42：只有 10-18（开6 高8 低4 收7 量12）-> 开6 高8 低4 收7
          2026-W43：10-19(开7,高7,低5,收5) 10-21(开5,高9,低3,收8)
                   10-22(开8,高8,低6,收6) 10-23(开6,高7,低5,收7)
                   -> 开=7（10-19 的开），高=max(7,9,8,7)=9，低=min(5,3,6,5)=3，收=7
                   量=8+15+5+7=35
          2026-W44：含 10-29(开7,高9,低6,收9,量10)、10-31(开9,高10,低8,收10,量20)、
                   11-01(开4,高6,低2,收3,量4)。11-01 是周日，ISO 周归上一周。
                   -> 开=7，高=max(9,10,6)=10，低=min(6,8,2)=2，收=3（11-01 的收）
                      量=10+20+4=34
          2026-W45：只有 11-02（开3,高9,低3,收8,量11）
                   -> 开3 高9 低3 收8 量11
          2026-W53：12-31、2027-01-01、2027-01-02 —— 注意 ISO 周会把跨年的
                   1 月 1–2 日归到上一年的第 53 周，所以它们和 12-31 同组：
                   开=8（12-31 的开），高=max(8,9,10)=10，低=min(7,7,8)=7，
                   收=10（01-02 的收），量=9+6+12=27
        真正整周全停牌的情况本 fixture 里没有，另见 tests/test_gaps.py 专测。
        """
        weeks = aggregate(self.days, "week")
        keys = [c.key for c in weeks]
        self.assertEqual(keys, ["2026-W42", "2026-W43", "2026-W44", "2026-W45", "2026-W53"])

        w42 = weeks[0]
        self.assertEqual((w42.open, w42.high, w42.low, w42.close), (6, 8, 4, 7))
        self.assertEqual(w42.volume, 12)  # 只有 10-18 一天有量

        w43 = weeks[1]
        self.assertEqual((w43.open, w43.high, w43.low, w43.close), (7, 9, 3, 7))
        self.assertEqual(w43.volume, 35)

        w44 = weeks[2]
        self.assertEqual((w44.open, w44.high, w44.low, w44.close), (7, 10, 2, 3))
        self.assertEqual(w44.volume, 34)

        w45 = weeks[3]
        self.assertEqual((w45.open, w45.high, w45.low, w45.close), (3, 9, 3, 8))
        self.assertEqual(w45.volume, 11)

        w53 = weeks[4]
        self.assertEqual((w53.open, w53.high, w53.low, w53.close), (8, 10, 7, 10))
        self.assertEqual(w53.volume, 27)

    def test_month_candles_hand_checked(self):
        """
        2026-10：有记录日 10-18,19,21,22,23,29,31（10-20、10-30 停牌）
                 开=6（10-18 的开），高=max(8,7,9,8,7,9,10)=10，低=min(4,5,3,6,5,6,8)=3，收=10
                 量=12+8+15+5+7+10+20=77
        2026-11：11-01、11-02 -> 开=4，高=9，低=2，收=8，量=15
        2026-12：12-31 -> 开=8，高=8，低=7，收=8，量=9
        2027-01：01-01、01-02 -> 开=8，高=10，低=7，收=10，量=18
        """
        months = aggregate(self.days, "month")
        self.assertEqual([c.key for c in months], ["2026-10", "2026-11", "2026-12", "2027-01"])
        oct_ = months[0]
        self.assertEqual((oct_.open, oct_.high, oct_.low, oct_.close), (6, 10, 3, 10))
        self.assertEqual(oct_.volume, 77)
        self.assertEqual(oct_.recorded_days, 7)
        self.assertEqual((months[1].open, months[1].high, months[1].low, months[1].close), (4, 9, 2, 8))
        self.assertEqual((months[2].open, months[2].high, months[2].low, months[2].close), (8, 8, 7, 8))
        self.assertEqual((months[3].open, months[3].high, months[3].low, months[3].close), (8, 10, 7, 10))

    def test_year_candles_hand_checked(self):
        """
        2026 年：有记录 10-18..12-31
                 开=6（10-18 的开），高=max(8,7,9,8,7,9,10,6,9,8)=10，
                 低=min(4,5,3,6,5,6,8,2,3,7)=2，收=8（12-31 的收）
                 量=12+8+15+5+7+10+20+4+11+9=101
        2027 年：01-01、01-02 -> 开=8，高=10，低=7，收=10，量=18
        """
        years = aggregate(self.days, "year")
        self.assertEqual([c.key for c in years], ["2026", "2027"])
        y26 = years[0]
        self.assertEqual((y26.open, y26.high, y26.low, y26.close), (6, 10, 2, 8))
        self.assertEqual(y26.volume, 101)
        y27 = years[1]
        self.assertEqual((y27.open, y27.high, y27.low, y27.close), (8, 10, 7, 10))
        self.assertEqual(y27.volume, 18)

    def test_day_candles_skip_suspended(self):
        days_candles = aggregate(self.days, "day")
        self.assertEqual(len(days_candles), 12)  # 14 行 - 2 天停牌
        keys = [c.key for c in days_candles]
        self.assertNotIn("2026-10-20", keys)
        self.assertNotIn("2026-10-30", keys)


if __name__ == "__main__":
    unittest.main()
