"""测试公用的小工具：跑 CLI、读 fixture。"""

from __future__ import annotations

import io
import subprocess
import sys
import contextlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"


def run_cli(*args: str, path: str | Path | None = None) -> tuple[int, str, str]:
    """在进程内跑 cli.main，拿到 (退出码, stdout, stderr)。"""
    sys.path.insert(0, str(ROOT))
    import cli

    argv: list[str] = []
    if path is not None:
        argv += ["--path", str(path)]
    argv += list(args)

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def run_cli_subprocess(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "cli.py"), *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
