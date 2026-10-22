"""验收判据 9：narrate 的数字必须随数据变化，且数据太少时不说废话。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.narrate import build as narrate  # noqa: E402
from core.store import parse_csv_text  # noqa: E402

HEADER = "date,open,high,low,close,volume,note,tags\n"

DATA_A = HEADER + """2026-01-05,3,5,2,4,1,
2026-01-06,4,6,3,5,1,
2026-01-07,5,7,4,6,1,
2026-01-08,6,8,5,7,1,
2026-02-10,7,9,2,2,1,
2026-03-11,2,4,1,3,1,
"""

DATA_B = HEADER + """2026-05-04,8,9,7,8,1,
2026-05-05,8,9,7,8,1,
2026-05-06,8,9,7,8,1,
2026-06-01,8,9,7,8,1,
2026-06-02,8,9,1,1,1,
"""

TOO_LITTLE = HEADER + """2026-07-01,5,6,4,5,1,
2026-07-02,5,6,4,5,1,
2026-07-03,5,6,4,5,1,
"""


class TestNarrateUsesRealNumbers(unittest.TestCase):
    def test_numbers_change_with_data(self):
        a = narrate(parse_csv_text(DATA_A))
        b = narrate(parse_csv_text(DATA_B))
        self.assertNotEqual(a, b)
        # A：6 天记录，最长连阳 3 天（01-05 起），最大回撤 1-2/7
        # B：5 天记录，没有连阳（全是平盘 + 最后一天暴跌），最大回撤 1-1/8
        self.assertIn("6 天", a)
        self.assertIn("5 天", b)
        self.assertIn("3 天", a)
        self.assertIn("回撤", a)
        self.assertIn("回撤", b)

    def test_not_a_hardcoded_template(self):
        """两份数据的关键数字不一样，才说明是算出来的。"""
        import re

        a = re.findall(r"\d+", narrate(parse_csv_text(DATA_A)))
        b = re.findall(r"\d+", narrate(parse_csv_text(DATA_B)))
        self.assertNotEqual(a, b)

    def test_no_meaningless_zero_days(self):
        """数据太少时，不许输出「最长连阳 0 天」这种废话。"""
        text = narrate(parse_csv_text(TOO_LITTLE))
        self.assertNotIn("0 天", text)
        self.assertNotIn("连阳 0", text)
        self.assertNotIn("回撤 0%", text)

    def test_flat_data_says_no_streak_instead_of_zero(self):
        """连着平盘：没有连阳也没有连阴，就别提连阳。"""
        text = narrate(parse_csv_text(TOO_LITTLE))
        self.assertNotIn("连阳", text)
        self.assertIn("没跌破", text)  # 回撤近 0 时换成克制的说法

    def test_no_data_case(self):
        text = narrate([])
        self.assertIn("没有记录", text)
        self.assertNotIn("0 天", text)

    def test_all_suspended_case(self):
        text = narrate(parse_csv_text(HEADER + "2026-07-01,,,,,,,\n2026-07-02,,,,,,,\n"))
        self.assertIn("没有记录", text)

    def test_mentions_unsuspended_days_honestly(self):
        """停牌率过半时必须点明，这是产品价值之一，不能藏起来。"""
        text = narrate(parse_csv_text(DATA_A))
        self.assertIn("停牌", text)

    def test_no_chicken_soup_structure(self):
        """语气克制：不出现感叹号、不出现鼓励式措辞。"""
        for data in (DATA_A, DATA_B, TOO_LITTLE):
            text = narrate(parse_csv_text(data))
            self.assertNotIn("！", text)
            self.assertNotIn("加油", text)
            self.assertNotIn("相信", text)

    def test_single_day(self):
        text = narrate(parse_csv_text(HEADER + "2026-07-01,5,6,4,5,1,\n"))
        self.assertIn("1 天", text)
        self.assertNotIn("连阳", text)


class TestStreakWindowStartsAtFirstCandle(unittest.TestCase):
    """连阳区间要从第一根阳线写起，不能把 Segment.start（参照日）当第一天。

    issue #10 的现场：`fixtures/full.csv` 的最长连阳是 3 根
    （10-23 / 10-29 / 10-31），start 记的是参照日 10-22，
    以前 narrate 拿 start 当起点，于是输出「10 月 22 日–10 月 31 日」。
    """

    def test_window_starts_on_first_up_candle(self):
        from tests.helpers import FIXTURES
        from core.store import load

        text = narrate(load(FIXTURES / "full.csv"))
        self.assertIn("最长连阳 3 天", text)
        self.assertIn("10 月 23 日–10 月 31 日", text)
        self.assertNotIn("10 月 22 日–10 月 31 日", text)


if __name__ == "__main__":
    unittest.main()
