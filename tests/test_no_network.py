"""验收判据 6：静态扫描全部 .py，不得引入任何网络能力。

用 ast 逐个文件检查 import（含 from ... import），覆盖 socket / urllib / http /
requests / ftplib / ssl / webbrowser。发现即失败，并打印是哪个文件哪一行。

验证「弄坏后会变红」：往任意 .py 里加一行 `import socket`，再跑本测试，
会在 test_no_network_imports_forbidden_modules 上失败——PR 描述里贴了红→绿实证。
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = ("socket", "urllib", "http", "requests", "ftplib", "ssl", "webbrowser")


def python_files() -> list[Path]:
    files = [p for p in ROOT.rglob("*.py") if ".git" not in p.parts]
    return sorted(files)


def imported_modules(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.append((node.lineno, node.module))
    return found


def offending(files: list[Path]) -> list[str]:
    bad: list[str] = []
    for path in files:
        for lineno, module in imported_modules(path):
            root_name = module.split(".")[0]
            if root_name in FORBIDDEN:
                try:
                    rel = path.relative_to(ROOT)
                except ValueError:
                    rel = path
                bad.append(f"{rel}:{lineno} import {module}")
    return bad


class TestNoNetworkImports(unittest.TestCase):
    def test_scans_a_non_empty_set_of_files(self):
        files = python_files()
        self.assertGreaterEqual(len(files), 6, f"扫描到的文件太少，可能路径写错了：{files}")

    def test_no_network_imports_forbidden_modules(self):
        bad = offending(python_files())
        self.assertEqual(bad, [], "发现网络相关 import：\n" + "\n".join(bad))

    def test_detector_itself_catches_socket(self):
        """自检：检测器必须能发现 `import socket`，否则上面的绿是假绿。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            bad_file = Path(tmp) / "bad.py"
            bad_file.write_text("import socket\n", encoding="utf-8")
            found = offending([bad_file])
            self.assertEqual(len(found), 1)
            self.assertIn("socket", found[0])

    def test_detector_catches_from_import(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            bad_file = Path(tmp) / "bad2.py"
            bad_file.write_text("from urllib.parse import urlparse\n", encoding="utf-8")
            self.assertEqual(len(offending([bad_file])), 1)


if __name__ == "__main__":
    unittest.main()
