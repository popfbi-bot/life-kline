"""验收判据 4：不可能的数据必须报错，且报错信息带 行号 + 日期 + 字段名。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.model import DataError, build_day  # noqa: E402
from core.store import parse_csv_text  # noqa: E402

HEADER = "date,open,high,low,close,volume,note,tags\n"


class TestOhlcValidationRejectsImpossible(unittest.TestCase):
    """每种不可能的数据一个用例；断言错误文案里同时出现行号、日期、字段名。"""

    def assert_located(self, csv_text: str, line_no: int, day: str, field: str, hint: str = "") -> None:
        with self.assertRaises(DataError) as ctx:
            parse_csv_text(csv_text)
        msg = str(ctx.exception)
        self.assertIn(f"第 {line_no} 行", msg, msg)
        self.assertIn(day, msg, msg)
        self.assertIn(field, msg, msg)
        if hint:
            self.assertIn(hint, msg, msg)

    def test_low_greater_than_open(self):
        # 第 2 行：low=9 > open=2，非法
        self.assert_located(HEADER + "2026-10-18,2,9,9,5,,\n", 2, "2026-10-18", "low")

    def test_high_less_than_close(self):
        # 第 2 行：high=4 < close=8，非法
        self.assert_located(HEADER + "2026-10-18,5,4,3,8,,\n", 2, "2026-10-18", "high")

    def test_partial_fields_rejected(self):
        # 第 2 行：只填了 open 和 low，不猜
        self.assert_located(HEADER + "2026-10-18,5,,3,,,\n", 2, "2026-10-18", "high")
        self.assert_located(HEADER + "2026-10-18,5,,,,,\n", 2, "2026-10-18", "high")

    def test_score_out_of_range(self):
        # 第 2 行：high=11 越界
        self.assert_located(HEADER + "2026-10-18,5,11,3,5,,\n", 2, "2026-10-18", "high", "0–10")

    def test_duplicate_date(self):
        csv_text = HEADER + "2026-10-18,5,6,3,5,,\n2026-10-18,6,7,5,6,,\n"
        self.assert_located(csv_text, 3, "2026-10-18", "date", "重复")

    def test_non_iso_date(self):
        self.assert_located(HEADER + "2026/10/18,5,6,3,5,,\n", 2, "2026/10/18", "date", "ISO")
        self.assert_located(HEADER + "2026-13-40,5,6,3,5,,\n", 2, "2026-13-40", "date")
        self.assert_located(HEADER + "20261018,5,6,3,5,,\n", 2, "20261018", "date")

    def test_edge_legality_not_rejected(self):
        """边界上合法的数据不能误报：全空=停牌，0 和 10 是合法分数。"""
        days = parse_csv_text(HEADER + "2026-10-18,0,10,0,10,0,\n2026-10-19,,,,,,\n")
        self.assertEqual(days[0].low, 0)
        self.assertEqual(days[0].high, 10)
        self.assertTrue(days[1].suspended)

    def test_build_day_reports_field_name(self):
        with self.assertRaises(DataError) as ctx:
            build_day("2026-10-18", {"open": "7", "high": "6", "low": "3", "close": "5"}, line=9)
        msg = str(ctx.exception)
        self.assertIn("第 9 行", msg)
        self.assertIn("2026-10-18", msg)
        self.assertIn("high", msg)

    def test_negative_volume_rejected(self):
        with self.assertRaises(DataError) as ctx:
            build_day("2026-10-18", {"open": "5", "high": "6", "low": "3", "close": "5"}, volume="-1", line=4)
        self.assertIn("volume", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
