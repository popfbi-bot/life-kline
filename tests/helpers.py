"""测试公用的小工具：跑 CLI、读 fixture。"""

from __future__ import annotations

import io
import subprocess
import sys
import contextlib
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"


@contextlib.contextmanager
def _empty_stdin() -> Iterator[io.StringIO]:
    """把 sys.stdin 换成空流，让 input() 立刻拿到 EOF。

    标准库直到 3.11 都没有 contextlib.redirect_stdin，所以自己写一个。
    """
    saved = sys.stdin
    sys.stdin = stream = io.StringIO("")
    try:
        yield stream
    finally:
        sys.stdin = saved


def run_cli(*args: str, path: str | Path | None = None) -> tuple[int, str, str]:
    """在进程内跑 cli.main，拿到 (退出码, stdout, stderr)。

    stdin 一律换成空流：cli 里的 `_ask()` 会走 `input()`，
    测试要保证「永远看到 EOF」，否则接着终端的 stdin 就会一直等下去。
    """
    sys.path.insert(0, str(ROOT))
    import cli

    argv: list[str] = []
    if path is not None:
        argv += ["--path", str(path)]
    argv += list(args)

    out, err = io.StringIO(), io.StringIO()
    with (
        _empty_stdin(),
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(err),
    ):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def run_cli_subprocess(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "cli.py"), *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
