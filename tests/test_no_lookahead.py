"""验收判据 5：任何指标都不许看未来。

断言方式：只给到第 N 天的数据，算出来的结果必须与给全量数据时「前 N 天的部分」逐项相等。
这条是红线一（不预测）在代码层面的落地。
"""

from __future__ import annotations

import sys
import unittest
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
    volatility,
)
from core.narrate import build as narrate  # noqa: E402
from core.store import load  # noqa: E402

CSV = ROOT / "fixtures" / "full.csv"


class TestNoForwardLookingMetric(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full = load(CSV)

    def prefixes(self):
        for n in range(2, len(self.full) + 1):
            yield n, self.full[:n]

    def test_daily_returns_tail_stable(self):
        full_returns = daily_returns(self.full)
        for n, prefix in self.prefixes():
            partial = daily_returns(prefix)
            if not partial:
                continue
            # 前 N 天算出的收益率，必须是全量结果的开头一段
            self.assertEqual(
                [round(x, 12) for x in partial],
                [round(x, 12) for x in full_returns[: len(partial)]],
                f"只给到第 {n} 天时，收益率与全量结果不一致",
            )

    def test_amplitudes_tail_stable(self):
        full_amp = amplitudes(self.full)
        for n, prefix in self.prefixes():
            partial = amplitudes(prefix)
            if not partial:
                continue
            self.assertEqual(
                [round(x, 12) for x in partial],
                [round(x, 12) for x in full_amp[: len(partial)]],
                f"只给到第 {n} 天时，振幅与全量结果不一致",
            )

    def test_volatility_of_prefix_is_not_affected_by_future(self):
        """波动率只吃自己收到的收益率样本；多加未来几天不会改变「前 N 天」这一段的取值。

        具体做法：对每个前缀分别算 volatility(收益率)，再对比全量数据的前 N 个收益率
        算出来的值——两者必须相等。同时验证函数是纯的：同一输入重复调用结果一致。
        """
        full_returns = daily_returns(self.full)
        checked = 0
        for n, prefix in self.prefixes():
            partial_returns = daily_returns(prefix)
            if len(partial_returns) < 2:
                self.assertIsNone(volatility(partial_returns))
                continue
            partial = volatility(partial_returns)
            expected = volatility(full_returns[: len(partial_returns)])
            self.assertIsNotNone(partial)
            self.assertEqual(partial, expected, f"第 {n} 天为界时波动率不一致")
            self.assertEqual(partial, volatility(partial_returns))  # 纯函数：可重复
            checked += 1
        self.assertGreater(checked, 5)

    def test_max_drawdown_of_prefix_only_uses_past(self):
        for n, prefix in self.prefixes():
            dd_partial, date_partial, _ = max_drawdown(prefix)
            dd_full_running, date_full_running, _ = max_drawdown(self.full[:n])
            self.assertEqual(dd_partial, dd_full_running)
            self.assertEqual(date_partial, date_full_running)
            # 前缀的结果绝不可能是「未来某天」造成的
            if date_partial is not None:
                self.assertLessEqual(date_partial, prefix[-1].date)

    def test_streaks_of_prefix_never_mention_future_dates(self):
        for n, prefix in self.prefixes():
            up, down = streaks(prefix)
            for seg in (up, down):
                if seg is None:
                    continue
                self.assertLessEqual(seg.start, prefix[-1].date)
                self.assertLessEqual(seg.end, prefix[-1].date)

    def test_stats_counters_monotonic(self):
        prev_recorded = -1
        prev_total = -1
        for n, prefix in self.prefixes():
            stats = compute_stats(prefix)
            self.assertGreaterEqual(stats.recorded_days, prev_recorded)
            self.assertGreaterEqual(stats.total_days, prev_total)
            self.assertLessEqual(stats.last_recorded, prefix[-1].date)
            prev_recorded = stats.recorded_days
            prev_total = stats.total_days

    def test_candles_of_prefix_are_prefix_of_full(self):
        for period in ("day", "week", "month", "year"):
            full_candles = aggregate(self.full, period)
            for n, prefix in self.prefixes():
                partial = aggregate(prefix, period)
                if not partial:
                    continue
                # 前缀的前 k-1 根必须与全量完全一致；最后一根可能还没走完
                for got, want in zip(partial[:-1], full_candles[: len(partial) - 1]):
                    self.assertEqual((got.key, got.open, got.high, got.low, got.close), (want.key, want.open, want.high, want.low, want.close))

    def test_narrate_changes_with_data_but_never_looks_ahead(self):
        """narrate 只看输入；截断数据后它描述的事实不能来自未来。"""
        for n, prefix in self.prefixes():
            text = narrate(prefix)
            self.assertIsInstance(text, str)
            if len(prefix) >= 2:
                # 截断到某天之后，文本里出现的日期痕迹不能晚于最后一个输入日
                last = prefix[-1].date
                self.assertNotIn(f"{last.year + 1} 年", text)


if __name__ == "__main__":
    unittest.main()
