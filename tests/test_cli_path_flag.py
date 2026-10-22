"""`--path` 放在子命令前后都得能用（issue #8）。

原来只挂在顶层，`life-kline verify --path x.csv` 会被 argparse 拒掉，
而 README 的写法让人正好这么写。
"""

from __future__ import annotations

import unittest

from tests.helpers import FIXTURES, run_cli


class PathBeforeSubcommand(unittest.TestCase):
    def test_path_before_subcommand(self):
        code, out, err = run_cli("--path", str(FIXTURES / "full.csv"), "verify")
        self.assertEqual(code, 0, err)
        self.assertIn("校验通过", out)


class PathAfterSubcommand(unittest.TestCase):
    def test_verify_accepts_path_after_subcommand(self):
        code, out, err = run_cli("verify", "--path", str(FIXTURES / "full.csv"))
        self.assertEqual(code, 0, err)
        self.assertIn("校验通过", out)

    def test_stats_accepts_path_after_subcommand(self):
        code, out, err = run_cli("stats", "--path", str(FIXTURES / "full.csv"))
        self.assertEqual(code, 0, err)
        self.assertIn("停牌率", out)

    def test_gaps_accepts_path_after_subcommand(self):
        code, out, err = run_cli("gaps", "--path", str(FIXTURES / "full.csv"))
        self.assertEqual(code, 0, err)
        self.assertIn("停牌", out)


class BothPositionsAgree(unittest.TestCase):
    def test_same_output_whichever_side(self):
        before = run_cli("--path", str(FIXTURES / "full.csv"), "stats")
        after = run_cli("stats", "--path", str(FIXTURES / "full.csv"))
        self.assertEqual(before[0], 0, before[2])
        self.assertEqual(before[:2], after[:2])


if __name__ == "__main__":
    unittest.main()
