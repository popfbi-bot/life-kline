"""缺口在图上要看得见，且位置正确。

两个从实际渲染里抓到的 bug：
1. 停牌虚线按日历比例算 x，而 K 线等距排列 —— 虚线落在两根柱子中间偏左，
   读者会以为缺口在别处；
2. 缺口不占宽度 —— 缺 58 天和缺 1 天在图上一样宽，「你很久没记录」看不出来。
"""

from __future__ import annotations

import datetime as dt
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import render  # noqa: E402
from core.aggregate import aggregate  # noqa: E402
from core.metrics import compute_stats, suspension_gaps  # noqa: E402
from core.narrate import build as narrate_build  # noqa: E402
from core.store import load, parse_csv_text  # noqa: E402

CSV = ROOT / "fixtures" / "full.csv"
HEADER = "date,open,high,low,close,volume,note,tags\n"


def html_for(csv_text: str, period: str = "day", mask: bool = False) -> str:
    days = parse_csv_text(csv_text)
    stats = compute_stats(days)
    return render.render(
        render.RenderInput(
            candles=aggregate(days, period),
            gap_dates=suspension_gaps(days),
            review=narrate_build(days, period=period),
            cards=[
                ("有记录天数", str(stats.recorded_days)),
                ("最长连阳", "—"),
                ("最大回撤", "—"),
                ("停牌率", "—"),
            ],
            extra_rows=[],
            period_label="测试",
            mask=mask,
        )
    )


class GapWidthTest(unittest.TestCase):
    def test_gap_width_is_monotonic_and_capped(self) -> None:
        """缺得越久占得越宽，但封顶，不让长停牌挤扁整张图。"""
        widths = [render._gap_width(n) for n in (0, 1, 6, 7, 29, 30, 365, 5000)]
        self.assertEqual(0.0, widths[0], "没缺就不占宽度")
        self.assertEqual(sorted(widths), widths, f"宽度必须单调不减：{widths}")
        self.assertLessEqual(max(widths), 1.6, "缺口宽度必须封顶")
        self.assertGreater(widths[-1], widths[1], "缺一个月要比缺一天更宽")

    def test_slot_offsets_accumulate_gap_room(self) -> None:
        csv_text = HEADER + (
            "2026-01-01,5,6,4,5,,\n"
            "2026-01-02,5,6,4,5,,\n"
            "2026-01-10,5,6,4,5,,\n"      # 缺 7 天
            "2026-03-10,5,6,4,5,,\n"      # 缺 58 天
        )
        days = parse_csv_text(csv_text)
        offsets = render._slot_offsets(aggregate(days, "day"))
        steps = [b - a for a, b in zip(offsets, offsets[1:])]
        self.assertEqual(3, len(steps))
        self.assertAlmostEqual(1.0, steps[0], places=6)   # 连续两天
        self.assertGreater(steps[1], 1.0)                  # 中间有缺口
        self.assertGreater(steps[2], steps[1])             # 长缺口比短缺口宽

    def test_long_gap_gets_more_room_than_short_gap(self) -> None:
        """缺口越长，两根柱子之间留的空档越宽（虚线本身总在空档正中）。

        所以要比的不是虚线的绝对 x，而是虚线到两侧柱子的距离。
        """
        short_text = HEADER + "2026-01-01,5,6,4,5,,\n2026-01-03,5,6,4,5,,\n"
        long_text = HEADER + "2026-01-01,5,6,4,5,,\n2026-03-10,5,6,4,5,,\n"

        def center_gap(html: str) -> float:
            rects = [float(m) for m in re.findall(r'<rect x="([\d.]+)"[^>]*fill="#[0-9a-f]{6}" rx="1"/>', html)]
            dash = float(re.search(r'<line x1="([\d.]+)"[^>]*stroke-dasharray="2 4"', html).group(1))
            centers = sorted(x + 26.0 / 2 for x in rects)
            self.assertEqual(2, len(centers))
            left_dash = centers[1] - dash
            right_dash = dash - centers[0]
            # 虚线在两根柱子正中：两侧距离应该差不多，且都大于柱宽的一半
            self.assertAlmostEqual(left_dash, right_dash, delta=1.0)
            return left_dash

        short_gap = center_gap(html_for(short_text))
        long_gap = center_gap(html_for(long_text))
        self.assertGreater(long_gap, short_gap, "缺 58 天的空档应该比缺 1 天宽")


class GapPositionTest(unittest.TestCase):
    def test_dash_sits_between_two_candles(self) -> None:
        """虚线必须落在两根 K 线之间，不能压在柱子上。"""
        html = html_for(CSV.read_text(encoding="utf-8"))
        candle_xs = sorted(
            float(m) for m in re.findall(r'<rect x="([\d.]+)" y="[\d.]+" width="[\d.]+" height="[\d.]+" fill="#[0-9a-f]{6}" rx="1"/>', html)
        )
        dash_xs = [float(m) for m in re.findall(r'<line x1="([\d.]+)"[^>]*stroke-dasharray="2 4"', html)]
        self.assertGreater(len(dash_xs), 0, "fixture 里有停牌，应该画出虚线")

        # 每根 K 线的中心
        centers = []
        for x in candle_xs:
            width = 26.0
            centers.append(x + width / 2)
        centers.sort()

        for x in dash_xs:
            on_a_candle = any(abs(x - c) < 12 for c in centers)
            self.assertFalse(on_a_candle, f"虚线 x={x} 压在 K 线上（中心 {centers}）")

    def test_gap_legend_wording(self) -> None:
        html = html_for(CSV.read_text(encoding="utf-8"))
        self.assertIn("停牌", html)
        self.assertIn('stroke-dasharray="2 4"', html)


class TitleVocabularyTest(unittest.TestCase):
    """红线三：标题里不能出现「人生」这类把自评当成客观命名的词。"""

    def test_title_says_state_not_life(self) -> None:
        html = html_for(CSV.read_text(encoding="utf-8"))
        self.assertIn("<title>状态 K 线</title>", html)
        self.assertNotIn("人生 K 线", html)
        self.assertNotIn("人生", html)

    def test_mask_title_says_state(self) -> None:
        html = html_for(CSV.read_text(encoding="utf-8"), mask=True)
        self.assertNotIn("人生", html)


if __name__ == "__main__":
    unittest.main()
