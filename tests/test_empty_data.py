"""空数据与空区间：给一句人话，不算错，也不说假话。

两个从实际输出里抓到的口径不一致：
1. `stats` 对空数据返回退出码 2（当成错误），但「还没开始记」不是错误；
2. `gaps` 对空数据显示「这段时间一天没停牌」—— 没数据不等于没停牌。
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


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "cli.py"), *args],
        cwd=str(ROOT), capture_output=True, text=True,
    )


class EmptyDataTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.empty = Path(self._tmp.name) / "empty.csv"
        self.empty.write_text(HEADER, encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_stats_on_empty_file_is_not_an_error(self) -> None:
        result = run("--path", str(self.empty), "stats")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("没有数据", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_gaps_on_empty_file_does_not_claim_no_gap(self) -> None:
        result = run("--path", str(self.empty), "gaps")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("一天没停牌", result.stdout, "没数据不能说「一天没停牌」")
        self.assertIn("还没有任何记录", result.stdout)

    def test_stats_on_empty_range_is_not_an_error(self) -> None:
        result = run("--path", str(CSV), "stats", "--from", "2020-01-01", "--to", "2020-01-31")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("没有数据", result.stdout)

    def test_verify_on_empty_file_passes(self) -> None:
        result = run("--path", str(self.empty), "verify")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("0 行", result.stdout)

    def test_chart_on_empty_file_renders_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "empty.html"
            result = run("--path", str(self.empty), "chart", "--out", str(out))
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(out.exists())
            html = out.read_text(encoding="utf-8")
            self.assertIn("<svg", html)
            # 图上不画任何 K 线，并且老实说明为什么
            self.assertIn("没有记录", html)
            self.assertNotIn("<rect", html.split("<svg", 1)[1])

    def test_chart_on_all_gap_file_is_not_an_error(self) -> None:
        """整份数据全是停牌：不是错误，画一张空图并说明。"""
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "allgap.csv"
            csv_path.write_text(HEADER + "2026-03-02,,,,,,\n", encoding="utf-8")
            out = Path(tmp) / "allgap.html"
            result = run("--path", str(csv_path), "chart", "--out", str(out))
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("没有记录", out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
