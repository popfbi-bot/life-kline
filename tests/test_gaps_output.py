"""gaps 命令的终端输出：进度条长度与它旁边写的百分比必须一致。

这是从实际输出里抓到的 bug：进度条按比例画，右侧却硬编码成 100%。
新增测试文件，不改既有断言。
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "fixtures" / "full.csv"

HEADER = "date,open,high,low,close,volume,note,tags\n"


def run_gaps(csv_path: Path) -> str:
    result = subprocess.run(
        [sys.executable, str(ROOT / "cli.py"), "--path", str(csv_path), "gaps"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


class GapsBarTest(unittest.TestCase):
    def test_bar_length_matches_printed_percentage(self):
        output = run_gaps(CSV)
        bars = [line for line in output.splitlines() if line.startswith("停牌 ")]
        self.assertEqual(1, len(bars), f"没有找到进度条：{output}")
        line = bars[0]

        filled = line.count("█")
        empty = line.count("░")
        self.assertGreater(filled + empty, 0, "进度条是空的")

        # 百分比标签必须与进度条实际填满的比例一致（±1 格取整误差）
        percent = float(line.split("停牌 ", 1)[1].split("%")[0].split()[-1])
        width = filled + empty
        self.assertAlmostEqual(percent / 100, filled / width, delta=1 / width + 1e-9,
                               msg=f"进度条与百分比不一致：{line}")

    def test_bar_is_not_hardcoded_full(self):
        """停牌率 84.4% 时，进度条不能画满，也不能写 100%。"""
        output = run_gaps(CSV)
        line = next(l for l in output.splitlines() if l.startswith("停牌 "))
        self.assertNotIn("100%", line)
        self.assertGreater(line.count("░"), 0, "未满的进度条必须留出空格")

    def test_half_suspended_shows_half_bar(self):
        """造一份正好一半停牌的数据，断言进度条与百分比同时是 50%。"""
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "life.csv"
            csv_path.write_text(
                HEADER
                + "2026-03-02,5,6,4,5,,\n"
                + "2026-03-03,,,,,,\n",
                encoding="utf-8",
            )
            output = run_gaps(csv_path)
        line = next(l for l in output.splitlines() if l.startswith("停牌 "))
        self.assertIn("50.0%", line)
        filled, empty = line.count("█"), line.count("░")
        self.assertAlmostEqual(0.5, filled / (filled + empty), delta=0.03, msg=line)

    def test_trailing_gap_is_counted(self):
        """末尾的停牌日也要算：写了「当天停牌不能又报一天没停牌」。

        这是从实际输出里抓到的 bug —— suspension_gaps 原来只扫到最后一个
        *有记录* 的日子，末尾停牌日被整段丢掉。
        """
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "life.csv"
            csv_path.write_text(
                HEADER + "2026-03-02,5,6,4,5,,\n2026-03-03,,,,,,\n",
                encoding="utf-8",
            )
            output = run_gaps(csv_path)
        self.assertIn("停牌 1 天", output)
        self.assertIn("2026-03-03", output)
        self.assertNotIn("一天没停牌", output)

    def test_leading_gap_is_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "life.csv"
            csv_path.write_text(
                HEADER + "2026-03-02,,,,,,\n2026-03-03,5,7,4,6,,\n",
                encoding="utf-8",
            )
            output = run_gaps(csv_path)
        self.assertIn("停牌 1 天", output)
        self.assertIn("2026-03-02", output)

    def test_gap_count_matches_stats(self):
        """gaps 报的天数必须与 stats 报的停牌天数一致。"""
        for csv_path in (CSV,):
            gaps_out = run_gaps(csv_path)
            stats = subprocess.run(
                [sys.executable, str(ROOT / "cli.py"), "--path", str(csv_path), "stats"],
                cwd=str(ROOT), capture_output=True, text=True,
            )
            gaps_days = next(l for l in gaps_out.splitlines() if l.startswith("有记录 ")).split("停牌 ")[1].split(" 天")[0]
            stats_days = next(l for l in stats.stdout.splitlines() if l.startswith("停牌天数")).split()[-2]
            self.assertEqual(gaps_days.strip(), stats_days.strip(), "gaps 与 stats 的停牌天数不一致")

    def test_no_gap_case_has_no_bar(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "life.csv"
            csv_path.write_text(
                HEADER + "2026-03-02,5,6,4,5,,\n2026-03-03,5,7,4,6,,\n",
                encoding="utf-8",
            )
            output = run_gaps(csv_path)
        self.assertIn("一天没停牌", output)
        self.assertNotIn("█", output)


if __name__ == "__main__":
    unittest.main()
