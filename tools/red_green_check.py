"""红线实证：往真实项目文件里注入 import socket，确认 test_no_network 会变红。

这不是测试用例（它需要写文件），是一次手动可复现的验证脚本：

    python3 tools/red_green_check.py

它证明 tests/test_no_network.py 的绿不是假绿 —— 一旦有人真的把 socket 引进来，
CI 会红。脚本跑完会把自己改坏的文件恢复原样，并用测试结果自证恢复成功。
"""
import shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "core" / "metrics.py"
BAK = ROOT / "core" / "metrics.py.redgreen-bak"


def run():
    return subprocess.run(
        [sys.executable, "-m", "unittest", "tests.test_no_network", "-v"],
        cwd=ROOT, capture_output=True, text=True,
    )


def main() -> int:
    shutil.copyfile(TARGET, BAK)
    try:
        before = run()
        print("=== 弄坏前 ===")
        print(before.stderr.strip().splitlines()[-1])
        before_ok = before.returncode == 0

        with TARGET.open("a", encoding="utf-8") as fh:
            fh.write("\nimport socket  # 故意注入，验证测试会变红\n")
        after = run()
        print("\n=== 注入 import socket 后 ===")
        tail = [line for line in after.stderr.splitlines() if "import" in line or "FAILED" in line]
        print("\n".join(tail[-6:]))
        after_broken = after.returncode != 0
    finally:
        shutil.move(BAK, TARGET)

    restored = run()
    print("\n=== 恢复后 ===")
    print(restored.stderr.strip().splitlines()[-1])
    restored_ok = restored.returncode == 0

    print(f"\n结论：弄坏前绿={before_ok}，弄坏后红={after_broken}，恢复后绿={restored_ok}")
    return 0 if (before_ok and after_broken and restored_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
