"""验收判据 10、11：读命令不许写文件；chart 不许动输入；只读命令不产新文件。

另外覆盖 add/init 的正常路径与「不覆盖已有文件」的行为。
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.helpers import run_cli  # noqa: E402

CSV = ROOT / "fixtures" / "full.csv"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root: Path) -> dict[str, str]:
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


class TestChartDoesNotTouchInput(unittest.TestCase):
    def test_chart_keeps_input_bytes_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            data = work / "data.csv"
            data.write_bytes(CSV.read_bytes())
            before = sha256(data)

            out = work / "life.html"
            code, stdout, stderr = run_cli("chart", "--period", "week", "--out", str(out), path=data)
            self.assertEqual(code, 0, stderr)
            self.assertEqual(sha256(data), before, "chart 改了输入 CSV")
            self.assertTrue(out.exists())

    def test_chart_mask_keeps_input_bytes_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            data = work / "data.csv"
            data.write_bytes(CSV.read_bytes())
            before = sha256(data)
            out = work / "share.html"
            code, _, stderr = run_cli("chart", "--mask", "--out", str(out), path=data)
            self.assertEqual(code, 0, stderr)
            self.assertEqual(sha256(data), before)

    def test_chart_writes_only_the_out_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            data = work / "data.csv"
            data.write_bytes(CSV.read_bytes())
            before = snapshot(work)
            out = work / "out" / "life.html"
            code, _, stderr = run_cli("chart", "--out", str(out), path=data)
            self.assertEqual(code, 0, stderr)
            after = snapshot(work)
            new_files = set(after) - set(before)
            self.assertEqual(new_files, {"out/life.html"}, "chart 额外写了文件")


class TestReadonlyCommandsWriteNothing(unittest.TestCase):
    def test_verify_stats_gaps_produce_no_files(self):
        for command in (("verify",), ("stats",), ("gaps",)):
            with tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                data = work / "data.csv"
                data.write_bytes(CSV.read_bytes())
                before = snapshot(work)
                code, stdout, stderr = run_cli(*command, path=data)
                self.assertEqual(code, 0, stderr)
                after = snapshot(work)
                self.assertEqual(after, before, f"{command} 产生了新文件或改了文件")
                self.assertTrue(stdout.strip(), f"{command} 没有输出")

    def test_stats_with_range_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            data = work / "data.csv"
            data.write_bytes(CSV.read_bytes())
            before = snapshot(work)
            code, out, err = run_cli("stats", "--from", "2026-10-18", "--to", "2026-11-02", path=data)
            self.assertEqual(code, 0, err)
            self.assertEqual(snapshot(work), before)
            self.assertIn("有记录天数", out)


class TestInitAndAdd(unittest.TestCase):
    def test_init_creates_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "life.csv"
            code, out, err = run_cli("init", path=data)
            self.assertEqual(code, 0, err)
            self.assertTrue(data.exists())
            text = data.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("date,open,high,low,close,volume,note,tags"))
            # 模板里有一条停牌日，方便理解「全空 = 停牌」
            self.assertIn("2026-10-20,,,", text)  # 整行全空 = 停牌

    def test_init_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "life.csv"
            data.write_text("date,open,high,low,close,volume,note,tags\n2026-01-01,1,2,0,1,,\n", encoding="utf-8")
            before = sha256(data)
            code, out, _ = run_cli("init", path=data)
            self.assertEqual(code, 0)
            self.assertIn("已存在", out)
            self.assertEqual(sha256(data), before)

    def test_add_non_interactive(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "life.csv"
            code, _, err = run_cli(
                "add", "--date", "2026-04-21", "--open", "5", "--high", "9", "--low", "3", "--close", "8",
                path=data,
            )
            self.assertEqual(code, 0, err)
            text = data.read_text(encoding="utf-8")
            self.assertIn("2026-04-21,5,9,3,8", text)

    def test_add_rejects_impossible_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "life.csv"
            run_cli("init", path=data)
            before = sha256(data)
            code, _, err = run_cli(
                "add", "--date", "2026-10-22", "--open", "2", "--high", "9", "--low", "9", "--close", "5",
                path=data,
            )
            self.assertEqual(code, 2)
            self.assertIn("low", err)
            self.assertEqual(sha256(data), before, "校验失败时不应该写文件")

    def test_add_refuses_duplicate_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "life.csv"
            run_cli("add", "--date", "2026-10-21", "--open", "5", "--high", "9", "--low", "3", "--close", "8", path=data)
            code, _, err = run_cli(
                "add", "--date", "2026-10-21", "--open", "1", "--high", "2", "--low", "0", "--close", "1", path=data
            )
            self.assertEqual(code, 2)
            self.assertIn("--force", err)

    def test_add_force_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "life.csv"
            run_cli("add", "--date", "2026-10-21", "--open", "5", "--high", "9", "--low", "3", "--close", "8", path=data)
            code, _, err = run_cli(
                "add", "--date", "2026-10-21", "--open", "1", "--high", "2", "--low", "0", "--close", "1",
                "--force", path=data,
            )
            self.assertEqual(code, 0, err)
            text = data.read_text(encoding="utf-8")
            self.assertIn("2026-10-21,1,2,0,1", text)
            self.assertEqual(text.count("2026-10-21"), 1)

    def test_no_temp_files_left_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            data = work / "life.csv"
            data.write_bytes(CSV.read_bytes())
            run_cli("chart", "--out", str(work / "a.html"), path=data)
            run_cli("stats", path=data)
            names = {p.name for p in work.rglob("*")}
            self.assertNotIn(".life-kline-cache", names)
            self.assertFalse([n for n in names if n.endswith(".tmp")], names)


if __name__ == "__main__":
    unittest.main()
